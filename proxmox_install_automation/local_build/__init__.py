"""
Local KVM/libvirt build path for Proxmox VE qcow2 image creation and OPCP deploy.

This package adds a local-first build path alongside the existing remote
image_builder flow: prerequisites → ISO staging → system disk → build VM →
documented interactive install → cleaning → finalization → boot test →
Glance import → Ironic deploy → first-boot scaffolding.

Public exports are populated incrementally as components land.
"""

from .boot_tester import BOOT_MARKERS, BootTester
from .build_vm import BuildVMCreator
from .builder import LocalImageBuilder
from .command_runner import LocalCommandRunner
from .config_loader import load_local_build_config
from .config_validator import LocalBuildConfigValidator
from .image_cleaner import ImageCleaner
from .image_finalizer import ImageFinalizer
from .ironic_deployer import IronicDeployer
from .iso_stager import ISO_BY_ARCH, ISOStager
from .exceptions import (
    BootTestError,
    BuildVMError,
    FirstBootScaffoldError,
    GlanceImportError,
    ImageCleanError,
    ImageFinalizeError,
    IronicDeployError,
    ISOStagingError,
    LocalBuildError,
    LocalCommandError,
    PrerequisiteError,
    SystemDiskError,
)
from .firstboot_scaffolder import REQUIRED_TOPICS, FirstBootScaffolder
from .glance_importer import GlanceImporter
from .models import (
    CleaningOp,
    CleaningPlan,
    CommandResult,
    DeployConfig,
    DeployResult,
    ImageBuildArtifact,
    LocalBuildConfig,
    PrerequisiteReport,
)
from .prerequisites import (
    REQUIRED_PACKAGES,
    PrerequisiteChecker,
    compute_missing_packages,
    detect_os_family,
    parse_os_release,
)
from .system_disk import SystemDiskCreator

__all__ = [
    # Exceptions
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
    # Models
    "CleaningOp",
    "CleaningPlan",
    "CommandResult",
    "DeployConfig",
    "DeployResult",
    "ImageBuildArtifact",
    "LocalBuildConfig",
    "PrerequisiteReport",
    # Command runner
    "LocalCommandRunner",
    # ISO staging
    "ISO_BY_ARCH",
    "ISOStager",
    # Prerequisites (Req 2)
    "REQUIRED_PACKAGES",
    "PrerequisiteChecker",
    "compute_missing_packages",
    "detect_os_family",
    "parse_os_release",
    # Components
    "BOOT_MARKERS",
    "BootTester",
    "BuildVMCreator",
    "FirstBootScaffolder",
    "GlanceImporter",
    "ImageCleaner",
    "ImageFinalizer",
    "IronicDeployer",
    "REQUIRED_TOPICS",
    "SystemDiskCreator",
    # Orchestrator (Req 2-12)
    "LocalImageBuilder",
    # Config loading & validation (Req 2.5, 3.5, 14.3)
    "load_local_build_config",
    "LocalBuildConfigValidator",
]
