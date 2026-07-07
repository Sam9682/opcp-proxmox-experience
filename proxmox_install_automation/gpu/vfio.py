"""
VFIO driver binding for GPU isolation.
"""

from typing import List

from ..exceptions import VFIOBindError
from ..logging_config import get_logger
from ..models import GPUDevice
from ..provisioner.ssh import SSHConnection

logger = get_logger("gpu.vfio")


class VFIOManager:
    """Manages VFIO driver binding for PCI passthrough."""

    def bind_devices(
        self, ssh: SSHConnection, devices: List[GPUDevice], blacklist_drivers: List[str]
    ) -> bool:
        """
        Bind GPU devices to the VFIO-PCI driver.

        Args:
            ssh: Active SSH connection.
            devices: List of GPU devices to bind.
            blacklist_drivers: Drivers to blacklist.

        Returns:
            True if binding succeeds.

        Raises:
            VFIOBindError: If binding fails.
        """
        if not devices:
            logger.warning("No devices to bind to VFIO")
            return True

        logger.info("Binding %d devices to VFIO-PCI driver", len(devices))

        try:
            # Step 1: Blacklist conflicting drivers
            self._blacklist_drivers(ssh, blacklist_drivers)

            # Step 2: Configure VFIO-PCI device IDs
            self._configure_vfio_ids(ssh, devices)

            # Step 3: Create udev rules for persistent binding
            self._create_udev_rules(ssh, devices)

            logger.info("VFIO binding configuration completed")
            return True

        except VFIOBindError:
            raise
        except Exception as e:
            raise VFIOBindError(f"VFIO binding failed: {e}") from e

    def _blacklist_drivers(self, ssh: SSHConnection, drivers: List[str]) -> None:
        """Blacklist GPU drivers to prevent them from loading."""
        logger.info("Blacklisting drivers: %s", ", ".join(drivers))

        blacklist_lines = "\n".join(f"blacklist {driver}" for driver in drivers)
        ssh.execute_sudo(
            f"bash -c 'echo \"{blacklist_lines}\" > /etc/modprobe.d/blacklist-gpu.conf'"
        )

        # Also add softdep to ensure vfio-pci loads first
        softdep_lines = "\n".join(
            f"softdep {driver} pre: vfio-pci" for driver in drivers
        )
        ssh.execute_sudo(
            f"bash -c 'echo \"{softdep_lines}\" >> /etc/modprobe.d/blacklist-gpu.conf'"
        )

    def _configure_vfio_ids(self, ssh: SSHConnection, devices: List[GPUDevice]) -> None:
        """Configure VFIO-PCI to claim specific device IDs."""
        # Build list of vendor:device pairs
        ids = set()
        for device in devices:
            ids.add(f"{device.vendor_id}:{device.device_id}")

        ids_str = ",".join(sorted(ids))
        logger.info("VFIO-PCI device IDs: %s", ids_str)

        # Write modprobe configuration
        ssh.execute_sudo(
            f"bash -c 'echo \"options vfio-pci ids={ids_str}\" > /etc/modprobe.d/vfio.conf'"
        )

    def _create_udev_rules(self, ssh: SSHConnection, devices: List[GPUDevice]) -> None:
        """Create udev rules for persistent VFIO binding."""
        rules = []
        for device in devices:
            # Create a udev rule that binds the device to vfio-pci
            rule = (
                f'ACTION=="add", ATTR{{vendor}}=="0x{device.vendor_id}", '
                f'ATTR{{device}}=="0x{device.device_id}", '
                f'DRIVER=="", ATTR{{driver_override}}="vfio-pci"'
            )
            rules.append(rule)

        rules_content = "\n".join(rules)
        ssh.execute_sudo(
            f"bash -c 'echo \"{rules_content}\" > /etc/udev/rules.d/99-vfio.rules'"
        )
        ssh.execute_sudo("udevadm control --reload-rules")

    def verify_binding(self, ssh: SSHConnection, devices: List[GPUDevice]) -> bool:
        """
        Verify devices are bound to VFIO-PCI.

        Args:
            ssh: Active SSH connection.
            devices: Devices to check.

        Returns:
            True if all devices are bound to vfio-pci.
        """
        logger.info("Verifying VFIO binding for %d devices", len(devices))
        all_bound = True

        for device in devices:
            result = ssh.execute_sudo(
                f"lspci -ks {device.pci_id} | grep 'Kernel driver in use:'"
            )
            if "vfio-pci" in result.stdout:
                logger.info("  ✓ %s (%s) bound to vfio-pci", device.pci_id, device.description)
            else:
                driver = result.stdout.strip() if result.stdout.strip() else "none"
                logger.warning(
                    "  ✗ %s (%s) NOT bound to vfio-pci (current: %s)",
                    device.pci_id,
                    device.description,
                    driver,
                )
                all_bound = False

        return all_bound

    def unbind_device(self, ssh: SSHConnection, device: GPUDevice) -> bool:
        """
        Unbind a device from its current driver.

        Args:
            ssh: Active SSH connection.
            device: Device to unbind.

        Returns:
            True if unbinding succeeds.
        """
        logger.info("Unbinding %s from current driver", device.pci_id)
        result = ssh.execute_sudo(
            f"echo '{device.pci_id}' > /sys/bus/pci/devices/{device.pci_id}/driver/unbind 2>/dev/null || true"
        )
        return True

    def manual_bind_vfio(self, ssh: SSHConnection, device: GPUDevice) -> bool:
        """
        Manually bind a device to vfio-pci (for runtime binding without reboot).

        Args:
            ssh: Active SSH connection.
            device: Device to bind.

        Returns:
            True if binding succeeds.
        """
        logger.info("Manually binding %s to vfio-pci", device.pci_id)

        # Unbind from current driver
        self.unbind_device(ssh, device)

        # Set driver override
        ssh.execute_sudo(
            f"echo 'vfio-pci' > /sys/bus/pci/devices/{device.pci_id}/driver_override"
        )

        # Probe the device
        ssh.execute_sudo(
            f"echo '{device.pci_id}' > /sys/bus/pci/drivers/vfio-pci/bind"
        )

        # Verify
        result = ssh.execute_sudo(
            f"lspci -ks {device.pci_id} | grep 'Kernel driver in use:'"
        )
        return "vfio-pci" in result.stdout
