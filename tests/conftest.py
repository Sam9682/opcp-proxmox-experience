"""
Shared test fixtures.
"""

import pytest

from proxmox_install_automation.models import (
    BuildConfiguration,
    Credentials,
    GPUDevice,
    GPUPassthroughConfig,
    IOMMUType,
    InstanceSpec,
    ProxmoxConfig,
    TestVMConfig,
)


@pytest.fixture
def sample_credentials():
    """Sample OpenStack credentials."""
    return Credentials(
        auth_url="https://auth.cloud.ovh.net/v3",
        region="GRA7",
        auth_type="v3applicationcredential",
        application_credential_id="test-cred-id",
        application_credential_secret="test-secret",
        project_name="test-project",
    )


@pytest.fixture
def sample_instance_spec():
    """Sample instance specification."""
    return InstanceSpec(
        base_image_name="Debian 12",
        flavor_name="b3-8",
        ssh_username="debian",
        ssh_key_name="test-keypair",
        ssh_key_path="~/.ssh/id_rsa",
        network_name="Ext-Net",
    )


@pytest.fixture
def sample_proxmox_config():
    """Sample Proxmox configuration."""
    return ProxmoxConfig(
        version="8.2",
        enterprise_repo=False,
        root_password="test-password-123",
        storage_type="local-lvm",
        network_bridge="vmbr0",
    )


@pytest.fixture
def sample_gpu_device():
    """Sample GPU device."""
    return GPUDevice(
        pci_id="0000:41:00.0",
        vendor_id="10de",
        device_id="1eb8",
        description="NVIDIA Tesla T4",
        iommu_group=1,
        driver="vfio-pci",
    )


@pytest.fixture
def sample_gpu_passthrough_config():
    """Sample GPU passthrough configuration."""
    return GPUPassthroughConfig(
        enabled=True,
        auto_detect=True,
        iommu_type=IOMMUType.INTEL,
        blacklist_drivers=["nouveau", "nvidia"],
    )


@pytest.fixture
def sample_test_vm_config():
    """Sample test VM configuration."""
    return TestVMConfig(
        enabled=True,
        name="gpu-test-vm",
        memory_mb=8192,
        cores=4,
        disk_gb=32,
        machine_type="q35",
        bios="ovmf",
    )


@pytest.fixture
def sample_build_config(
    sample_credentials,
    sample_instance_spec,
    sample_proxmox_config,
    sample_gpu_passthrough_config,
    sample_test_vm_config,
):
    """Complete sample build configuration."""
    return BuildConfiguration(
        credentials=sample_credentials,
        instance_spec=sample_instance_spec,
        proxmox=sample_proxmox_config,
        gpu_passthrough=sample_gpu_passthrough_config,
        test_vm=sample_test_vm_config,
    )
