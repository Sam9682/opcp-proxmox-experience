"""
Image Builder module for Proxmox qcow2 image creation on OpenStack.

This module orchestrates the pipeline: authenticate → create instance →
download ISO → convert to qcow2 → snapshot → upload to Glance → cleanup.
"""

from .auth import ImageBuildAuthManager
from .builder import ImageBuilder
from .cleanup import ImageBuildCleanupManager
from .config_loader import load_image_build_config
from .config_validator import ImageBuildConfigValidator
from .glance_uploader import GlanceUploader
from .instance import ImageBuildInstanceManager
from .models import (
    CleanupReport,
    CleanupResource,
    ImageBuildConfig,
    ImageBuildResult,
    ImageMetadata,
)
from .snapshot import SnapshotManager, generate_snapshot_name

__all__ = [
    "CleanupReport",
    "CleanupResource",
    "GlanceUploader",
    "ImageBuildAuthManager",
    "ImageBuildCleanupManager",
    "ImageBuildConfig",
    "ImageBuildConfigValidator",
    "ImageBuilder",
    "ImageBuildInstanceManager",
    "ImageBuildResult",
    "ImageMetadata",
    "SnapshotManager",
    "generate_snapshot_name",
    "load_image_build_config",
]
