"""
Tests for GPU detection and passthrough.
"""

from unittest.mock import MagicMock, patch

import pytest

from proxmox_install_automation.gpu.detector import GPUDetector
from proxmox_install_automation.gpu.iommu import IOMMUConfigurator
from proxmox_install_automation.gpu.vfio import VFIOManager
from proxmox_install_automation.models import ExecutionResult, GPUDevice, IOMMUType


class TestGPUDetector:
    """Tests for GPU device detection."""

    def test_detect_nvidia_gpu(self):
        """Test detection of NVIDIA GPU."""
        detector = GPUDetector()
        ssh = MagicMock()

        # Mock lspci output
        lspci_output = (
            "41:00.0 3D controller [0302]: NVIDIA Corporation Tesla T4 [10de:1eb8] (rev a1)\n"
        )
        ssh.execute_sudo.side_effect = [
            ExecutionResult(exit_code=0, stdout=lspci_output, stderr="", command="lspci"),
            # Audio device check
            ExecutionResult(exit_code=1, stdout="", stderr="", command="lspci"),
            # IOMMU groups
            ExecutionResult(
                exit_code=0,
                stdout="/sys/kernel/iommu_groups/1/devices/0000:41:00.0\n",
                stderr="",
                command="find",
            ),
        ]

        devices = detector.detect(ssh)

        assert len(devices) == 1
        assert devices[0].vendor_id == "10de"
        assert devices[0].device_id == "1eb8"
        assert "Tesla T4" in devices[0].description

    def test_detect_no_gpu(self):
        """Test detection when no GPU is present."""
        detector = GPUDetector()
        ssh = MagicMock()

        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=1, stdout="", stderr="", command="lspci"
        )

        devices = detector.detect(ssh)
        assert len(devices) == 0

    def test_detect_multiple_gpus(self):
        """Test detection of multiple GPUs."""
        detector = GPUDetector()
        ssh = MagicMock()

        lspci_output = (
            "41:00.0 3D controller [0302]: NVIDIA Corporation Tesla T4 [10de:1eb8] (rev a1)\n"
            "81:00.0 VGA compatible controller [0300]: NVIDIA Corporation Tesla V100 [10de:1db4] (rev a1)\n"
        )
        ssh.execute_sudo.side_effect = [
            ExecutionResult(exit_code=0, stdout=lspci_output, stderr="", command="lspci"),
            # Audio checks
            ExecutionResult(exit_code=1, stdout="", stderr="", command="lspci"),
            ExecutionResult(exit_code=1, stdout="", stderr="", command="lspci"),
            # IOMMU groups
            ExecutionResult(
                exit_code=0,
                stdout=(
                    "/sys/kernel/iommu_groups/1/devices/0000:41:00.0\n"
                    "/sys/kernel/iommu_groups/2/devices/0000:81:00.0\n"
                ),
                stderr="",
                command="find",
            ),
        ]

        devices = detector.detect(ssh)
        assert len(devices) == 2


class TestIOMMUConfigurator:
    """Tests for IOMMU configuration."""

    def test_configure_intel_iommu(self):
        """Test Intel IOMMU configuration."""
        configurator = IOMMUConfigurator()
        ssh = MagicMock()

        # Mock responses
        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=0,
            stdout='GRUB_CMDLINE_LINUX_DEFAULT="quiet"',
            stderr="",
            command="",
        )

        result = configurator.configure(ssh, IOMMUType.INTEL)
        assert result is True

        # Verify sed was called with intel_iommu=on
        calls = ssh.execute_sudo.call_args_list
        sed_calls = [c for c in calls if "sed" in str(c)]
        assert any("intel_iommu=on" in str(c) for c in sed_calls)

    def test_verify_iommu_enabled(self):
        """Test IOMMU verification."""
        configurator = IOMMUConfigurator()
        ssh = MagicMock()

        ssh.execute_sudo.side_effect = [
            ExecutionResult(
                exit_code=0,
                stdout="[    0.000000] DMAR: IOMMU enabled\n",
                stderr="",
                command="dmesg",
            ),
            ExecutionResult(
                exit_code=0, stdout="15\n", stderr="", command="find"
            ),
        ]

        assert configurator.verify(ssh) is True

    def test_verify_iommu_not_enabled(self):
        """Test IOMMU verification when not enabled."""
        configurator = IOMMUConfigurator()
        ssh = MagicMock()

        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", command="dmesg"
        )

        assert configurator.verify(ssh) is False


class TestVFIOManager:
    """Tests for VFIO driver binding."""

    def test_bind_devices(self):
        """Test VFIO device binding configuration."""
        vfio = VFIOManager()
        ssh = MagicMock()
        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", command=""
        )

        devices = [
            GPUDevice(
                pci_id="0000:41:00.0",
                vendor_id="10de",
                device_id="1eb8",
                description="NVIDIA T4",
            ),
        ]

        result = vfio.bind_devices(ssh, devices, ["nouveau", "nvidia"])
        assert result is True

        # Verify blacklist was written
        calls = [str(c) for c in ssh.execute_sudo.call_args_list]
        assert any("blacklist" in c for c in calls)
        assert any("vfio-pci" in c for c in calls)

    def test_bind_empty_devices(self):
        """Test binding with no devices is a no-op."""
        vfio = VFIOManager()
        ssh = MagicMock()

        result = vfio.bind_devices(ssh, [], ["nouveau"])
        assert result is True

    def test_verify_binding_success(self):
        """Test verifying successful VFIO binding."""
        vfio = VFIOManager()
        ssh = MagicMock()

        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=0,
            stdout="Kernel driver in use: vfio-pci",
            stderr="",
            command="lspci",
        )

        devices = [
            GPUDevice(
                pci_id="0000:41:00.0",
                vendor_id="10de",
                device_id="1eb8",
                description="NVIDIA T4",
            ),
        ]

        assert vfio.verify_binding(ssh, devices) is True

    def test_verify_binding_failure(self):
        """Test verifying failed VFIO binding."""
        vfio = VFIOManager()
        ssh = MagicMock()

        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=0,
            stdout="Kernel driver in use: nouveau",
            stderr="",
            command="lspci",
        )

        devices = [
            GPUDevice(
                pci_id="0000:41:00.0",
                vendor_id="10de",
                device_id="1eb8",
                description="NVIDIA T4",
            ),
        ]

        assert vfio.verify_binding(ssh, devices) is False
