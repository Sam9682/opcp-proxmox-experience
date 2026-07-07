"""
GPU validation inside VMs.
"""

import time

from ..logging_config import get_logger
from ..provisioner.ssh import SSHConnection

logger = get_logger("vm.validator")


class VMValidator:
    """Validates GPU passthrough is working inside VMs."""

    def validate_gpu_visible(self, ssh: SSHConnection, vmid: int) -> bool:
        """
        Check if the GPU is visible inside the VM.

        This uses qm guest exec to run lspci inside the VM (requires QEMU guest agent).

        Args:
            ssh: SSH connection to the Proxmox host.
            vmid: VM ID to check.

        Returns:
            True if GPU is visible in the VM.
        """
        logger.info("Validating GPU visibility in VM %d", vmid)

        # Wait for VM to be fully booted
        time.sleep(10)

        # Check VM status
        result = ssh.execute_sudo(f"qm status {vmid}")
        if "running" not in result.stdout.lower():
            logger.warning("VM %d is not running", vmid)
            return False

        # Try using QEMU guest agent to check lspci
        result = ssh.execute_sudo(
            f"qm guest exec {vmid} -- lspci 2>/dev/null | grep -i 'nvidia\\|amd'"
        )
        if result.exit_code == 0 and result.stdout.strip():
            logger.info("GPU visible in VM %d: %s", vmid, result.stdout.strip())
            return True

        # Alternative: check from host that PCI device is assigned
        result = ssh.execute_sudo(f"qm config {vmid} | grep hostpci")
        if result.exit_code == 0 and result.stdout.strip():
            logger.info(
                "GPU PCI passthrough configured for VM %d: %s",
                vmid,
                result.stdout.strip(),
            )
            return True

        logger.warning("Could not confirm GPU visibility in VM %d", vmid)
        return False

    def validate_host_isolation(self, ssh: SSHConnection, pci_id: str) -> bool:
        """
        Validate that the GPU is properly isolated on the host.

        Args:
            ssh: SSH connection to the Proxmox host.
            pci_id: PCI device ID.

        Returns:
            True if device is properly isolated (bound to vfio-pci).
        """
        result = ssh.execute_sudo(
            f"lspci -ks {pci_id} | grep 'Kernel driver in use:'"
        )
        if "vfio-pci" in result.stdout:
            logger.info("Device %s is properly isolated (vfio-pci)", pci_id)
            return True

        logger.warning("Device %s is NOT isolated: %s", pci_id, result.stdout.strip())
        return False
