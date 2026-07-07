"""
Tests for the build orchestrator.
"""

from unittest.mock import MagicMock, patch

import pytest

from proxmox_install_automation.exceptions import ConfigurationError
from proxmox_install_automation.models import BuildStatus
from proxmox_install_automation.orchestrator.builder import ProxmoxBuilder


class TestProxmoxBuilder:
    """Tests for the build orchestrator."""

    def test_validate_config_success(self, sample_build_config):
        """Test config validation with valid config."""
        builder = ProxmoxBuilder()
        assert builder.validate_config(sample_build_config) is True

    def test_validate_config_missing_auth_url(self, sample_build_config):
        """Test config validation fails without auth_url."""
        builder = ProxmoxBuilder()
        sample_build_config.credentials.auth_url = ""

        with pytest.raises(ConfigurationError, match="auth_url"):
            builder.validate_config(sample_build_config)

    def test_validate_config_missing_region(self, sample_build_config):
        """Test config validation fails without region."""
        builder = ProxmoxBuilder()
        sample_build_config.credentials.region = ""

        with pytest.raises(ConfigurationError, match="region"):
            builder.validate_config(sample_build_config)

    def test_validate_config_missing_credential_id(self, sample_build_config):
        """Test config validation fails without credential ID."""
        builder = ProxmoxBuilder()
        sample_build_config.credentials.application_credential_id = None

        with pytest.raises(ConfigurationError, match="credential_id"):
            builder.validate_config(sample_build_config)

    def test_validate_config_missing_key_name(self, sample_build_config):
        """Test config validation fails without SSH key name."""
        builder = ProxmoxBuilder()
        sample_build_config.instance_spec.ssh_key_name = ""

        with pytest.raises(ConfigurationError, match="ssh_key_name"):
            builder.validate_config(sample_build_config)

    @patch("proxmox_install_automation.orchestrator.builder.OpenStackAuthManager")
    @patch("proxmox_install_automation.orchestrator.builder.InstanceProvisioner")
    @patch("proxmox_install_automation.orchestrator.builder.SSHConnection")
    def test_run_auth_failure(
        self, mock_ssh, mock_provisioner, mock_auth, sample_build_config
    ):
        """Test that auth failure results in FAILED status."""
        from proxmox_install_automation.exceptions import AuthenticationError

        mock_auth_instance = MagicMock()
        mock_auth.return_value = mock_auth_instance
        mock_auth_instance.authenticate.side_effect = AuthenticationError("Bad credentials")

        builder = ProxmoxBuilder()
        state = builder.run(sample_build_config)

        assert state.status == BuildStatus.FAILED
        assert "Bad credentials" in state.error_message
