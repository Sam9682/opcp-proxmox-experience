"""
Abstract interfaces for Proxmox Install Automation components.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import (
    BuildConfiguration,
    BuildState,
    Credentials,
    ExecutionResult,
    GPUDevice,
    Instance,
    InstanceSpec,
    TestVM,
    TestVMConfig,
)


class AuthenticationManager(ABC):
    """Interface for OpenStack authentication."""

    @abstractmethod
    def authenticate(self, credentials: Credentials) -> object:
        """Authenticate and return an OpenStack connection."""
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        """Validate the current connection is active."""
        pass


class InstanceProvisioner(ABC):
    """Interface for baremetal instance provisioning."""

    @abstractmethod
    def create_instance(self, spec: InstanceSpec) -> Instance:
        """Create a baremetal instance."""
        pass

    @abstractmethod
    def wait_for_ready(self, instance: Instance, timeout: int) -> bool:
        """Wait for instance to be ready."""
        pass

    @abstractmethod
    def get_instance_ip(self, instance: Instance) -> str:
        """Get the accessible IP address of the instance."""
        pass

    @abstractmethod
    def destroy_instance(self, instance: Instance) -> bool:
        """Destroy the instance."""
        pass


class SSHManager(ABC):
    """Interface for SSH connection management."""

    @abstractmethod
    def connect(self, host: str, username: str, key_path: str, timeout: int) -> None:
        """Establish SSH connection."""
        pass

    @abstractmethod
    def execute(self, command: str, timeout: int = 600) -> ExecutionResult:
        """Execute a command over SSH."""
        pass

    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """Upload a file via SFTP."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close SSH connection."""
        pass


class ProxmoxInstaller(ABC):
    """Interface for Proxmox VE installation."""

    @abstractmethod
    def install(self, ssh: SSHManager) -> bool:
        """Install Proxmox VE packages."""
        pass

    @abstractmethod
    def configure_network(self, ssh: SSHManager, bridge_name: str) -> bool:
        """Configure network bridges."""
        pass

    @abstractmethod
    def configure_storage(self, ssh: SSHManager, storage_type: str) -> bool:
        """Configure storage backend."""
        pass

    @abstractmethod
    def verify_installation(self, ssh: SSHManager) -> bool:
        """Verify Proxmox is installed and running."""
        pass


class GPUManager(ABC):
    """Interface for GPU detection and passthrough configuration."""

    @abstractmethod
    def detect_gpus(self, ssh: SSHManager) -> List[GPUDevice]:
        """Detect available GPU devices."""
        pass

    @abstractmethod
    def configure_iommu(self, ssh: SSHManager, iommu_type: str) -> bool:
        """Configure IOMMU kernel parameters."""
        pass

    @abstractmethod
    def bind_vfio(self, ssh: SSHManager, devices: List[GPUDevice]) -> bool:
        """Bind GPU devices to VFIO driver."""
        pass

    @abstractmethod
    def verify_passthrough(self, ssh: SSHManager, devices: List[GPUDevice]) -> bool:
        """Verify GPU passthrough is correctly configured."""
        pass


class VMManager(ABC):
    """Interface for test VM management."""

    @abstractmethod
    def create_vm(
        self, ssh: SSHManager, config: TestVMConfig, gpu: Optional[GPUDevice] = None
    ) -> TestVM:
        """Create a test VM with optional GPU passthrough."""
        pass

    @abstractmethod
    def start_vm(self, ssh: SSHManager, vmid: int) -> bool:
        """Start a VM."""
        pass

    @abstractmethod
    def validate_gpu_in_vm(self, ssh: SSHManager, vmid: int) -> bool:
        """Validate GPU is accessible inside the VM."""
        pass

    @abstractmethod
    def destroy_vm(self, ssh: SSHManager, vmid: int) -> bool:
        """Destroy a VM."""
        pass


class BuildOrchestrator(ABC):
    """Interface for the overall build orchestration."""

    @abstractmethod
    def run(self, config: BuildConfiguration) -> BuildState:
        """Run the complete installation workflow."""
        pass

    @abstractmethod
    def validate_config(self, config: BuildConfiguration) -> bool:
        """Validate build configuration."""
        pass

    @abstractmethod
    def cleanup(self, state: BuildState) -> bool:
        """Clean up all resources."""
        pass
