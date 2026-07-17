"""
Glance image uploader for the image building pipeline.

Uploads qcow2 images to OpenStack Glance with metadata, handles
retry logic, and polls for ACTIVE status.
"""

import time

from openstack.connection import Connection

from ..logging_config import get_logger
from .exceptions import GlanceUploadError
from .models import ImageMetadata

logger = get_logger("image_builder.glance_uploader")

_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 10
_POLL_INTERVAL_SECONDS = 10


class GlanceUploader:
    """
    Uploads qcow2 images to OpenStack Glance.

    Handles image creation with metadata, data upload with retry logic,
    and polling until the image reaches ACTIVE status.
    """

    def upload(
        self,
        connection: Connection,
        image_data: bytes,
        metadata: ImageMetadata,
    ) -> str:
        """
        Upload a qcow2 image to Glance with metadata.

        Creates a Glance image record with the specified metadata, uploads
        the raw image data, and returns the image ID. Retries the entire
        operation up to 3 times on failure.

        Args:
            connection: An authenticated OpenStack SDK Connection object.
            image_data: Raw bytes of the qcow2 image file.
            metadata: ImageMetadata with name, formats, and custom properties.

        Returns:
            The Glance image ID string.

        Raises:
            GlanceUploadError: If the upload fails after 3 retry attempts,
                including the HTTP status code and response body from the
                last failure.
        """
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                logger.info(
                    "Uploading image '%s' to Glance (attempt %d/%d)",
                    metadata.name,
                    attempt,
                    _MAX_RETRIES,
                )

                image = connection.image.create_image(
                    name=metadata.name,
                    disk_format=metadata.disk_format,
                    container_format=metadata.container_format,
                    visibility=metadata.visibility,
                    proxmox_version=metadata.proxmox_version,
                    build_timestamp=metadata.build_timestamp,
                )

                logger.info(
                    "Image record created with id='%s', uploading data...",
                    image.id,
                )

                connection.image.upload_image(image, data=image_data)

                logger.info(
                    "Image '%s' uploaded successfully (id='%s')",
                    metadata.name,
                    image.id,
                )
                return image.id

            except Exception as e:
                last_error = e
                logger.warning(
                    "Upload attempt %d/%d failed: %s",
                    attempt,
                    _MAX_RETRIES,
                    e,
                )

                if attempt < _MAX_RETRIES:
                    logger.info(
                        "Retrying in %d seconds...", _RETRY_DELAY_SECONDS
                    )
                    time.sleep(_RETRY_DELAY_SECONDS)

        # All retries exhausted
        http_status = getattr(last_error, "status_code", None) or getattr(
            last_error, "http_status", "unknown"
        )
        response_body = getattr(last_error, "details", None) or str(
            last_error
        )

        error_msg = (
            f"Glance upload failed after {_MAX_RETRIES} attempts. "
            f"HTTP status: {http_status}, response: {response_body}"
        )
        logger.error(error_msg)
        raise GlanceUploadError(error_msg) from last_error

    def wait_for_active(
        self,
        connection: Connection,
        image_id: str,
        timeout: int,
    ) -> bool:
        """
        Poll the image status until it reaches ACTIVE or timeout.

        Checks the image status every 10 seconds. Raises an error if
        the image enters ERROR status or the timeout is exceeded.

        Args:
            connection: An authenticated OpenStack SDK Connection object.
            image_id: The Glance image ID to monitor.
            timeout: Maximum seconds to wait for ACTIVE status.

        Returns:
            True when the image reaches ACTIVE status.

        Raises:
            GlanceUploadError: If the image status becomes ERROR or the
                timeout is exceeded.
        """
        logger.info(
            "Waiting for image '%s' to become ACTIVE (timeout: %ds)",
            image_id,
            timeout,
        )
        start_time = time.time()

        while time.time() - start_time < timeout:
            image = connection.image.get_image(image_id)
            status = image.status.upper() if image.status else "UNKNOWN"

            if status == "ACTIVE":
                logger.info("Image '%s' is ACTIVE", image_id)
                return True

            if status == "ERROR":
                logger.error(
                    "Image '%s' entered ERROR status", image_id
                )
                raise GlanceUploadError(
                    f"Image '{image_id}' entered ERROR status"
                )

            logger.debug(
                "Image '%s' status: %s, waiting %ds...",
                image_id,
                status,
                _POLL_INTERVAL_SECONDS,
            )
            time.sleep(_POLL_INTERVAL_SECONDS)

        # Timeout reached
        elapsed = int(time.time() - start_time)
        logger.error(
            "Image '%s' did not reach ACTIVE within %ds (elapsed: %ds)",
            image_id,
            timeout,
            elapsed,
        )
        raise GlanceUploadError(
            f"Image '{image_id}' did not reach ACTIVE status "
            f"within {timeout}s (last status: {status})"
        )
