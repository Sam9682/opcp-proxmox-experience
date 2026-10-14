"""
System disk creation for the local KVM/libvirt build path (Req 4).

`SystemDiskCreator` creates the 64GB qcow2 System_Disk that serves as the
Build_VM boot and system volume. The disk is created independently of any
future data disks so the resulting image contains only the operating system.

The qemu-img argv is produced by the pure `build_argv` helper so it can be
asserted directly in tests, while `create` wires that argv to an injected
`LocalCommandRunner`, mirroring how other components in this package depend on
a single mockable command runner.
"""

from posixpath import join as posix_join
from typing import List

from ..logging_config import get_logger
from .command_runner import LocalCommandRunner
from .exceptions import LocalCommandError, SystemDiskError
from .models import LocalBuildConfig

logger = get_logger("local_build.system_disk")


class SystemDiskCreator:
    """Creates the 64GB qcow2 System_Disk for the Build_VM (Req 4)."""

    def __init__(self, runner: LocalCommandRunner) -> None:
        """
        Args:
            runner: Injected local command runner used to invoke qemu-img.
        """
        self._runner = runner

    def build_argv(self, path: str, size_gb: int) -> List[str]:
        """
        Pure: build the qemu-img argv for creating a qcow2 disk.

        Args:
            path: Destination path for the qcow2 disk.
            size_gb: Disk capacity in gibibytes.

        Returns:
            ``['qemu-img', 'create', '-f', 'qcow2', path, f'{size_gb}G']``.
        """
        return ["qemu-img", "create", "-f", "qcow2", path, f"{size_gb}G"]

    def create(self, config: LocalBuildConfig) -> str:
        """
        Create the qcow2 System_Disk independent of any data disks (Req 4.1, 4.2).

        Computes the disk path from the configured libvirt images directory and
        system disk name, invokes qemu-img via the injected runner, and returns
        the created disk path.

        Args:
            config: The local build configuration.

        Returns:
            The path to the created qcow2 System_Disk.

        Raises:
            SystemDiskError: If the disk cannot be created (Req 4.3).
        """
        disk_path = posix_join(config.libvirt_images_dir, config.system_disk_name)
        argv = self.build_argv(disk_path, config.system_disk_size_gb)

        logger.info(
            "Creating %dGB qcow2 system disk at %s",
            config.system_disk_size_gb,
            disk_path,
        )

        try:
            self._runner.run(argv, timeout=config.build_timeout, check=True)
        except LocalCommandError as exc:
            raise SystemDiskError(
                f"Failed to create system disk at {disk_path}: {exc}"
            ) from exc

        logger.info("System disk created: %s", disk_path)
        return disk_path


__all__ = ["SystemDiskCreator"]
