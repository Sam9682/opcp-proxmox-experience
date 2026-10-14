"""
Tests for the IronicDeployer component (local_build, Requirement 11).

Covers:
- build_configure_node_argv sets capabilities=boot_mode:uefi (Req 11.1).
- build_server_create_argv deploys the imported image to the configured
  flavor/network (Req 11.2).
- configure_node invokes the injected runner (Req 11.1).
- deploy authenticates via the reused auth manager, configures the node for
  UEFI, runs server create, and returns the stripped server id (Req 11.2, 11.3).
- deploy raises IronicDeployError when node configuration or server create
  fails, or when no server id is returned (Req 11.4).
"""

from unittest.mock import MagicMock

import pytest

from proxmox_install_automation.local_build.exceptions import (
    IronicDeployError,
    LocalCommandError,
)
from proxmox_install_automation.local_build.ironic_deployer import IronicDeployer
from proxmox_install_automation.local_build.models import CommandResult, DeployConfig
from proxmox_install_automation.models import Credentials

GLANCE_IMAGE_ID = "glance-img-42"


def _credentials() -> Credentials:
    return Credentials(auth_url="https://keystone.example/v3", region="RegionOne")


def _deploy_config(**overrides) -> DeployConfig:
    base = dict(
        final_image_path="/var/lib/libvirt/images/proxmox-opcp-final.qcow2",
        glance_image_name="proxmox-opcp",
        credentials=_credentials(),
        ironic_node="node-1",
        bare_metal_flavor="baremetal",
        network_name="Ext-Net",
        deploy_timeout=30,
    )
    base.update(overrides)
    return DeployConfig(**base)


def _result(stdout: str = "server-xyz", argv=None) -> CommandResult:
    return CommandResult(
        argv=argv or ["openstack"],
        exit_code=0,
        stdout=stdout,
        stderr="",
    )


def _deployer(runner=None, auth=None):
    """Build an IronicDeployer with mocked runner and auth manager so no real
    OpenStack / provisioner calls happen."""
    runner = runner or MagicMock()
    auth = auth or MagicMock()
    return IronicDeployer(runner=runner, auth_manager=auth), runner, auth


class TestBuildConfigureNodeArgv:
    """build_configure_node_argv is pure and sets UEFI boot mode (Req 11.1)."""

    def test_sets_boot_mode_uefi_capability(self):
        deployer, _, _ = _deployer()

        argv = deployer.build_configure_node_argv("node-1")

        assert argv[:4] == ["openstack", "baremetal", "node", "set"]
        assert "node-1" in argv
        assert "--property" in argv
        assert "capabilities=boot_mode:uefi" in argv

    def test_is_pure_no_runner_or_auth_interaction(self):
        deployer, runner, auth = _deployer()

        deployer.build_configure_node_argv("node-1")

        runner.run.assert_not_called()
        auth.authenticate.assert_not_called()


class TestBuildServerCreateArgv:
    """build_server_create_argv deploys the imported image (Req 11.2)."""

    def test_contains_image_flavor_and_network(self):
        deployer, _, _ = _deployer()
        config = _deploy_config()

        argv = deployer.build_server_create_argv(config, GLANCE_IMAGE_ID)

        assert argv[:3] == ["openstack", "server", "create"]
        # --image <glance_image_id>
        assert "--image" in argv
        assert argv[argv.index("--image") + 1] == GLANCE_IMAGE_ID
        # --flavor <bare_metal_flavor>
        assert "--flavor" in argv
        assert argv[argv.index("--flavor") + 1] == config.bare_metal_flavor
        # --network <network_name>
        assert "--network" in argv
        assert argv[argv.index("--network") + 1] == config.network_name

    def test_is_pure_no_runner_or_auth_interaction(self):
        deployer, runner, auth = _deployer()

        deployer.build_server_create_argv(_deploy_config(), GLANCE_IMAGE_ID)

        runner.run.assert_not_called()
        auth.authenticate.assert_not_called()


class TestConfigureNode:
    """configure_node invokes the runner and maps failures (Req 11.1, 11.4)."""

    def test_invokes_runner_with_uefi_argv(self):
        runner = MagicMock()
        runner.run.return_value = _result()
        deployer, _, _ = _deployer(runner=runner)

        deployer.configure_node("node-1")

        runner.run.assert_called_once()
        called_argv = runner.run.call_args.args[0]
        assert "capabilities=boot_mode:uefi" in called_argv

    def test_raises_ironic_deploy_error_on_command_failure(self):
        runner = MagicMock()
        runner.run.side_effect = LocalCommandError("set failed")
        deployer, _, _ = _deployer(runner=runner)

        with pytest.raises(IronicDeployError, match="configure Ironic node"):
            deployer.configure_node("node-1")


class TestDeploy:
    """deploy orchestrates auth, node config, and server create (Req 11.2-11.4)."""

    def test_authenticates_configures_and_returns_server_id(self):
        runner = MagicMock()
        # configure_node then server create; server create returns the id.
        runner.run.side_effect = [_result(), _result(stdout="  server-xyz  \n")]
        auth = MagicMock()
        deployer, _, _ = _deployer(runner=runner, auth=auth)
        config = _deploy_config()

        server_id = deployer.deploy(config, GLANCE_IMAGE_ID)

        # Stripped server id returned from runner stdout.
        assert server_id == "server-xyz"
        # Authenticated via the injected auth manager (Req 11.3).
        auth.authenticate.assert_called_once_with(config.credentials)
        # Two runner calls: node config (UEFI) + server create.
        assert runner.run.call_count == 2
        first_argv = runner.run.call_args_list[0].args[0]
        second_argv = runner.run.call_args_list[1].args[0]
        assert "capabilities=boot_mode:uefi" in first_argv
        assert second_argv[:3] == ["openstack", "server", "create"]
        assert GLANCE_IMAGE_ID in second_argv

    def test_raises_when_authentication_fails(self):
        auth = MagicMock()
        auth.authenticate.side_effect = RuntimeError("no creds")
        runner = MagicMock()
        deployer, _, _ = _deployer(runner=runner, auth=auth)

        with pytest.raises(IronicDeployError, match="authenticate"):
            deployer.deploy(_deploy_config(), GLANCE_IMAGE_ID)

    def test_raises_when_node_configuration_fails(self):
        runner = MagicMock()
        runner.run.side_effect = LocalCommandError("node set failed")
        deployer, _, _ = _deployer(runner=runner)

        with pytest.raises(IronicDeployError, match="configure Ironic node"):
            deployer.deploy(_deploy_config(), GLANCE_IMAGE_ID)

    def test_raises_when_server_create_fails(self):
        runner = MagicMock()
        # configure_node succeeds, server create raises.
        runner.run.side_effect = [_result(), LocalCommandError("create failed")]
        deployer, _, _ = _deployer(runner=runner)

        with pytest.raises(IronicDeployError, match="deploy image"):
            deployer.deploy(_deploy_config(), GLANCE_IMAGE_ID)

    def test_raises_when_server_id_is_empty(self):
        runner = MagicMock()
        # configure_node succeeds, server create returns empty/whitespace id.
        runner.run.side_effect = [_result(), _result(stdout="   \n")]
        deployer, _, _ = _deployer(runner=runner)

        with pytest.raises(IronicDeployError, match="did not return a server id"):
            deployer.deploy(_deploy_config(), GLANCE_IMAGE_ID)
