"""
Core data models for Proxmox Install Automation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID, uuid4


class BuildStatus(str, Enum):
    """Build status enumeration."""
    PENDING = "pending"
    PROVISIONING = "provisioning"
    INSTALLING_PROXMOX = "installing_proxmox"
    CONFIGURING_GPU = "configuring_gpu"
    CREATING_VM = "creating_vm"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IOMMUType(str, Enum):
    """IOMMU type enumeration."""
    INTEL = "intel"
    AMD = "amd"


@dataclass
class Credentials:
    """OpenStack authentication credentials."""
    auth_url: str
    region: str
    auth_type: str = "v3applicationcredential"
    application_credential_id: Optional[str] = None
    application_credential_secret: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    project_name: Optional[str] = None
    user_domain_name: str = "Default"
    project_domain_name: str = "Default"
    identity_api_version: str = "3"
    interface: str = "public"


@dataclass
class InstanceSpec:
    """Specification for creating a baremetal instance."""
    base_image_name: str
    flavor_name: str
    ssh_username: str
    ssh_key_name: str
    ssh_key_path: str
    network_name: str = "Ext-Net"
    security_groups: List[str] = field(default_factory=lambda: ["default"])
    availability_zone: Optional[str] = None
    use_floating_ip: bool = True
    floating_ip_pool: Optional[str] = None


@dataclass
class Instance:
    """Represents a provisioned baremetal instance."""
    id: str
    name: str
    status: str
    ip_address: Optional[str] = None
    floating_ip: Optional[str] = None
    flavor: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class GPUDevice:
    """Represents a GPU PCI device."""
    pci_id: str  # e.g., "0000:41:00.0"
    vendor_id: str  # e.g., "10de" for NVIDIA
    device_id: str  # e.g., "1eb8" for T4
    description: str  # e.g., "NVIDIA Tesla T4"
    iommu_group: Optional[int] = None
    driver: Optional[str] = None  # Current driver binding
    numa_node: Optional[int] = None


@dataclass
class IOMMUGroup:
    """Represents an IOMMU group containing PCI devices."""
    group_id: int
    devices: List[GPUDevice] = field(default_factory=list)


@dataclass
class ProxmoxConfig:
    """Proxmox VE configuration."""
    version: str = "8.2"
    enterprise_repo: bool = False
    root_password: Optional[str] = None
    storage_type: str = "local-lvm"
    network_bridge: str = "vmbr0"
    cluster_name: Optional[str] = None


@dataclass
class GPUPassthroughConfig:
    """GPU passthrough configuration."""
    enabled: bool = True
    auto_detect: bool = True
    iommu_type: IOMMUType = IOMMUType.INTEL
    blacklist_drivers: List[str] = field(
        default_factory=lambda: ["nouveau", "nvidia", "nvidiafb", "nvidia_drm"]
    )
    devices: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class TestVMConfig:
    """Test VM configuration for GPU passthrough validation."""
    enabled: bool = True
    name: str = "gpu-test-vm"
    memory_mb: int = 8192
    cores: int = 4
    disk_gb: int = 32
    machine_type: str = "q35"
    bios: str = "ovmf"
    os_type: str = "l26"
    network_bridge: str = "vmbr0"
    os_iso: Optional[str] = None


@dataclass
class TestVM:
    """Represents a created test VM."""
    vmid: int
    name: str
    status: str
    gpu_attached: bool = False
    gpu_device: Optional[GPUDevice] = None


@dataclass
class BuildConfiguration:
    """Complete build configuration."""
    credentials: Credentials
    instance_spec: InstanceSpec
    proxmox: ProxmoxConfig = field(default_factory=ProxmoxConfig)
    gpu_passthrough: GPUPassthroughConfig = field(default_factory=GPUPassthroughConfig)
    test_vm: TestVMConfig = field(default_factory=TestVMConfig)
    timeouts: Dict[str, int] = field(default_factory=lambda: {
        "instance_ready": 600,
        "ssh_connection": 300,
        "proxmox_install": 1200,
        "reboot_wait": 300,
        "gpu_setup": 600,
        "vm_creation": 300,
    })


@dataclass
class BuildState:
    """Represents the current state of a build."""
    build_id: UUID = field(default_factory=uuid4)
    status: BuildStatus = BuildStatus.PENDING
    instance: Optional[Instance] = None
    gpu_devices: List[GPUDevice] = field(default_factory=list)
    test_vm: Optional[TestVM] = None
    proxmox_url: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    logs: List[str] = field(default_factory=list)

    def add_log(self, message: str) -> None:
        """Add a timestamped log entry."""
        timestamp = datetime.utcnow().isoformat()
        self.logs.append(f"[{timestamp}] {message}")


@dataclass
class ExecutionResult:
    """Result of a remote command execution."""
    exit_code: int
    stdout: str
    stderr: str
    command: str
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        """Check if command succeeded."""
        return self.exit_code == 0
