"""
Proxmox VE Installation Automation on OVH Baremetal OpenStack

This package automates the deployment of Proxmox VE on OVH OpenStack baremetal
instances, with GPU PCI passthrough support for running GPU-accelerated VMs.

Key features:
- Automated Proxmox VE installation on Debian-based baremetal
- IOMMU/VT-d configuration for PCI passthrough
- GPU device detection and VFIO driver binding
- Test VM creation with GPU passthrough validation
"""

__version__ = "0.1.0"
__author__ = "OPCP Automation Team"

from .models import (
    Credentials,
    BuildConfiguration,
    BuildState,
    BuildStatus,
    GPUDevice,
    ProxmoxConfig,
)

__all__ = [
    "Credentials",
    "BuildConfiguration",
    "BuildState",
    "BuildStatus",
    "GPUDevice",
    "ProxmoxConfig",
]
