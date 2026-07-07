"""
Custom exceptions for Proxmox Install Automation.
"""


class ProxmoxAutomationError(Exception):
    """Base exception for all automation errors."""
    pass


class AuthenticationError(ProxmoxAutomationError):
    """Raised when OpenStack authentication fails."""
    pass


class InstanceCreationError(ProxmoxAutomationError):
    """Raised when baremetal instance creation fails."""
    pass


class InstanceError(ProxmoxAutomationError):
    """Raised when instance enters an error state."""
    pass


class SSHConnectionError(ProxmoxAutomationError):
    """Raised when SSH connection cannot be established."""
    pass


class SSHCommandError(ProxmoxAutomationError):
    """Raised when a remote command execution fails."""
    pass


class ProxmoxInstallError(ProxmoxAutomationError):
    """Raised when Proxmox VE installation fails."""
    pass


class NetworkConfigError(ProxmoxAutomationError):
    """Raised when network configuration fails."""
    pass


class GPUDetectionError(ProxmoxAutomationError):
    """Raised when GPU detection fails."""
    pass


class IOMMUConfigError(ProxmoxAutomationError):
    """Raised when IOMMU configuration fails."""
    pass


class VFIOBindError(ProxmoxAutomationError):
    """Raised when VFIO driver binding fails."""
    pass


class GPUPassthroughError(ProxmoxAutomationError):
    """Raised when GPU passthrough configuration fails."""
    pass


class VMCreationError(ProxmoxAutomationError):
    """Raised when test VM creation fails."""
    pass


class ValidationError(ProxmoxAutomationError):
    """Raised when validation fails."""
    pass


class ConfigurationError(ProxmoxAutomationError):
    """Raised when configuration is invalid."""
    pass


class CleanupError(ProxmoxAutomationError):
    """Raised when cleanup fails."""
    pass


class TimeoutError(ProxmoxAutomationError):
    """Raised when an operation times out."""
    pass


class BuildError(ProxmoxAutomationError):
    """Raised when the overall build process fails."""
    pass
