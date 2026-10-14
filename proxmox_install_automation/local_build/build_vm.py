"""
Build VM creation for the local KVM/libvirt Proxmox VE build path (Req 5).

`BuildVMCreator` wraps ``virt-install`` to create the transient Build_VM named
``proxmox-image-builder``. The argv is produced by a pure helper,
``build_argv``, so the generated command line is fully deterministic and can be
asserted by tests without spawning any process. Execution is delegated to the
injected `LocalCommandRunner`, mirroring the other local_build components.

The generated argv guarantees the mandated resources (Req 5.1, 5.2):

- ``--name proxmox-image-builder`` (``config.build_vm_name``)
- ``--vcpus 8`` (``config.vcpus``)
- ``--memory 16384`` (``config.ram_mib``)
- ``--cpu host-passthrough`` (``config.cpu_mode``)
- UEFI boot via an OVMF loader (``--boot uefi``)
- a VirtIO system disk (``--disk ... ,bus=virtio``)
- a VirtIO network interface (``--network ... ,model=virtio``)
- the staged ISO attached as a CD-ROM (``--cdrom <iso_path>``)
"""

from typing import List

from ..logging_config import get_logger
from .command_runner import LocalCommandRunner
from .exceptions import BuildVMError, LocalCommandError
from .models import LocalBuildConfig

logger = get_logger("local_build.build_vm")


class BuildVMCreator:
    """Create the transient Build_VM via ``virt-install`` (Req 5)."""

    def __init__(self, runner: LocalCommandRunner) -> None:
        """
        Args:
            runner: The mockable local command runner used to invoke
                ``virt-install``.
        """
        self._runner = runner

    def build_argv(
        self,
        config: LocalBuildConfig,
        iso_path: str,
        disk_path: str,
    ) -> List[str]:
        """
        Build the full ``virt-install`` argv (pure, deterministic).

        This function performs no I/O and depends only on its arguments, so it
        is safe to call from property tests. The returned argv guarantees the
        presence of every resource mandated by Requirement 5.2.

        Args:
            config: The local build configuration supplying VM name, vCPUs,
                RAM, CPU mode, and the VirtIO disk/network models.
            iso_path: Path to the staged installer ISO, attached as the CD-ROM.
            disk_path: Path to the qcow2 System_Disk, attached as a VirtIO disk.

        Returns:
            The ``virt-install`` command and its arguments as a list of strings.
        """
        return [
            "virt-install",
            "--name",
            config.build_vm_name,
            "--vcpus",
            str(config.vcpus),
            "--memory",
            str(config.ram_mib),
            "--cpu",
            config.cpu_mode,
            "--boot",
            "uefi",
            "--disk",
            f"path={disk_path},format=qcow2,bus={config.disk_bus}",
            "--network",
            f"network=default,model={config.network_model}",
            "--cdrom",
            iso_path,
        ]

    def create(
        self,
        config: LocalBuildConfig,
        iso_path: str,
        disk_path: str,
    ) -> None:
        """
        Invoke ``virt-install`` to create the Build_VM (Req 5.1).

        Args:
            config: The local build configuration.
            iso_path: Path to the staged installer ISO.
            disk_path: Path to the qcow2 System_Disk.

        Raises:
            BuildVMError: If ``virt-install`` fails or cannot be executed
                (Req 5.3).
        """
        argv = self.build_argv(config, iso_path, disk_path)
        logger.info(
            "Creating build VM '%s' via virt-install", config.build_vm_name
        )
        try:
            self._runner.run(argv, timeout=config.build_timeout, check=True)
        except LocalCommandError as exc:
            raise BuildVMError(
                f"Failed to create build VM '{config.build_vm_name}': {exc}"
            ) from exc


__all__ = ["BuildVMCreator"]
