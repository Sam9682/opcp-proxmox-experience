"""
Glance import for the local KVM/libvirt build path (Requirement 10).

`GlanceImporter` imports the finalized qcow2 image into OpenStack Glance as a
whole-disk image (disk_format=qcow2, container_format=bare) and waits for the
image to reach ACTIVE status, raising GlanceImportError on timeout.

Authentication reuses the shared OpenStack stack exactly as the existing
``image_builder`` flow does: ``auth.manager.OpenStackAuthManager`` consumes the
``Credentials`` carried on ``DeployConfig`` and yields an authenticated SDK
``Connection``. The request-body construction is isolated in the pure,
side-effect-free ``build_import_request`` helper so it can be property-tested
directly; it NEVER sets ``kernel_id`` or ``ramdisk_id`` (Req 10.2).
"""

import time

from ..auth.manager import OpenStackAuthManager
from ..logging_config import get_logger
from .exceptions import GlanceImportError
from .models import DeployConfig

logger = get_logger("local_build.glance_importer")

# Whole-disk image formats (Req 10.1).
_DISK_FORMAT = "qcow2"
_CONTAINER_FORMAT = "bare"

_POLL_INTERVAL_SECONDS = 10


class GlanceImporter:
    """Imports the final qcow2 image into OpenStack Glance (Req 10)."""

    def __init__(self, auth_manager: OpenStackAuthManager | None = None) -> None:
        self._auth_manager = auth_manager or OpenStackAuthManager()

    def build_import_request(self, name: str, path: str) -> dict:
        """Build the whole-disk Glance import request body.

        Pure and side-effect free: given an image name and a local qcow2
        path, returns the request dict with ``disk_format='qcow2'`` and
        ``container_format='bare'`` (Req 10.1). The result NEVER contains a
        ``kernel_id`` or ``ramdisk_id`` key, guaranteeing a whole-disk image
        rather than a split kernel/ramdisk image (Req 10.2).

        Args:
            name: The Glance image name.
            path: Local filesystem path to the final qcow2 image.

        Returns:
            A request dict suitable for ``create_image``.
        """
        return {
            "name": name,
            "disk_format": _DISK_FORMAT,
            "container_format": _CONTAINER_FORMAT,
            "filename": path,
        }

    def import_image(self, config: DeployConfig) -> str:
        """Create the Glance image and wait until its status is ACTIVE.

        Authenticates via the shared ``OpenStackAuthManager`` using the
        credentials on ``config``, creates the whole-disk Glance image from
        ``config.final_image_path`` with the name ``config.glance_image_name``,
        and polls until the image reaches ACTIVE status (Req 10.3).

        Args:
            config: Deploy configuration carrying credentials, the final image
                path, the target Glance image name, and ``glance_timeout``.

        Returns:
            The Glance image id string.

        Raises:
            GlanceImportError: If image creation fails, if the image enters
                ERROR status, or if it does not become ACTIVE within
                ``config.glance_timeout`` seconds (Req 10.4).
        """
        request = self.build_import_request(
            config.glance_image_name, config.final_image_path
        )

        logger.info(
            "Importing image '%s' into Glance from %s "
            "(disk_format=%s, container_format=%s)",
            request["name"],
            request["filename"],
            request["disk_format"],
            request["container_format"],
        )

        try:
            connection = self._auth_manager.authenticate(config.credentials)
            image = connection.image.create_image(**request)
        except Exception as e:
            error_msg = f"Failed to create Glance image '{request['name']}': {e}"
            logger.error(error_msg)
            raise GlanceImportError(error_msg) from e

        image_id = image.id
        logger.info("Glance image record created (id='%s'), waiting for ACTIVE", image_id)

        timeout = config.glance_timeout
        start_time = time.time()
        status = "UNKNOWN"

        while time.time() - start_time < timeout:
            try:
                current = connection.image.get_image(image_id)
            except Exception as e:
                error_msg = (
                    f"Failed to query status of Glance image '{image_id}': {e}"
                )
                logger.error(error_msg)
                raise GlanceImportError(error_msg) from e

            status = current.status.upper() if current.status else "UNKNOWN"

            if status == "ACTIVE":
                logger.info("Glance image '%s' is ACTIVE", image_id)
                return image_id

            if status == "ERROR":
                error_msg = f"Glance image '{image_id}' entered ERROR status"
                logger.error(error_msg)
                raise GlanceImportError(error_msg)

            logger.debug(
                "Glance image '%s' status: %s, waiting %ds...",
                image_id,
                status,
                _POLL_INTERVAL_SECONDS,
            )
            time.sleep(_POLL_INTERVAL_SECONDS)

        elapsed = int(time.time() - start_time)
        error_msg = (
            f"Glance image '{image_id}' did not reach ACTIVE status within "
            f"{timeout}s (elapsed: {elapsed}s, last status: {status})"
        )
        logger.error(error_msg)
        raise GlanceImportError(error_msg)
