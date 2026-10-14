"""
Configuration validator for the local KVM/libvirt build and OPCP deploy path.

Validates a LocalBuildConfig instance (and, optionally, a DeployConfig) and
raises a single ConfigurationError listing all validation failures found.

Mirrors image_builder/config_validator.py: a single ``validate`` method that
collects every error and raises one aggregate exception.
"""

from typing import List, Optional

from proxmox_install_automation.exceptions import ConfigurationError

from .models import DeployConfig, LocalBuildConfig

# LocalBuildConfig fields that must be present and non-empty
REQUIRED_FIELDS = (
    "iso_source_path",
    "architecture",
    "libvirt_images_dir",
    "system_disk_name",
    "build_vm_name",
    "final_image_name",
    "output_dir",
)

# Allowed CPU architectures
VALID_ARCHITECTURES = {"x86_64", "amd64", "arm64"}

# Allowed first-boot scaffolding formats
VALID_FIRSTBOOT_FORMATS = {"cloud-init", "systemd", "ansible"}

# DeployConfig fields that must be present and non-empty when deploying
DEPLOY_REQUIRED_FIELDS = (
    "final_image_path",
    "glance_image_name",
    "ironic_node",
    "bare_metal_flavor",
    "network_name",
)


class LocalBuildConfigValidator:
    """Validates a LocalBuildConfig, collecting all errors into a single exception."""

    def validate(
        self,
        config: LocalBuildConfig,
        deploy_config: Optional[DeployConfig] = None,
    ) -> None:
        """Validate the given config(s).

        Args:
            config: The local build configuration to validate.
            deploy_config: Optional deploy configuration; validated when present.

        Raises:
            ConfigurationError: If one or more validation rules are violated.
                The error message lists all failures found.
        """
        errors: List[str] = []

        self._validate_local_build(config, errors)

        if deploy_config is not None:
            self._validate_deploy(deploy_config, errors)

        if errors:
            raise ConfigurationError(
                "Configuration validation failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

    def _validate_local_build(
        self, config: LocalBuildConfig, errors: List[str]
    ) -> None:
        """Collect validation errors for a LocalBuildConfig."""
        # Required fields present and non-empty
        for field_name in REQUIRED_FIELDS:
            value = getattr(config, field_name, None)
            if not value or (isinstance(value, str) and not value.strip()):
                errors.append(
                    f"Required field '{field_name}' is missing or empty"
                )

        # Architecture must be one of the supported values
        if config.architecture not in VALID_ARCHITECTURES:
            errors.append(
                f"architecture must be one of {sorted(VALID_ARCHITECTURES)} "
                f"(got: '{config.architecture}')"
            )

        # Positive numeric constraints
        if config.system_disk_size_gb <= 0:
            errors.append(
                "system_disk_size_gb must be a positive integer "
                f"(got: {config.system_disk_size_gb})"
            )
        if config.vcpus <= 0:
            errors.append(
                f"vcpus must be a positive integer (got: {config.vcpus})"
            )
        if config.ram_mib <= 0:
            errors.append(
                f"ram_mib must be a positive integer (got: {config.ram_mib})"
            )

        # Timeouts must be positive
        for timeout_field in ("build_timeout", "convert_timeout", "boot_test_timeout"):
            value = getattr(config, timeout_field)
            if value <= 0:
                errors.append(
                    f"{timeout_field} must be a positive integer (got: {value})"
                )

    def _validate_deploy(
        self, deploy_config: DeployConfig, errors: List[str]
    ) -> None:
        """Collect validation errors for a DeployConfig."""
        for field_name in DEPLOY_REQUIRED_FIELDS:
            value = getattr(deploy_config, field_name, None)
            if not value or (isinstance(value, str) and not value.strip()):
                errors.append(
                    f"Required deploy field '{field_name}' is missing or empty"
                )

        # First-boot format must be supported
        if deploy_config.firstboot_format not in VALID_FIRSTBOOT_FORMATS:
            errors.append(
                "firstboot_format must be one of "
                f"{sorted(VALID_FIRSTBOOT_FORMATS)} "
                f"(got: '{deploy_config.firstboot_format}')"
            )

        # Positive timeout constraints
        for timeout_field in ("glance_timeout", "deploy_timeout"):
            value = getattr(deploy_config, timeout_field)
            if value <= 0:
                errors.append(
                    f"{timeout_field} must be a positive integer (got: {value})"
                )

        # Credentials must carry an auth_url and region
        creds = deploy_config.credentials
        if not creds.auth_url or not creds.auth_url.strip():
            errors.append("deploy credentials: 'auth_url' is missing or empty")
        if not creds.region or not creds.region.strip():
            errors.append("deploy credentials: 'region' is missing or empty")
