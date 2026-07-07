"""
Resource cleanup manager.
"""

from typing import List, Tuple

from ..logging_config import get_logger
from ..models import Instance

logger = get_logger("cleanup.manager")


class CleanupManager:
    """Manages cleanup of OpenStack resources."""

    def __init__(self) -> None:
        self._instances: List[Tuple[object, Instance]] = []

    def register_instance(self, provisioner: object, instance: Instance) -> None:
        """Register an instance for cleanup."""
        self._instances.append((provisioner, instance))
        logger.debug("Registered instance '%s' for cleanup", instance.name)

    def cleanup_all(self) -> bool:
        """
        Clean up all registered resources.

        Returns:
            True if all cleanup succeeds.
        """
        logger.info("Starting cleanup of %d registered resources", len(self._instances))
        success = True

        for provisioner, instance in self._instances:
            try:
                provisioner.destroy_instance(instance)
                logger.info("Cleaned up instance: %s", instance.name)
            except Exception as e:
                logger.error("Failed to cleanup instance '%s': %s", instance.name, e)
                success = False

        self._instances.clear()
        return success

    def cleanup_instance(self, provisioner: object, instance: Instance) -> bool:
        """
        Clean up a specific instance.

        Args:
            provisioner: Instance provisioner.
            instance: Instance to clean up.

        Returns:
            True if cleanup succeeds.
        """
        try:
            provisioner.destroy_instance(instance)
            logger.info("Cleaned up instance: %s", instance.name)
            # Remove from registry
            self._instances = [
                (p, i) for p, i in self._instances if i.id != instance.id
            ]
            return True
        except Exception as e:
            logger.error("Failed to cleanup instance '%s': %s", instance.name, e)
            return False
