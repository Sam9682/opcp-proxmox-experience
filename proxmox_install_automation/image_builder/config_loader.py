"""
YAML configuration loader for the image build pipeline.
"""

import os
from pathlib import Path
from typing import Any, Dict

import yaml

from proxmox_install_automation.exceptions import ConfigurationError
from proxmox_install_automation.models import Credentials

from .models import ImageBuildConfig


def _resolve_env_vars(value: Any) -> Any:
    """Resolve environment variable references in config values."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        resolved = os.environ.get(env_var)
        if resolved is None:
            raise ConfigurationError(
                f"Environment variable '{env_var}' is not set"
            )
        return resolved
    return value


def _resolve_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively resolve environment variables in a dictionary."""
    resolved = {}
    for key, value in data.items():
        if isinstance(value, dict):
            resolved[key] = _resolve_dict(value)
        elif isinstance(value, list):
            resolved[key] = [_resolve_env_vars(item) for item in value]
        else:
            resolved[key] = _resolve_env_vars(value)
    return resolved


def load_image_build_config(path: str) -> ImageBuildConfig:
    """
    Load and parse image build configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        ImageBuildConfig object populated from the YAML contents.

    Raises:
        ConfigurationError: If the file does not exist or contains invalid YAML.
    """
    config_path = Path(path)

    if not config_path.exists():
        raise ConfigurationError(
            f"Configuration file not found: {path}"
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigurationError(
            f"Failed to parse YAML configuration: {e}"
        )

    if not raw_config:
        raise ConfigurationError("Configuration file is empty")

    # Resolve environment variables
    config = _resolve_dict(raw_config)

    return _build_image_build_config(config)


def _build_image_build_config(config: Dict[str, Any]) -> ImageBuildConfig:
    """Build an ImageBuildConfig from a parsed config dictionary."""

    # Parse image_build section
    image_build = config.get("image_build", {})

    # Parse openstack section into Credentials
    os_config = config.get("openstack", {})
    credentials = Credentials(
        auth_url=os_config.get("auth_url", ""),
        region=os_config.get("region", ""),
        auth_type=os_config.get("auth_type", "v3applicationcredential"),
        application_credential_id=os_config.get("application_credential_id"),
        application_credential_secret=os_config.get("application_credential_secret"),
        username=os_config.get("username"),
        password=os_config.get("password"),
        project_name=os_config.get("project_name"),
        user_domain_name=os_config.get("user_domain_name", "Default"),
        project_domain_name=os_config.get("project_domain_name", "Default"),
        identity_api_version=os_config.get("identity_api_version", "3"),
        interface=os_config.get("interface", "public"),
    )

    # Parse instance section
    instance_config = config.get("instance", {})

    return ImageBuildConfig(
        # Required fields from image_build section
        iso_url=image_build.get("iso_url", ""),
        base_image_name=image_build.get("base_image_name", ""),
        flavor_name=image_build.get("flavor_name", ""),
        target_image_name=image_build.get("target_image_name", ""),
        # Authentication
        credentials=credentials,
        # Instance config
        ssh_key_name=instance_config.get("ssh_key_name", ""),
        ssh_key_path=instance_config.get("ssh_key_path", ""),
        network_name=instance_config.get("network_name", "Ext-Net"),
        # Optional fields from image_build section
        proxmox_version=image_build.get("proxmox_version", "8.2"),
        target_visibility=image_build.get("target_visibility", "private"),
        build_timeout=image_build.get("build_timeout", 1800),
        iso_expected_size=image_build.get("iso_expected_size"),
        iso_download_dir=image_build.get("iso_download_dir", "/tmp"),
        iso_download_timeout=image_build.get("iso_download_timeout", 1800),
        conversion_timeout=image_build.get("conversion_timeout", 600),
        snapshot_timeout=image_build.get("snapshot_timeout", 1800),
    )
