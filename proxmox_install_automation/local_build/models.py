"""
Data models for the local KVM/libvirt Proxmox VE build and OPCP deploy path.

Mirrors the dataclass conventions of image_builder/models.py and reuses the
shared Credentials model from proxmox_install_automation.models.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from proxmox_install_automation.models import Credentials


@dataclass
class LocalBuildConfig:
    """Configuration for the local KVM/libvirt build path."""

    # ISO staging (Req 3)
    iso_source_path: str
    architecture: str = "x86_64"          # x86_64 | amd64 | arm64
    libvirt_images_dir: str = "/var/lib/libvirt/images"

    # System disk (Req 4)
    system_disk_size_gb: int = 64
    system_disk_name: str = "proxmox-image-builder.qcow2"

    # Build VM (Req 5)
    build_vm_name: str = "proxmox-image-builder"
    vcpus: int = 8
    ram_mib: int = 16384                  # 16 GB
    cpu_mode: str = "host-passthrough"
    network_model: str = "virtio"
    disk_bus: str = "virtio"

    # Finalization (Req 8)
    final_image_name: str = "proxmox-opcp-final.qcow2"
    output_dir: str = "/var/lib/libvirt/images"

    # Timeouts
    build_timeout: int = 3600
    convert_timeout: int = 1800
    boot_test_timeout: int = 600

    # Interactive gate (Req 6)
    assume_install_complete: bool = False  # skip the operator pause


@dataclass
class DeployConfig:
    """Configuration for Glance import + Ironic deploy + first-boot (Req 10-12)."""

    final_image_path: str
    glance_image_name: str
    credentials: Credentials               # reuses proxmox_install_automation.models
    ironic_node: str
    bare_metal_flavor: str
    network_name: str = "Ext-Net"
    glance_timeout: int = 1800
    deploy_timeout: int = 3600
    firstboot_format: str = "cloud-init"   # cloud-init | systemd | ansible
    firstboot_output_dir: str = "./firstboot"


@dataclass
class ImageBuildArtifact:
    """Result of a successful local image build."""

    final_image_path: str
    virtual_size_bytes: int
    actual_size_bytes: int
    build_duration_seconds: float
    boot_test_passed: bool


@dataclass
class DeployResult:
    """Result of a successful Glance import + Ironic deploy."""

    glance_image_id: str
    server_id: str
    ironic_node: str
    firstboot_artifacts: List[str] = field(default_factory=list)
    deploy_duration_seconds: float = 0.0


@dataclass
class PrerequisiteReport:
    """Aggregate result of the prerequisite checks (Req 2)."""

    os_supported: bool
    missing_packages: List[str]
    kvm_available: bool
    uefi_available: bool

    @property
    def ok(self) -> bool:
        """True iff every prerequisite is satisfied."""
        return (
            self.os_supported
            and not self.missing_packages
            and self.kvm_available
            and self.uefi_available
        )


@dataclass
class CleaningOp:
    """A single declarative guest-image cleaning operation (Req 7).

    Operations are ordered within a CleaningPlan and applied via libguestfs.
    `action` names the kind of operation (e.g. "write-file", "set-hostname",
    "run-command", "delete") and `params` carries the operation-specific
    arguments. `description` documents the requirement the op satisfies.
    """

    action: str
    params: Dict[str, str] = field(default_factory=dict)
    description: str = ""


@dataclass
class CleaningPlan:
    """An ordered, declarative set of generic-ization cleaning operations."""

    operations: List[CleaningOp] = field(default_factory=list)


@dataclass
class CommandResult:
    """Result of a local subprocess command execution."""

    argv: List[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        """Check if the command succeeded."""
        return self.exit_code == 0
