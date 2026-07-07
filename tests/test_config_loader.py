"""
Tests for configuration loading.
"""

import os
import tempfile

import pytest
import yaml

from proxmox_install_automation.config_loader import load_config
from proxmox_install_automation.exceptions import ConfigurationError
from proxmox_install_automation.models import IOMMUType


class TestConfigLoader:
    """Tests for the config loader."""

    def _write_config(self, config_dict, tmpdir):
        """Helper to write config to a temp file."""
        path = os.path.join(tmpdir, "config.yaml")
        with open(path, "w") as f:
            yaml.dump(config_dict, f)
        return path

    def test_load_valid_config(self, tmp_path):
        """Test loading a valid configuration."""
        config = {
            "openstack": {
                "auth_url": "https://auth.cloud.ovh.net/v3",
                "region": "GRA7",
                "auth_type": "v3applicationcredential",
                "application_credential_id": "test-id",
                "application_credential_secret": "test-secret",
            },
            "instance": {
                "base_image_name": "Debian 12",
                "flavor_name": "b3-8",
                "ssh_username": "debian",
                "ssh_key_name": "my-key",
                "ssh_key_path": "~/.ssh/id_rsa",
            },
            "proxmox": {
                "version": "8.2",
                "enterprise_repo": False,
            },
            "gpu_passthrough": {
                "enabled": True,
                "iommu_type": "intel",
            },
            "test_vm": {
                "enabled": True,
                "name": "test-vm",
                "memory_mb": 4096,
            },
        }

        path = self._write_config(config, str(tmp_path))
        result = load_config(path)

        assert result.credentials.auth_url == "https://auth.cloud.ovh.net/v3"
        assert result.credentials.region == "GRA7"
        assert result.instance_spec.flavor_name == "b3-8"
        assert result.proxmox.version == "8.2"
        assert result.gpu_passthrough.enabled is True
        assert result.gpu_passthrough.iommu_type == IOMMUType.INTEL
        assert result.test_vm.name == "test-vm"
        assert result.test_vm.memory_mb == 4096

    def test_load_missing_file(self):
        """Test loading a non-existent file raises error."""
        with pytest.raises(ConfigurationError, match="not found"):
            load_config("/nonexistent/path/config.yaml")

    def test_load_empty_file(self, tmp_path):
        """Test loading an empty file raises error."""
        path = os.path.join(str(tmp_path), "empty.yaml")
        with open(path, "w") as f:
            f.write("")

        with pytest.raises(ConfigurationError, match="empty"):
            load_config(path)

    def test_load_invalid_yaml(self, tmp_path):
        """Test loading invalid YAML raises error."""
        path = os.path.join(str(tmp_path), "invalid.yaml")
        with open(path, "w") as f:
            f.write("invalid: yaml: content: [")

        with pytest.raises(ConfigurationError, match="parse"):
            load_config(path)

    def test_env_var_resolution(self, tmp_path, monkeypatch):
        """Test environment variable resolution."""
        monkeypatch.setenv("TEST_AUTH_URL", "https://test.example.com/v3")
        monkeypatch.setenv("TEST_REGION", "SBG5")

        config = {
            "openstack": {
                "auth_url": "${TEST_AUTH_URL}",
                "region": "${TEST_REGION}",
                "auth_type": "v3applicationcredential",
                "application_credential_id": "id",
                "application_credential_secret": "secret",
            },
            "instance": {
                "base_image_name": "Debian 12",
                "flavor_name": "b3-8",
                "ssh_username": "debian",
                "ssh_key_name": "key",
            },
        }

        path = self._write_config(config, str(tmp_path))
        result = load_config(path)

        assert result.credentials.auth_url == "https://test.example.com/v3"
        assert result.credentials.region == "SBG5"

    def test_env_var_missing(self, tmp_path):
        """Test missing environment variable raises error."""
        config = {
            "openstack": {
                "auth_url": "${NONEXISTENT_VAR_12345}",
                "region": "GRA7",
            },
        }

        path = self._write_config(config, str(tmp_path))
        with pytest.raises(ConfigurationError, match="NONEXISTENT_VAR_12345"):
            load_config(path)

    def test_default_values(self, tmp_path):
        """Test that defaults are applied for missing values."""
        config = {
            "openstack": {
                "auth_url": "https://auth.example.com/v3",
                "region": "GRA7",
            },
        }

        path = self._write_config(config, str(tmp_path))
        result = load_config(path)

        # Check defaults
        assert result.instance_spec.base_image_name == "Debian 12"
        assert result.instance_spec.flavor_name == "b3-8"
        assert result.proxmox.version == "8.2"
        assert result.gpu_passthrough.enabled is True
        assert result.test_vm.machine_type == "q35"
        assert result.timeouts["instance_ready"] == 600
