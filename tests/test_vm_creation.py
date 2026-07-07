"""
Tests for VM creation.
"""

from unittest.mock import MagicMock

import pytest

from proxmox_install_automation.models import (
    ExecutionResult,
    GPUDevice,
    TestVMConfig,
)
from proxmox_install_automation.vm.creator import VMCreator


class TestVMCreator:
    """Tests for VM creation with GPU passthrough."""

    def test_create_vm_without_gpu(self):
        """Test creating a VM without GPU passthrough."""
        creator = VMCreator()
        ssh = MagicMock()

        ssh.execute_sudo.side_effect = [
            # pvesh get /cluster/nextid
            ExecutionResult(exit_code=0, stdout="100", stderr="", command=""),
            # qm create
            ExecutionResult(exit_code=0, stdout="", stderr="", command=""),
        ]

        config = TestVMConfig(name="test-vm", memory_mb=4096, cores=2, disk_gb=20)
        vm = creator.create(ssh, config, gpu=None)

        assert vm.vmid == 100
        assert vm.name == "test-vm"
        assert vm.gpu_attached is False
        assert vm.gpu_device is None

    def test_create_vm_with_gpu(self):
        """Test creating a VM with GPU passthrough."""
        creator = VMCreator()
        ssh = MagicMock()

        ssh.execute_sudo.side_effect = [
            # pvesh get /cluster/nextid
            ExecutionResult(exit_code=0, stdout="101", stderr="", command=""),
            # qm create
            ExecutionResult(exit_code=0, stdout="", stderr="", command=""),
            # qm set hostpci
            ExecutionResult(exit_code=0, stdout="", stderr="", command=""),
            # qm set cpu
            ExecutionResult(exit_code=0, stdout="", stderr="", command=""),
        ]

        config = TestVMConfig(name="gpu-vm", memory_mb=8192, cores=4)
        gpu = GPUDevice(
            pci_id="0000:41:00.0",
            vendor_id="10de",
            device_id="1eb8",
            description="NVIDIA T4",
        )

        vm = creator.create(ssh, config, gpu=gpu)

        assert vm.vmid == 101
        assert vm.gpu_attached is True
        assert vm.gpu_device == gpu

        # Verify hostpci was set
        calls = [str(c) for c in ssh.execute_sudo.call_args_list]
        assert any("hostpci0" in c for c in calls)
        assert any("41:00.0" in c for c in calls)

    def test_create_vm_with_ovmf(self):
        """Test that OVMF BIOS creates EFI disk."""
        creator = VMCreator()
        ssh = MagicMock()

        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=0, stdout="100", stderr="", command=""
        )

        config = TestVMConfig(
            name="efi-vm", bios="ovmf", machine_type="q35"
        )
        creator.create(ssh, config)

        # Check that efidisk0 was included
        calls = [str(c) for c in ssh.execute_sudo.call_args_list]
        assert any("efidisk0" in c for c in calls)

    def test_create_vm_failure(self):
        """Test VM creation failure raises error."""
        creator = VMCreator()
        ssh = MagicMock()

        ssh.execute_sudo.side_effect = [
            ExecutionResult(exit_code=0, stdout="100", stderr="", command=""),
            ExecutionResult(exit_code=1, stdout="", stderr="TASK ERROR", command=""),
        ]

        config = TestVMConfig(name="fail-vm")
        from proxmox_install_automation.exceptions import VMCreationError

        with pytest.raises(VMCreationError):
            creator.create(ssh, config)

    def test_start_vm(self):
        """Test starting a VM."""
        creator = VMCreator()
        ssh = MagicMock()

        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", command=""
        )

        assert creator.start(ssh, 100) is True

    def test_destroy_vm(self):
        """Test destroying a VM."""
        creator = VMCreator()
        ssh = MagicMock()

        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", command=""
        )

        assert creator.destroy(ssh, 100) is True

    def test_gpu_pci_address_strip_domain(self):
        """Test that PCI address domain prefix is stripped for Proxmox."""
        creator = VMCreator()
        ssh = MagicMock()

        ssh.execute_sudo.side_effect = [
            ExecutionResult(exit_code=0, stdout="100", stderr="", command=""),
            ExecutionResult(exit_code=0, stdout="", stderr="", command=""),
            ExecutionResult(exit_code=0, stdout="", stderr="", command=""),
            ExecutionResult(exit_code=0, stdout="", stderr="", command=""),
        ]

        config = TestVMConfig(name="test")
        gpu = GPUDevice(
            pci_id="0000:41:00.0",
            vendor_id="10de",
            device_id="1eb8",
            description="GPU",
        )

        creator.create(ssh, config, gpu=gpu)

        # The hostpci command should use 41:00.0 (without 0000: prefix)
        calls = [str(c) for c in ssh.execute_sudo.call_args_list]
        hostpci_calls = [c for c in calls if "hostpci" in c]
        assert any("41:00.0" in c for c in hostpci_calls)
        assert not any("0000:41:00.0" in c for c in hostpci_calls)
