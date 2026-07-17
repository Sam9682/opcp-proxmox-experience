"""
Snapshot management for the image building pipeline.

Handles creating, polling, and deleting OpenStack server snapshots
used as intermediate artifacts in the Proxmox qcow2 image build process.
"""

import time
from datetime import datetime

from openstack.connection import Connection

from .exceptions import SnapshotError
from ..logging_config import get_logger

logger = get_logger("image_builder.snapshot")


def generate_snapshot_name(version: str, build_start_time: datetime) -> str:
    """
    Generate a snapshot name from a Proxmox version and build start time.

    Args:
        version: Proxmox version string (e.g. "8.2").
        build_start_time: UTC datetime representing when the build started.

    Returns:
        Snapshot name in format `proxmox-{version}-{YYYYMMDD-HHMMSS}`.
    """
    timestamp = build_start_time.strftime("%Y%m%d-%H%M%S")
    return f"proxmox-{version}-{timestamp}"


class SnapshotManager:
    """
    Manages OpenStack server snapshots for the image building pipeline.

    Creates server snapshots, polls for ACTIVE status, and handles
    cleanup on failure or timeout.
    """

    def create_snapshot(
        self, connection: Connection, server_id: str, name: str
    ) -> str:
        """
        Create a server snapshot using the OpenStack Compute API.

        Args:
            connection: An authenticated OpenStack SDK Connection object.
            server_id: The ID of the server to snapshot.
            name: The name to assign to the snapshot image.

        Returns:
            The snapshot image ID.

        Raises:
            SnapshotError: If the snapshot creation API call fails.
        """
        logger.info(
            "Creating snapshot '%s' from server '%s'", name, server_id
        )

        try:
            image_id = connection.compute.create_server_image(
                server_id, name=name
            )
            logger.info(
                "Snapshot '%s' creation initiated with image id '%s'",
                name,
                image_id,
            )
            return image_id
        except Exception as e:
            raise SnapshotError(
                f"Failed to create snapshot '{name}' from server "
                f"'{server_id}': {e}"
            ) from e

    def wait_for_active(
        self,
        connection: Connection,
        image_id: str,
        timeout: int = 1800,
        poll_interval: int = 10,
    ) -> bool:
        """
        Poll snapshot image status until ACTIVE or timeout.

        Args:
            connection: An authenticated OpenStack SDK Connection object.
            image_id: The snapshot image ID to monitor.
            timeout: Maximum seconds to wait (default 1800).
            poll_interval: Seconds between status checks (default 10).

        Returns:
            True if the snapshot reached ACTIVE status.

        Raises:
            SnapshotError: If the snapshot does not reach ACTIVE status
                within the timeout or enters an error state. The error
                includes the snapshot name, last observed status, and
                elapsed wait time.
        """
        logger.info(
            "Waiting for snapshot image '%s' to become ACTIVE (timeout: %ds)",
            image_id,
            timeout,
        )
        start_time = time.time()
        last_status = "UNKNOWN"

        while time.time() - start_time < timeout:
            image = connection.image.get_image(image_id)
            last_status = image.status.upper() if image.status else "UNKNOWN"

            if last_status == "ACTIVE":
                elapsed = int(time.time() - start_time)
                logger.info(
                    "Snapshot image '%s' is ACTIVE after %ds",
                    image_id,
                    elapsed,
                )
                return True

            if last_status in ("ERROR", "KILLED", "DELETED"):
                elapsed = int(time.time() - start_time)
                image_name = image.name or image_id
                logger.error(
                    "Snapshot image '%s' entered %s status after %ds",
                    image_name,
                    last_status,
                    elapsed,
                )
                raise SnapshotError(
                    f"Snapshot '{image_name}' entered {last_status} status "
                    f"after {elapsed}s"
                )

            logger.debug(
                "Snapshot image '%s' status: %s, waiting %ds...",
                image_id,
                last_status,
                poll_interval,
            )
            time.sleep(poll_interval)

        # Timeout reached
        elapsed = int(time.time() - start_time)
        image = connection.image.get_image(image_id)
        image_name = image.name or image_id if image else image_id
        last_status = (
            image.status.upper() if image and image.status else "UNKNOWN"
        )

        logger.error(
            "Snapshot '%s' did not become ACTIVE within %ds "
            "(last status: %s, elapsed: %ds)",
            image_name,
            timeout,
            last_status,
            elapsed,
        )
        raise SnapshotError(
            f"Snapshot '{image_name}' did not reach ACTIVE status within "
            f"{timeout}s (last status: {last_status}, elapsed: {elapsed}s)"
        )

    def delete_snapshot(
        self, connection: Connection, image_id: str
    ) -> bool:
        """
        Delete a snapshot image.

        Args:
            connection: An authenticated OpenStack SDK Connection object.
            image_id: The snapshot image ID to delete.

        Returns:
            True if deletion succeeded, False otherwise.
        """
        logger.info("Deleting snapshot image '%s'", image_id)
        try:
            connection.image.delete_image(image_id)
            logger.info("Snapshot image '%s' deletion initiated", image_id)
            return True
        except Exception as e:
            logger.warning(
                "Failed to delete snapshot image '%s': %s", image_id, e
            )
            return False
