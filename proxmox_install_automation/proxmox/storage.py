"""
Storage configuration for Proxmox VE.
"""

from ..logging_config import get_logger
from ..provisioner.ssh import SSHConnection

logger = get_logger("proxmox.storage")


class StorageConfigurator:
    """Configures storage backends for Proxmox VE."""

    def configure(self, ssh: SSHConnection, storage_type: str = "local-lvm") -> bool:
        """
        Configure storage backend.

        Args:
            ssh: Active SSH connection.
            storage_type: Storage backend type (local-lvm, dir, zfs, etc.)

        Returns:
            True if configuration succeeds.
        """
        logger.info("Configuring storage: %s", storage_type)

        if storage_type == "local-lvm":
            return self._configure_lvm(ssh)
        elif storage_type == "dir":
            return self._configure_directory(ssh)
        else:
            logger.warning("Unknown storage type '%s', using defaults", storage_type)
            return True

    def _configure_lvm(self, ssh: SSHConnection) -> bool:
        """Configure LVM-thin storage."""
        # Check if LVM is already configured
        result = ssh.execute_sudo("pvesm status")
        if "local-lvm" in result.stdout:
            logger.info("local-lvm storage already configured")
            return True

        # Create LVM thin pool if not exists
        result = ssh.execute_sudo("lvs | grep data || true")
        if "data" not in result.stdout:
            logger.info("Creating LVM thin pool")
            # Find the volume group
            result = ssh.execute_sudo("vgs --noheadings -o vg_name | tr -d ' '")
            vg_name = result.stdout.strip()
            if vg_name:
                ssh.execute_sudo(
                    f"lvcreate -l 80%FREE -n data {vg_name} -T"
                )

        logger.info("LVM storage configured")
        return True

    def _configure_directory(self, ssh: SSHConnection) -> bool:
        """Configure directory-based storage."""
        ssh.execute_sudo("mkdir -p /var/lib/vz")
        logger.info("Directory storage configured at /var/lib/vz")
        return True

    def verify_storage(self, ssh: SSHConnection) -> bool:
        """
        Verify storage is available.

        Args:
            ssh: Active SSH connection.

        Returns:
            True if storage is available.
        """
        result = ssh.execute_sudo("pvesm status")
        if result.exit_code != 0:
            return False

        logger.info("Storage status:\n%s", result.stdout)
        return "active" in result.stdout.lower() or "local" in result.stdout.lower()
