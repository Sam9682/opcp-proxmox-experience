"""
IOMMU configuration for PCI passthrough.
"""

from ..exceptions import IOMMUConfigError
from ..logging_config import get_logger
from ..models import IOMMUType
from ..provisioner.ssh import SSHConnection

logger = get_logger("gpu.iommu")


class IOMMUConfigurator:
    """Configures IOMMU for PCI passthrough."""

    def configure(self, ssh: SSHConnection, iommu_type: IOMMUType) -> bool:
        """
        Configure IOMMU kernel parameters and modules.

        Args:
            ssh: Active SSH connection.
            iommu_type: Intel or AMD IOMMU type.

        Returns:
            True if configuration succeeds.

        Raises:
            IOMMUConfigError: If configuration fails.
        """
        logger.info("Configuring IOMMU (type: %s)", iommu_type.value)

        try:
            # Step 1: Configure GRUB kernel parameters
            self._configure_grub(ssh, iommu_type)

            # Step 2: Load required kernel modules
            self._configure_modules(ssh)

            # Step 3: Update initramfs
            self._update_initramfs(ssh)

            logger.info("IOMMU configuration completed - reboot required")
            return True

        except IOMMUConfigError:
            raise
        except Exception as e:
            raise IOMMUConfigError(f"IOMMU configuration failed: {e}") from e

    def _configure_grub(self, ssh: SSHConnection, iommu_type: IOMMUType) -> None:
        """Configure GRUB with IOMMU parameters."""
        logger.info("Configuring GRUB for IOMMU")

        if iommu_type == IOMMUType.INTEL:
            iommu_param = "intel_iommu=on"
        else:
            iommu_param = "amd_iommu=on"

        # Additional parameters for passthrough
        grub_params = f"{iommu_param} iommu=pt"

        # Read current GRUB config
        result = ssh.execute_sudo("cat /etc/default/grub")
        if result.exit_code != 0:
            raise IOMMUConfigError("Failed to read GRUB configuration")

        grub_content = result.stdout

        # Update GRUB_CMDLINE_LINUX_DEFAULT
        if iommu_param in grub_content:
            logger.info("IOMMU already configured in GRUB")
        else:
            # Replace the GRUB_CMDLINE_LINUX_DEFAULT line
            ssh.execute_sudo(
                f"sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT=\"\\(.*\\)\"/GRUB_CMDLINE_LINUX_DEFAULT=\"\\1 {grub_params}\"/' /etc/default/grub"
            )

        # Update GRUB
        result = ssh.execute_sudo("update-grub")
        if result.exit_code != 0:
            raise IOMMUConfigError(f"update-grub failed: {result.stderr}")

        logger.info("GRUB configured with: %s", grub_params)

    def _configure_modules(self, ssh: SSHConnection) -> None:
        """Configure required kernel modules."""
        logger.info("Configuring VFIO kernel modules")

        modules = [
            "vfio",
            "vfio_iommu_type1",
            "vfio_pci",
            "vfio_virqfd",
        ]

        # Add modules to /etc/modules
        for module in modules:
            ssh.execute_sudo(
                f"grep -q '{module}' /etc/modules || echo '{module}' >> /etc/modules"
            )

        # Also add to modprobe configuration
        modules_conf = "\\n".join(modules)
        ssh.execute_sudo(
            f"bash -c 'echo -e \"{modules_conf}\" > /etc/modules-load.d/vfio.conf'"
        )

        logger.info("VFIO modules configured: %s", ", ".join(modules))

    def _update_initramfs(self, ssh: SSHConnection) -> None:
        """Update initramfs to include VFIO modules."""
        logger.info("Updating initramfs")
        result = ssh.execute_sudo("update-initramfs -u -k all", timeout=120)
        if result.exit_code != 0:
            raise IOMMUConfigError(f"update-initramfs failed: {result.stderr}")

    def verify(self, ssh: SSHConnection) -> bool:
        """
        Verify IOMMU is enabled after reboot.

        Args:
            ssh: Active SSH connection.

        Returns:
            True if IOMMU is enabled.
        """
        logger.info("Verifying IOMMU is enabled")

        # Check dmesg for IOMMU
        result = ssh.execute_sudo("dmesg | grep -i iommu | head -5")
        if "IOMMU" in result.stdout or "DMAR" in result.stdout:
            logger.info("IOMMU is enabled in kernel")

            # Check IOMMU groups exist
            result = ssh.execute_sudo(
                "find /sys/kernel/iommu_groups/ -maxdepth 1 -mindepth 1 -type d | wc -l"
            )
            group_count = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
            logger.info("Found %d IOMMU groups", group_count)
            return group_count > 0

        logger.error("IOMMU does not appear to be enabled")
        return False
