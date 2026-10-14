"""
YAML configuration loader for the local KVM/libvirt build and OPCP deploy path.

Reads a YAML file and constructs a LocalBuildConfig (always) and, when a
``deploy`` section is present, a DeployConfig reusing the shared Credentials
model from proxmox_install_automation.models.

Mirrors the conventions in image_builder/config_loader.py (env-var resolution,
section-based mapping, graceful parse errors).
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

from proxmox_install_automation.models import Credentials

from .exceptions import LocalBuildError
from .models import DeployConfig, LocalBuildConfig


def _resolve_env_vars(value: Any) -> Any:
    """Resolve environment variable references in config values."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        resolved = os.environ.get(env_var)
        if resolved is None:
            raise LocalBuildError(
                f"Environment variable '{env_var}' is not set"
            )
        return resolved
    return value


def _resolve_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively resolve environment variables in a dictionary."""
    resolved: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            resolved[key] = _resolve_dict(value)
        elif isinstance(value, list):
            resolved[key] = [_resolve_env_vars(item) for item in value]
        else:
            resolved[key] = _resolve_env_vars(value)
    return resolved


def load_local_build_config(
    path: str,
) -> Tuple[LocalBuildConfig, Optional[DeployConfig]]:
    """
    Load and parse local-build configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        A tuple ``(local_build_config, deploy_config)`` where ``deploy_config``
        is ``None`` when the YAML file contains no ``deploy`` section.

    Raises:
        LocalBuildError: If the file does not exist, is empty, or contains
            invalid YAML.
    """
    config_path = Path(path)

    if not config_path.exists():
        raise LocalBuildError(f"Configuration file not found: {path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise LocalBuildError(f"Failed to parse YAML configuration: {e}")

    if not raw_config:
        raise LocalBuildError("Configuration file is empty")

    config = _resolve_dict(raw_config)

    local_build_config = _build_local_build_config(config)
    deploy_config = _build_deploy_config(config)

    return local_build_config, deploy_config


def _build_local_build_config(config: Dict[str, Any]) -> LocalBuildConfig:
    """Build a LocalBuildConfig from a parsed config dictionary."""
    lb = config.get("local_build", {}) or {}

    defaults = LocalBuildConfig(iso_source_path="")

    return LocalBuildConfig(
        # ISO staging (Req 3)
        iso_source_path=lb.get("iso_source_path", ""),
        architecture=lb.get("architecture", defaults.architecture),
        libvirt_images_dir=lb.get(
            "libvirt_images_dir", defaults.libvirt_images_dir
        ),
        # System disk (Req 4)
        system_disk_size_gb=lb.get(
            "system_disk_size_gb", defaults.system_disk_size_gb
        ),
        system_disk_name=lb.get("system_disk_name", defaults.system_disk_name),
        # Build VM (Req 5)
        build_vm_name=lb.get("build_vm_name", defaults.build_vm_name),
        vcpus=lb.get("vcpus", defaults.vcpus),
        ram_mib=lb.get("ram_mib", defaults.ram_mib),
        cpu_mode=lb.get("cpu_mode", defaults.cpu_mode),
        network_model=lb.get("network_model", defaults.network_model),
        disk_bus=lb.get("disk_bus", defaults.disk_bus),
        # Finalization (Req 8)
        final_image_name=lb.get("final_image_name", defaults.final_image_name),
        output_dir=lb.get("output_dir", defaults.output_dir),
        # Timeouts
        build_timeout=lb.get("build_timeout", defaults.build_timeout),
        convert_timeout=lb.get("convert_timeout", defaults.convert_timeout),
        boot_test_timeout=lb.get(
            "boot_test_timeout", defaults.boot_test_timeout
        ),
        # Interactive gate (Req 6)
        assume_install_complete=lb.get(
            "assume_install_complete", defaults.assume_install_complete
        ),
    )


def _build_deploy_config(config: Dict[str, Any]) -> Optional[DeployConfig]:
    """Build a DeployConfig when a ``deploy`` section is present, else None."""
    deploy = config.get("deploy")
    if not deploy:
        return None

    os_config = config.get("openstack", {}) or {}
    credentials = Credentials(
        auth_url=os_config.get("auth_url", ""),
        region=os_config.get("region", ""),
        auth_type=os_config.get("auth_type", "v3applicationcredential"),
        application_credential_id=os_config.get("application_credential_id"),
        application_credential_secret=os_config.get(
            "application_credential_secret"
        ),
        username=os_config.get("username"),
        password=os_config.get("password"),
        project_name=os_config.get("project_name"),
        user_domain_name=os_config.get("user_domain_name", "Default"),
        project_domain_name=os_config.get("project_domain_name", "Default"),
        identity_api_version=os_config.get("identity_api_version", "3"),
        interface=os_config.get("interface", "public"),
    )

    defaults = DeployConfig(
        final_image_path="",
        glance_image_name="",
        credentials=credentials,
        ironic_node="",
        bare_metal_flavor="",
    )

    return DeployConfig(
        final_image_path=deploy.get("final_image_path", ""),
        glance_image_name=deploy.get("glance_image_name", ""),
        credentials=credentials,
        ironic_node=deploy.get("ironic_node", ""),
        bare_metal_flavor=deploy.get("bare_metal_flavor", ""),
        network_name=deploy.get("network_name", defaults.network_name),
        glance_timeout=deploy.get("glance_timeout", defaults.glance_timeout),
        deploy_timeout=deploy.get("deploy_timeout", defaults.deploy_timeout),
        firstboot_format=deploy.get(
            "firstboot_format", defaults.firstboot_format
        ),
        firstboot_output_dir=deploy.get(
            "firstboot_output_dir", defaults.firstboot_output_dir
        ),
    )
