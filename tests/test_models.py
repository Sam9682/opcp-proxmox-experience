"""
Tests for data models.
"""

from uuid import UUID

import pytest

from proxmox_install_automation.models import (
    BuildState,
    BuildStatus,
    Credentials,
    ExecutionResult,
    GPUDevice,
    IOMMUType,
    Instance,
    InstanceSpec,
    ProxmoxConfig,
    TestVM,
)


class TestModels:
    """Tests for data models."""

    def test_credentials_default_values(self):
        """Test Credentials defaults."""
        creds = Credentials(auth_url="https://test.com/v3", region="GRA7")
        assert creds.auth_type == "v3applicationcredential"
        assert creds.user_domain_name == "Default"
        assert creds.identity_api_version == "3"
        assert creds.interface == "public"

    def test_instance_spec_defaults(self):
        """Test InstanceSpec defaults."""
        spec = InstanceSpec(
            base_image_name="Debian 12",
            flavor_name="b3-8",
            ssh_username="debian",
            ssh_key_name="key",
            ssh_key_path="~/.ssh/id_rsa",
        )
        assert spec.network_name == "Ext-Net"
        assert spec.security_groups == ["default"]
        assert spec.use_floating_ip is True

    def test_gpu_device_creation(self):
        """Test GPUDevice creation."""
        gpu = GPUDevice(
            pci_id="0000:41:00.0",
            vendor_id="10de",
            device_id="1eb8",
            description="NVIDIA Tesla T4",
            iommu_group=1,
        )
        assert gpu.pci_id == "0000:41:00.0"
        assert gpu.vendor_id == "10de"
        assert gpu.iommu_group == 1

    def test_build_state_add_log(self):
        """Test BuildState log addition."""
        state = BuildState()
        state.add_log("Test message")
        assert len(state.logs) == 1
        assert "Test message" in state.logs[0]
        # Should have timestamp
        assert "[" in state.logs[0]

    def test_build_state_uuid(self):
        """Test BuildState has UUID."""
        state = BuildState()
        assert isinstance(state.build_id, UUID)

    def test_build_status_enum(self):
        """Test BuildStatus enumeration."""
        assert BuildStatus.PENDING.value == "pending"
        assert BuildStatus.COMPLETED.value == "completed"
        assert BuildStatus.CONFIGURING_GPU.value == "configuring_gpu"

    def test_iommu_type_enum(self):
        """Test IOMMUType enumeration."""
        assert IOMMUType.INTEL.value == "intel"
        assert IOMMUType.AMD.value == "amd"

    def test_execution_result_success(self):
        """Test ExecutionResult success property."""
        result = ExecutionResult(
            exit_code=0, stdout="ok", stderr="", command="test"
        )
        assert result.success is True

    def test_execution_result_failure(self):
        """Test ExecutionResult failure."""
        result = ExecutionResult(
            exit_code=1, stdout="", stderr="error", command="test"
        )
        assert result.success is False

    def test_proxmox_config_defaults(self):
        """Test ProxmoxConfig defaults."""
        config = ProxmoxConfig()
        assert config.version == "8.2"
        assert config.enterprise_repo is False
        assert config.storage_type == "local-lvm"
        assert config.network_bridge == "vmbr0"

    def test_test_vm_creation(self):
        """Test TestVM data model."""
        vm = TestVM(
            vmid=100,
            name="test-vm",
            status="running",
            gpu_attached=True,
            gpu_device=GPUDevice(
                pci_id="0000:41:00.0",
                vendor_id="10de",
                device_id="1eb8",
                description="GPU",
            ),
        )
        assert vm.vmid == 100
        assert vm.gpu_attached is True
        assert vm.gpu_device.vendor_id == "10de"

    def test_instance_model(self):
        """Test Instance data model."""
        instance = Instance(
            id="server-123",
            name="proxmox-installer-123",
            status="ACTIVE",
            ip_address="192.168.1.10",
        )
        assert instance.id == "server-123"
        assert instance.status == "ACTIVE"
