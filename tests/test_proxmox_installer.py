"""
Tests for the Proxmox installer.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from proxmox_install_automation.models import ExecutionResult, ProxmoxConfig
from proxmox_install_automation.proxmox.installer import ProxmoxInstaller


class TestProxmoxInstaller:
    """Tests for Proxmox VE installation."""

    def test_install_success(self):
        """Test successful Proxmox installation."""
        config = ProxmoxConfig(
            version="8.2",
            enterprise_repo=False,
            root_password="test123",
        )
        installer = ProxmoxInstaller(config)
        ssh = MagicMock()

        # Mock all SSH commands to succeed
        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=0, stdout="192.168.1.10", stderr="", command=""
        )

        result = installer.install(ssh)
        assert result is True

    def test_install_uses_no_subscription_repo(self):
        """Test that non-enterprise repo is used when configured."""
        config = ProxmoxConfig(enterprise_repo=False)
        installer = ProxmoxInstaller(config)
        ssh = MagicMock()

        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=0, stdout="10.0.0.1", stderr="", command=""
        )

        installer.install(ssh)

        # Check that pve-no-subscription repo was used
        calls = [str(c) for c in ssh.execute_sudo.call_args_list]
        assert any("pve-no-subscription" in c for c in calls)

    def test_install_uses_enterprise_repo(self):
        """Test that enterprise repo is used when configured."""
        config = ProxmoxConfig(enterprise_repo=True)
        installer = ProxmoxInstaller(config)
        ssh = MagicMock()

        ssh.execute_sudo.return_value = ExecutionResult(
            exit_code=0, stdout="10.0.0.1", stderr="", command=""
        )

        installer.install(ssh)

        calls = [str(c) for c in ssh.execute_sudo.call_args_list]
        assert any("pve-enterprise" in c for c in calls)

    def test_root_password_generation(self):
        """Test that root password is auto-generated if not set."""
        config = ProxmoxConfig(root_password=None)
        installer = ProxmoxInstaller(config)

        password = installer.root_password
        assert len(password) == 20
        assert password == installer.root_password  # Should be consistent

    def test_root_password_from_config(self):
        """Test that configured root password is used."""
        config = ProxmoxConfig(root_password="my-secure-password")
        installer = ProxmoxInstaller(config)

        assert installer.root_password == "my-secure-password"

    def test_verify_installation_success(self):
        """Test successful installation verification."""
        config = ProxmoxConfig()
        installer = ProxmoxInstaller(config)
        ssh = MagicMock()

        ssh.execute_sudo.side_effect = [
            ExecutionResult(exit_code=0, stdout="pve-manager/8.2.2", stderr="", command=""),
            ExecutionResult(exit_code=0, stdout="active\n", stderr="", command=""),
            ExecutionResult(exit_code=0, stdout="active\n", stderr="", command=""),
            ExecutionResult(exit_code=0, stdout="active\n", stderr="", command=""),
        ]

        assert installer.verify_installation(ssh) is True

    def test_verify_installation_service_down(self):
        """Test verification failure when a service is down."""
        config = ProxmoxConfig()
        installer = ProxmoxInstaller(config)
        ssh = MagicMock()

        # pveversion succeeds, pve-cluster is active, but pvedaemon is inactive
        ssh.execute_sudo.side_effect = [
            ExecutionResult(exit_code=0, stdout="pve-manager/8.2.2", stderr="", command=""),
            ExecutionResult(exit_code=0, stdout="active\n", stderr="", command=""),
            ExecutionResult(exit_code=0, stdout="inactive\n", stderr="", command=""),
        ]

        assert installer.verify_installation(ssh) is False

    def test_apt_update_failure_raises(self):
        """Test that apt-get update failure raises error."""
        config = ProxmoxConfig()
        installer = ProxmoxInstaller(config)
        ssh = MagicMock()

        # Hostname succeeds, but apt-get update fails
        ssh.execute_sudo.side_effect = [
            ExecutionResult(exit_code=0, stdout="10.0.0.1", stderr="", command=""),
            ExecutionResult(exit_code=0, stdout="", stderr="", command=""),
            ExecutionResult(exit_code=0, stdout="", stderr="", command=""),
            ExecutionResult(exit_code=0, stdout="", stderr="", command=""),  # wget
            ExecutionResult(exit_code=0, stdout="", stderr="", command=""),  # echo repo
            ExecutionResult(exit_code=1, stdout="", stderr="E: Failed", command="apt-get update"),
        ]

        from proxmox_install_automation.exceptions import ProxmoxInstallError

        with pytest.raises(ProxmoxInstallError):
            installer.install(ssh)
