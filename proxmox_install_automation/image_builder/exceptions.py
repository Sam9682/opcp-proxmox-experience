"""
Custom exceptions for the image builder pipeline.

All exceptions extend ProxmoxAutomationError from the parent module.
ConfigurationError and AuthenticationError are re-exported for convenience.
"""

from proxmox_install_automation.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ProxmoxAutomationError,
)


class ImageBuildError(ProxmoxAutomationError):
    """Raised when the image build pipeline fails."""

    pass


class ISODownloadError(ProxmoxAutomationError):
    """Raised when ISO download fails after retries."""

    pass


class ISOConversionError(ProxmoxAutomationError):
    """Raised when qemu-img conversion fails."""

    pass


class SnapshotError(ProxmoxAutomationError):
    """Raised when snapshot creation/wait fails."""

    pass


class GlanceUploadError(ProxmoxAutomationError):
    """Raised when Glance upload fails after retries."""

    pass


__all__ = [
    "AuthenticationError",
    "ConfigurationError",
    "GlanceUploadError",
    "ISOConversionError",
    "ISODownloadError",
    "ImageBuildError",
    "SnapshotError",
]
