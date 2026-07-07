"""
Configuration loader for Proxmox Install Automation.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .exceptions import ConfigurationError
from .models import (
    BuildConfiguration,
    Credentials,
    GPUPassthroughConfig,
    IOMMUType,
    InstanceSpec,
    ProxmoxConfig,
    TestVMConfig,
)


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


def load_config(config_path: str) -> BuildConfiguration:
    """
    Load and parse configuration from a YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        BuildConfiguration object.

    Raises:
        ConfigurationError: If the config file is invalid or missing.
    """
    path = Path(config_path)
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Failed to parse YAML config: {e}")

    if not raw_config:
        raise ConfigurationError("Configuration file is empty")

    # Resolve environment variables
    config = _resolve_dict(raw_config)

    return _build_configuration(config)


def _build_configuration(config: Dict[str, Any]) -> BuildConfiguration:
    """Build a BuildConfiguration from a parsed config dictionary."""

    # Parse OpenStack credentials
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

    # Parse instance spec
    inst_config = config.get("instance", {})
    net_config = config.get("networking", {})
    instance_spec = InstanceSpec(
        base_image_name=inst_config.get("base_image_name", "Debian 12"),
        flavor_name=inst_config.get("flavor_name", "b3-8"),
        ssh_username=inst_config.get("ssh_username", "debian"),
        ssh_key_name=inst_config.get("ssh_key_name", ""),
        ssh_key_path=inst_config.get("ssh_key_path", "~/.ssh/id_rsa"),
        network_name=net_config.get("network_name", "Ext-Net"),
        security_groups=net_config.get("security_groups", ["default"]),
        availability_zone=inst_config.get("availability_zone"),
        use_floating_ip=net_config.get("use_floating_ip", True),
        floating_ip_pool=net_config.get("floating_ip_pool"),
    )

    # Parse Proxmox config
    pve_config = config.get("proxmox", {})
    proxmox = ProxmoxConfig(
        version=pve_config.get("version", "8.2"),
        enterprise_repo=pve_config.get("enterprise_repo", False),
        root_password=pve_config.get("root_password"),
        storage_type=pve_config.get("storage_type", "local-lvm"),
        network_bridge=pve_config.get("network_bridge", "vmbr0"),
        cluster_name=pve_config.get("cluster_name"),
    )

    # Parse GPU passthrough config
    gpu_config = config.get("gpu_passthrough", {})
    iommu_type_str = gpu_config.get("iommu_type", "intel")
    try:
        iommu_type = IOMMUType(iommu_type_str)
    except ValueError:
        iommu_type = IOMMUType.INTEL

    gpu_passthrough = GPUPassthroughConfig(
        enabled=gpu_config.get("enabled", True),
        auto_detect=gpu_config.get("auto_detect", True),
        iommu_type=iommu_type,
        blacklist_drivers=gpu_config.get(
            "blacklist_drivers", ["nouveau", "nvidia", "nvidiafb", "nvidia_drm"]
        ),
        devices=gpu_config.get("devices", []),
    )

    # Parse test VM config
    vm_config = config.get("test_vm", {})
    test_vm = TestVMConfig(
        enabled=vm_config.get("enabled", True),
        name=vm_config.get("name", "gpu-test-vm"),
        memory_mb=vm_config.get("memory_mb", 8192),
        cores=vm_config.get("cores", 4),
        disk_gb=vm_config.get("disk_gb", 32),
        machine_type=vm_config.get("machine_type", "q35"),
        bios=vm_config.get("bios", "ovmf"),
        os_type=vm_config.get("os_type", "l26"),
        network_bridge=vm_config.get("network_bridge", "vmbr0"),
        os_iso=vm_config.get("os_iso"),
    )

    # Parse timeouts
    timeouts = config.get("timeouts", {})

    return BuildConfiguration(
        credentials=credentials,
        instance_spec=instance_spec,
        proxmox=proxmox,
        gpu_passthrough=gpu_passthrough,
        test_vm=test_vm,
        timeouts={
            "instance_ready": timeouts.get("instance_ready", 600),
            "ssh_connection": timeouts.get("ssh_connection", 300),
            "proxmox_install": timeouts.get("proxmox_install", 1200),
            "reboot_wait": timeouts.get("reboot_wait", 300),
            "gpu_setup": timeouts.get("gpu_setup", 600),
            "vm_creation": timeouts.get("vm_creation", 300),
        },
    )
