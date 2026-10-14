"""
Custom exceptions for the local KVM/libvirt build and OPCP deploy path.

All exceptions extend ProxmoxAutomationError from the parent module,
mirroring the convention in image_builder/exceptions.py.
"""

from proxmox_install_automation.exceptions import ProxmoxAutomationError


class LocalBuildError(ProxmoxAutomationError):
    """Raised when the local build pipeline fails overall."""

    pass


class LocalCommandError(ProxmoxAutomationError):
    """Raised when a local subprocess command exits non-zero or times out."""

    pass


class PrerequisiteError(ProxmoxAutomationError):
    """Raised when build-host prerequisites are not satisfied."""

    pass


class ISOStagingError(ProxmoxAutomationError):
    """Raised when staging the installer ISO fails."""

    pass


class SystemDiskError(ProxmoxAutomationError):
    """Raised when the system disk cannot be created."""

    pass


class BuildVMError(ProxmoxAutomationError):
    """Raised when the transient build VM cannot be created."""

    pass


class ImageCleanError(ProxmoxAutomationError):
    """Raised when guest-image cleaning (generic-ization) fails."""

    pass


class ImageFinalizeError(ProxmoxAutomationError):
    """Raised when image finalization or validation fails."""

    pass


class BootTestError(ProxmoxAutomationError):
    """Raised when the final image fails the import boot test."""

    pass


class GlanceImportError(ProxmoxAutomationError):
    """Raised when importing the image into Glance fails."""

    pass


class IronicDeployError(ProxmoxAutomationError):
    """Raised when the Ironic bare-metal deploy fails."""

    pass


class FirstBootScaffoldError(ProxmoxAutomationError):
    """Raised when first-boot scaffolding generation fails."""

    pass


__all__ = [
    "BootTestError",
    "BuildVMError",
    "FirstBootScaffoldError",
    "GlanceImportError",
    "ISOStagingError",
    "ImageCleanError",
    "ImageFinalizeError",
    "IronicDeployError",
    "LocalBuildError",
    "LocalCommandError",
    "PrerequisiteError",
    "SystemDiskError",
]
