"""
Data models for the Proxmox qcow2 image building pipeline.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from proxmox_install_automation.models import Credentials


@dataclass
class ImageBuildConfig:
    """Configuration for the qcow2 image build pipeline."""

    # Required fields
    iso_url: str
    base_image_name: str
    flavor_name: str
    target_image_name: str

    # Authentication (reuses existing Credentials)
    credentials: Credentials

    # Instance config
    ssh_key_name: str
    ssh_key_path: str
    network_name: str = "Ext-Net"

    # Optional fields with defaults
    proxmox_version: str = "8.2"
    target_visibility: str = "private"
    build_timeout: int = 1800
    iso_expected_size: Optional[int] = None
    iso_download_dir: str = "/tmp"
    iso_download_timeout: int = 1800
    conversion_timeout: int = 600
    snapshot_timeout: int = 1800


@dataclass
class ImageBuildResult:
    """Result of a successful image build."""

    image_id: str
    image_name: str
    build_duration_seconds: float
    snapshot_id: Optional[str] = None


@dataclass
class ImageMetadata:
    """Metadata attached to the Glance image."""

    name: str
    disk_format: str = "qcow2"
    container_format: str = "bare"
    proxmox_version: str = ""
    build_timestamp: str = ""  # ISO 8601
    visibility: str = "private"


@dataclass
class CleanupResource:
    """A resource to be cleaned up after the build."""

    resource_type: str  # "snapshot" | "instance" | "floating_ip"
    resource_id: str
    resource_name: Optional[str] = None


@dataclass
class CleanupReport:
    """Report of cleanup operations."""

    total: int
    succeeded: int
    failed: int
    failures: List[str] = field(default_factory=list)
