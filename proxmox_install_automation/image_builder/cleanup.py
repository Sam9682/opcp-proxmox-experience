"""
Cleanup manager for the image build pipeline.

Destroys temporary build resources (snapshots, instances, floating IPs)
in reverse creation order with retry logic. Failures are logged as warnings
and do not prevent cleanup of remaining resources.
"""

import time
from typing import List

from openstack.connection import Connection

from ..logging_config import get_logger
from .models import CleanupReport, CleanupResource

logger = get_logger("image_builder.cleanup")

# Constants
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1

# Priority order for cleanup (reverse creation order):
# snapshots first, then instances, then floating IPs
_RESOURCE_TYPE_PRIORITY = {
    "snapshot": 0,
    "instance": 1,
    "floating_ip": 2,
}


class ImageBuildCleanupManager:
    """Cleans up build resources in reverse creation order."""

    def __init__(self, connection: Connection) -> None:
        """
        Initialize the cleanup manager.

        Args:
            connection: An active OpenStack SDK connection.
        """
        self._connection = connection

    def cleanup(self, resources: List[CleanupResource]) -> CleanupReport:
        """
        Destroy resources in reverse creation order.

        Sorts resources by type priority (snapshots → instances → floating IPs)
        and retries each destruction up to 3 times. On failure after all retries,
        logs a warning and continues to the next resource.

        Args:
            resources: List of CleanupResource objects to destroy.

        Returns:
            CleanupReport with totals and failure details.
        """
        sorted_resources = sorted(
            resources,
            key=lambda r: _RESOURCE_TYPE_PRIORITY.get(r.resource_type, 99),
        )

        total = len(sorted_resources)
        succeeded = 0
        failed = 0
        failures: List[str] = []

        logger.info("Starting cleanup of %d resource(s)", total)

        for resource in sorted_resources:
            resource_label = (
                f"{resource.resource_type} {resource.resource_name or resource.resource_id}"
            )

            success = self._destroy_with_retries(resource)

            if success:
                succeeded += 1
                logger.info(
                    "Cleanup succeeded: %s (id=%s)",
                    resource_label,
                    resource.resource_id,
                )
            else:
                failed += 1
                failure_msg = (
                    f"Failed to destroy {resource.resource_type} "
                    f"{resource.resource_id}"
                )
                failures.append(failure_msg)
                logger.warning(
                    "Cleanup failed after %d retries: %s (id=%s)",
                    MAX_RETRIES,
                    resource_label,
                    resource.resource_id,
                )

        logger.info(
            "Cleanup complete: %d total, %d succeeded, %d failed",
            total,
            succeeded,
            failed,
        )

        return CleanupReport(
            total=total,
            succeeded=succeeded,
            failed=failed,
            failures=failures,
        )

    def _destroy_with_retries(self, resource: CleanupResource) -> bool:
        """
        Attempt to destroy a resource with retry logic.

        Args:
            resource: The resource to destroy.

        Returns:
            True if the resource was successfully destroyed, False otherwise.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._destroy_resource(resource)
                return True
            except Exception as e:
                logger.warning(
                    "Destroy attempt %d/%d failed for %s %s: %s",
                    attempt,
                    MAX_RETRIES,
                    resource.resource_type,
                    resource.resource_id,
                    str(e),
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS)

        return False

    def _destroy_resource(self, resource: CleanupResource) -> None:
        """
        Destroy a single resource using the appropriate OpenStack SDK call.

        Args:
            resource: The resource to destroy.

        Raises:
            Exception: If the destruction call fails.
        """
        if resource.resource_type == "snapshot":
            self._connection.image.delete_image(resource.resource_id)
        elif resource.resource_type == "instance":
            self._connection.compute.delete_server(resource.resource_id)
        elif resource.resource_type == "floating_ip":
            self._connection.network.delete_ip(resource.resource_id)
        else:
            raise ValueError(
                f"Unknown resource type: {resource.resource_type}"
            )
