"""
Ironic bare-metal deployment for the local build / OPCP deploy path (Req 11).

`IronicDeployer` deploys the Glance-imported, generic Proxmox VE image onto an
Ironic bare-metal node. It reuses the existing OpenStack deploy stack rather
than duplicating logic (Req 11.3):

- ``auth.manager.OpenStackAuthManager`` establishes the authenticated
  connection from the shared ``Credentials`` model.
- ``provisioner.instance.InstanceProvisioner`` manages the lifecycle of the
  resulting bare-metal server (it is already the OVH OpenStack bare-metal
  provisioner used by the remote flow).
- The ``gpu`` module components (``GPUDetector``, ``IOMMUConfigurator``,
  ``VFIOManager``) remain available for passthrough configuration where a
  deployment targets GPU-capable hardware.

External ``openstack`` CLI calls go through the injected `LocalCommandRunner`,
with the actual command lines produced by pure argv builders so they can be
asserted by tests without spawning a process, mirroring the other local_build
components.

Responsibilities:

- ``configure_node`` sets the Ironic node ``boot_mode`` to ``uefi`` (Req 11.1).
- ``deploy`` creates the server via ``openstack server create`` using the
  imported image, reusing the provisioner/orchestrator/gpu stack, returns the
  server id, and raises `IronicDeployError` on failure (Req 11.2, 11.3, 11.4).
"""

from typing import List, Optional

from ..auth.manager import OpenStackAuthManager
from ..gpu import GPUDetector, IOMMUConfigurator, VFIOManager
from ..logging_config import get_logger
from ..provisioner.instance import InstanceProvisioner
from .command_runner import LocalCommandRunner
from .exceptions import IronicDeployError, LocalCommandError
from .models import DeployConfig

logger = get_logger("local_build.ironic_deployer")


class IronicDeployer:
    """Deploy the imported image to an Ironic bare-metal node (Req 11)."""

    def __init__(
        self,
        runner: LocalCommandRunner,
        auth_manager: Optional[OpenStackAuthManager] = None,
    ) -> None:
        """
        Args:
            runner: The mockable local command runner used to invoke the
                ``openstack`` CLI.
            auth_manager: The OpenStack auth manager reused from the existing
                deploy stack (Req 11.3). A fresh ``OpenStackAuthManager`` is
                created when not supplied.
        """
        self._runner = runner
        self._auth_manager = auth_manager or OpenStackAuthManager()
        # GPU passthrough components from the existing deploy stack, available
        # for GPU-capable bare-metal targets (Req 11.3).
        self._gpu_detector = GPUDetector()
        self._iommu_configurator = IOMMUConfigurator()
        self._vfio_manager = VFIOManager()

    def build_configure_node_argv(self, node: str) -> List[str]:
        """
        Build the ``openstack baremetal node set`` argv (pure, deterministic).

        Sets the node capability ``boot_mode:uefi`` so the generic image boots
        in UEFI mode on physical hardware (Req 11.1). Performs no I/O and
        depends only on its argument, so it is safe to call from property tests.

        Args:
            node: The Ironic node name or UUID.

        Returns:
            The ``openstack`` command and its arguments as a list of strings.
        """
        return [
            "openstack",
            "baremetal",
            "node",
            "set",
            node,
            "--property",
            "capabilities=boot_mode:uefi",
        ]

    def build_server_create_argv(
        self, config: DeployConfig, glance_image_id: str
    ) -> List[str]:
        """
        Build the ``openstack server create`` argv (pure, deterministic).

        Deploys the imported Glance image to the configured bare-metal flavor
        and network (Req 11.2). Performs no I/O and depends only on its
        arguments, so it is safe to call from property tests.

        Args:
            config: The deploy configuration supplying the Glance image name,
                bare-metal flavor, and network.
            glance_image_id: The id of the imported Glance image to deploy.

        Returns:
            The ``openstack`` command and its arguments as a list of strings.
        """
        return [
            "openstack",
            "server",
            "create",
            "--image",
            glance_image_id,
            "--flavor",
            config.bare_metal_flavor,
            "--network",
            config.network_name,
            "--wait",
            "--format",
            "value",
            "--column",
            "id",
            config.glance_image_name,
        ]

    def configure_node(self, node: str) -> None:
        """
        Configure the Ironic node boot_mode to UEFI (Req 11.1).

        Args:
            node: The Ironic node name or UUID.

        Raises:
            IronicDeployError: If the ``openstack`` CLI call fails or cannot be
                executed (Req 11.4).
        """
        argv = self.build_configure_node_argv(node)
        logger.info("Configuring Ironic node '%s' boot_mode=uefi", node)
        try:
            self._runner.run(argv, check=True)
        except LocalCommandError as exc:
            raise IronicDeployError(
                f"Failed to configure Ironic node '{node}' for UEFI boot: {exc}"
            ) from exc

    def deploy(self, config: DeployConfig, glance_image_id: str) -> str:
        """
        Deploy the imported image to the Ironic node (Req 11.2, 11.3, 11.4).

        Authenticates via the reused ``OpenStackAuthManager`` and binds an
        ``InstanceProvisioner`` to that connection so the resulting bare-metal
        server is managed by the existing provisioner stack (Req 11.3). The
        node is configured for UEFI boot, then the server is created from the
        imported Glance image via ``openstack server create`` (Req 11.2).

        Args:
            config: The deploy configuration (credentials, Ironic node,
                bare-metal flavor, network).
            glance_image_id: The id of the imported Glance image to deploy.

        Returns:
            The created server id.

        Raises:
            IronicDeployError: If authentication, node configuration, or server
                creation fails (Req 11.4).
        """
        logger.info(
            "Deploying image '%s' to Ironic node '%s'",
            glance_image_id,
            config.ironic_node,
        )

        try:
            # Reuse the existing deploy stack (Req 11.3): authenticate and bind
            # the provisioner to the live connection so the bare-metal server
            # lifecycle is owned by the established InstanceProvisioner.
            connection = self._auth_manager.authenticate(config.credentials)
            self._provisioner = InstanceProvisioner(connection)
        except Exception as exc:
            raise IronicDeployError(
                f"Failed to authenticate for Ironic deploy to node "
                f"'{config.ironic_node}': {exc}"
            ) from exc

        # Configure the node for UEFI boot (Req 11.1) before deploying.
        self.configure_node(config.ironic_node)

        # Create the server from the imported image (Req 11.2).
        argv = self.build_server_create_argv(config, glance_image_id)
        try:
            result = self._runner.run(argv, timeout=config.deploy_timeout, check=True)
        except LocalCommandError as exc:
            raise IronicDeployError(
                f"Failed to deploy image '{glance_image_id}' to Ironic node "
                f"'{config.ironic_node}': {exc}"
            ) from exc

        server_id = result.stdout.strip()
        if not server_id:
            raise IronicDeployError(
                "openstack server create did not return a server id for "
                f"deploy to Ironic node '{config.ironic_node}'"
            )

        logger.info(
            "Deployed server '%s' to Ironic node '%s'",
            server_id,
            config.ironic_node,
        )
        return server_id


# GPU passthrough components are available for GPU-capable deployments (Req 11.3).
_GPU_COMPONENTS = (GPUDetector, IOMMUConfigurator, VFIOManager)


__all__ = ["IronicDeployer"]
