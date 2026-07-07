"""
VM creation with GPU PCI passthrough.
"""

from typing import Optional

from ..exceptions import VMCreationError
from ..logging_config import get_logger
from ..models import GPUDevice, TestVM, TestVMConfig
from ..provisioner.ssh import SSHConnection

logger = get_logger("vm.creator")


class VMCreator:
    """Creates Proxmox VMs with GPU passthrough."""

    def __init__(self) -> None:
        self._next_vmid = 100

    def create(
        self,
        ssh: SSHConnection,
        config: TestVMConfig,
        gpu: Optional[GPUDevice] = None,
    ) -> TestVM:
        """
        Create a VM in Proxmox with optional GPU passthrough.

        Args:
            ssh: Active SSH connection.
            config: VM configuration.
            gpu: Optional GPU device to attach.

        Returns:
            TestVM object.

        Raises:
            VMCreationError: If VM creation fails.
        """
        vmid = self._get_next_vmid(ssh)
        logger.info(
            "Creating VM '%s' (VMID: %d) with %d MB RAM, %d cores",
            config.name,
            vmid,
            config.memory_mb,
            config.cores,
        )

        try:
            # Build qm create command
            cmd_parts = [
                f"qm create {vmid}",
                f"--name {config.name}",
                f"--memory {config.memory_mb}",
                f"--cores {config.cores}",
                f"--machine {config.machine_type}",
                f"--bios {config.bios}",
                f"--ostype {config.os_type}",
                f"--net0 virtio,bridge={config.network_bridge}",
                f"--scsihw virtio-scsi-single",
            ]

            # Add disk
            cmd_parts.append(
                f"--scsi0 local-lvm:{config.disk_gb},iothread=1"
            )

            # Add EFI disk for OVMF
            if config.bios == "ovmf":
                cmd_parts.append("--efidisk0 local-lvm:1,efitype=4m")

            # Add ISO if specified
            if config.os_iso:
                cmd_parts.append(f"--cdrom {config.os_iso}")

            # Create the VM
            create_cmd = " ".join(cmd_parts)
            result = ssh.execute_sudo(create_cmd)
            if result.exit_code != 0:
                raise VMCreationError(
                    f"Failed to create VM: {result.stderr}"
                )

            logger.info("VM %d created successfully", vmid)

            # Attach GPU if provided
            gpu_attached = False
            if gpu:
                gpu_attached = self._attach_gpu(ssh, vmid, gpu)

            return TestVM(
                vmid=vmid,
                name=config.name,
                status="created",
                gpu_attached=gpu_attached,
                gpu_device=gpu if gpu_attached else None,
            )

        except VMCreationError:
            raise
        except Exception as e:
            raise VMCreationError(f"VM creation failed: {e}") from e

    def _attach_gpu(self, ssh: SSHConnection, vmid: int, gpu: GPUDevice) -> bool:
        """
        Attach a GPU to a VM via PCI passthrough.

        Args:
            ssh: Active SSH connection.
            vmid: VM ID.
            gpu: GPU device to attach.

        Returns:
            True if attachment succeeds.
        """
        logger.info(
            "Attaching GPU %s (%s) to VM %d",
            gpu.pci_id,
            gpu.description,
            vmid,
        )

        # Strip the domain prefix for Proxmox (0000:41:00.0 -> 41:00.0)
        pci_addr = gpu.pci_id
        if pci_addr.startswith("0000:"):
            pci_addr = pci_addr[5:]

        # Add hostpci device
        result = ssh.execute_sudo(
            f"qm set {vmid} --hostpci0 {pci_addr},pcie=1,x-vga=1"
        )
        if result.exit_code != 0:
            logger.error("Failed to attach GPU: %s", result.stderr)
            return False

        # Enable CPU flags needed for passthrough
        result = ssh.execute_sudo(
            f"qm set {vmid} --cpu host,hidden=1,flags=+pcid"
        )

        logger.info("GPU attached to VM %d", vmid)
        return True

    def start(self, ssh: SSHConnection, vmid: int) -> bool:
        """
        Start a VM.

        Args:
            ssh: Active SSH connection.
            vmid: VM ID to start.

        Returns:
            True if VM started successfully.
        """
        logger.info("Starting VM %d", vmid)
        result = ssh.execute_sudo(f"qm start {vmid}")
        if result.exit_code != 0:
            logger.error("Failed to start VM %d: %s", vmid, result.stderr)
            return False
        return True

    def stop(self, ssh: SSHConnection, vmid: int) -> bool:
        """Stop a VM."""
        logger.info("Stopping VM %d", vmid)
        result = ssh.execute_sudo(f"qm stop {vmid}")
        return result.exit_code == 0

    def destroy(self, ssh: SSHConnection, vmid: int) -> bool:
        """
        Destroy a VM and its disks.

        Args:
            ssh: Active SSH connection.
            vmid: VM ID to destroy.

        Returns:
            True if VM destroyed successfully.
        """
        logger.info("Destroying VM %d", vmid)
        # Stop first
        ssh.execute_sudo(f"qm stop {vmid} 2>/dev/null || true")
        # Destroy
        result = ssh.execute_sudo(f"qm destroy {vmid} --purge")
        if result.exit_code != 0:
            logger.warning("Failed to destroy VM %d: %s", vmid, result.stderr)
            return False
        return True

    def _get_next_vmid(self, ssh: SSHConnection) -> int:
        """Get the next available VM ID."""
        result = ssh.execute_sudo("pvesh get /cluster/nextid")
        if result.exit_code == 0 and result.stdout.strip().isdigit():
            return int(result.stdout.strip())
        return self._next_vmid
