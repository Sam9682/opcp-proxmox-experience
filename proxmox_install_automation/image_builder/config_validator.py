"""
Configuration validator for the image build pipeline.

Validates an ImageBuildConfig instance and raises a single ConfigurationError
listing all validation failures found.
"""

from typing import List

from proxmox_install_automation.image_builder.exceptions import ConfigurationError
from proxmox_install_automation.image_builder.models import ImageBuildConfig

# Fields that must be present and non-empty
REQUIRED_FIELDS = ("iso_url", "base_image_name", "flavor_name", "target_image_name")

# Allowed values for target_visibility
VALID_VISIBILITIES = {"private", "shared", "public"}

# Build timeout bounds (inclusive)
MIN_BUILD_TIMEOUT = 60
MAX_BUILD_TIMEOUT = 7200


class ImageBuildConfigValidator:
    """Validates an ImageBuildConfig, collecting all errors into a single exception."""

    def validate(self, config: ImageBuildConfig) -> None:
        """Validate the given config.

        Raises:
            ConfigurationError: If one or more validation rules are violated.
                The error message lists all failures found.
        """
        errors: List[str] = []

        # Check required fields are present and non-empty
        for field_name in REQUIRED_FIELDS:
            value = getattr(config, field_name, None)
            if not value or (isinstance(value, str) and not value.strip()):
                errors.append(f"Required field '{field_name}' is missing or empty")

        # Validate iso_url uses HTTPS
        if config.iso_url and config.iso_url.strip():
            if not config.iso_url.startswith("https://"):
                errors.append(
                    "iso_url must start with 'https://' "
                    f"(got: '{config.iso_url}')"
                )

        # Validate target_visibility
        if config.target_visibility not in VALID_VISIBILITIES:
            errors.append(
                f"target_visibility must be one of {sorted(VALID_VISIBILITIES)} "
                f"(got: '{config.target_visibility}')"
            )

        # Validate build_timeout range
        if not (MIN_BUILD_TIMEOUT <= config.build_timeout <= MAX_BUILD_TIMEOUT):
            errors.append(
                f"build_timeout must be between {MIN_BUILD_TIMEOUT} and "
                f"{MAX_BUILD_TIMEOUT} seconds inclusive "
                f"(got: {config.build_timeout})"
            )

        if errors:
            raise ConfigurationError(
                "Configuration validation failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )
