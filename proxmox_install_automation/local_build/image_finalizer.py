"""
Image finalization for the local KVM/libvirt Proxmox VE build path (Req 8).

`ImageFinalizer` performs the terminal build steps that turn the cleaned
Build_VM System_Disk into the verified, compact Final_Image:

  8.1  clean shutdown of the Build_VM (``virsh shutdown`` + wait for shut-off)
  8.2  ``virsh undefine proxmox-image-builder --nvram`` while RETAINING the
       System_Disk qcow2 file (never a storage-removal flag)
  8.3  validate the qcow2 disk via ``qemu-img check`` and ``qemu-img info``
  8.4  compress via ``qemu-img convert -O qcow2 -c`` into
       ``proxmox-opcp-final.qcow2``
  8.5  raise :class:`ImageFinalizeError` if validation fails

The shell command lines are produced by the pure helpers ``build_undefine_argv``
and ``build_convert_argv`` so the generated argv is deterministic and can be
asserted directly in tests. ``build_undefine_argv`` NEVER includes a
storage-removal flag (e.g. ``--remove-all-storage`` / ``--storage`` /
``--delete-storage``) so the System_Disk is always preserved. Execution is
delegated to the injected :class:`LocalCommandRunner`, mirroring the other
local_build components.
"""

import json
import time
from posixpath import join as posix_join
from typing import List

from ..logging_config import get_logger
from .command_runner import LocalCommandRunner
from .exceptions import ImageFinalizeError, LocalCommandError
from .models import ImageBuildArtifact, LocalBuildConfig

logger = get_logger("local_build.image_finalizer")

# Poll interval and bound used while waiting for the Build_VM to reach the
# ``shut off`` libvirt domain state after a clean shutdown (Req 8.1).
_SHUTDOWN_POLL_SECONDS = 5
_SHUTDOWN_STATE = "shut off"


class ImageFinalizer:
    """Undefine the Build_VM, validate the disk, and compress the Final_Image."""

    def __init__(self, runner: LocalCommandRunner) -> None:
        """
        Args:
            runner: Injected local command runner used to invoke ``virsh`` and
                ``qemu-img``.
        """
        self._runner = runner

    def build_undefine_argv(self, vm_name: str) -> List[str]:
        """
        Pure: build the ``virsh undefine`` argv (Req 8.2).

        Returns ``['virsh', 'undefine', vm_name, '--nvram']``. The ``--nvram``
        flag removes the per-VM UEFI NVRAM while the System_Disk qcow2 file is
        retained. This argv NEVER includes a storage-removal flag
        (``--remove-all-storage``, ``--storage``, ``--delete-storage``), so the
        System_Disk is always preserved.

        Args:
            vm_name: The transient Build_VM domain name to undefine.

        Returns:
            The ``virsh undefine`` command and its arguments as a list.
        """
        return ["virsh", "undefine", vm_name, "--nvram"]

    def build_convert_argv(self, src: str, dst: str) -> List[str]:
        """
        Pure: build the ``qemu-img convert`` argv for compression (Req 8.4).

        Returns ``['qemu-img', 'convert', '-O', 'qcow2', '-c', src, dst]``. The
        ``-c`` flag enables qcow2 compression so the Final_Image is compact.

        Args:
            src: Path to the validated source qcow2 disk.
            dst: Path to the compressed Final_Image to produce.

        Returns:
            The ``qemu-img convert`` command and its arguments as a list.
        """
        return ["qemu-img", "convert", "-O", "qcow2", "-c", src, dst]

    def shutdown(self, vm_name: str) -> None:
        """
        Perform a clean shutdown of the Build_VM and wait for shut-off (Req 8.1).

        Issues ``virsh shutdown`` and then polls ``virsh domstate`` until the
        domain reports ``shut off``. The injected runner is used for both
        invocations so the behavior is fully mockable in tests.

        Args:
            vm_name: The transient Build_VM domain name to shut down.

        Raises:
            ImageFinalizeError: If the shutdown request fails or the domain does
                not reach the shut-off state.
        """
        logger.info("Requesting clean shutdown of build VM '%s'", vm_name)
        try:
            self._runner.run(["virsh", "shutdown", vm_name], check=True)
        except LocalCommandError as exc:
            raise ImageFinalizeError(
                f"Failed to request shutdown of build VM '{vm_name}': {exc}"
            ) from exc

        logger.info("Waiting for build VM '%s' to reach shut-off state", vm_name)
        try:
            result = self._runner.run(
                ["virsh", "domstate", vm_name], check=True
            )
        except LocalCommandError as exc:
            raise ImageFinalizeError(
                f"Failed to query state of build VM '{vm_name}': {exc}"
            ) from exc

        while _SHUTDOWN_STATE not in (result.stdout or "").strip().lower():
            time.sleep(_SHUTDOWN_POLL_SECONDS)
            try:
                result = self._runner.run(
                    ["virsh", "domstate", vm_name], check=True
                )
            except LocalCommandError as exc:
                raise ImageFinalizeError(
                    f"Failed to query state of build VM '{vm_name}': {exc}"
                ) from exc

        logger.info("Build VM '%s' is shut off", vm_name)

    def finalize(
        self, config: LocalBuildConfig, disk_path: str
    ) -> ImageBuildArtifact:
        """
        Undefine the Build_VM, validate the disk, and compress the Final_Image.

        Sequence (Req 8.2–8.5):
          1. ``virsh undefine <vm> --nvram`` retaining the System_Disk (8.2).
          2. ``qemu-img check`` + ``qemu-img info`` validation (8.3). On any
             validation failure, raise :class:`ImageFinalizeError` (8.5).
          3. ``qemu-img convert -O qcow2 -c`` into ``final_image_name`` under
             ``output_dir`` (8.4).
          4. Populate and return an :class:`ImageBuildArtifact` describing the
             produced Final_Image.

        Args:
            config: The local build configuration supplying the Build_VM name,
                the final image name, the output directory, and timeouts.
            disk_path: Path to the cleaned System_Disk qcow2 to finalize.

        Returns:
            An :class:`ImageBuildArtifact` for the produced Final_Image.

        Raises:
            ImageFinalizeError: If undefine fails, qcow2 validation fails, or
                the compression step fails (Req 8.5).
        """
        start = time.monotonic()

        # 8.2 — undefine the Build_VM, retaining the System_Disk qcow2.
        undefine_argv = self.build_undefine_argv(config.build_vm_name)
        logger.info("Undefining build VM '%s' (retaining disk)", config.build_vm_name)
        try:
            self._runner.run(undefine_argv, check=True)
        except LocalCommandError as exc:
            raise ImageFinalizeError(
                f"Failed to undefine build VM '{config.build_vm_name}': {exc}"
            ) from exc

        # 8.3 — validate the qcow2 disk via qemu-img check + qemu-img info.
        self._validate_disk(disk_path)
        info = self._qemu_img_info(disk_path)
        virtual_size = int(info.get("virtual-size", 0))
        actual_size = int(info.get("actual-size", 0))

        # 8.4 — compress the validated disk into the Final_Image.
        final_image_path = posix_join(config.output_dir, config.final_image_name)
        convert_argv = self.build_convert_argv(disk_path, final_image_path)
        logger.info(
            "Compressing disk %s into Final_Image %s", disk_path, final_image_path
        )
        try:
            self._runner.run(
                convert_argv, timeout=config.convert_timeout, check=True
            )
        except LocalCommandError as exc:
            raise ImageFinalizeError(
                f"Failed to compress disk into {final_image_path}: {exc}"
            ) from exc

        duration = time.monotonic() - start
        logger.info("Final_Image produced at %s in %.3fs", final_image_path, duration)

        return ImageBuildArtifact(
            final_image_path=final_image_path,
            virtual_size_bytes=virtual_size,
            actual_size_bytes=actual_size,
            build_duration_seconds=duration,
            boot_test_passed=False,
        )

    def _validate_disk(self, disk_path: str) -> None:
        """
        Validate the qcow2 disk via ``qemu-img check`` (Req 8.3).

        Raises:
            ImageFinalizeError: If ``qemu-img check`` reports a non-zero exit or
                cannot be executed (Req 8.5).
        """
        logger.info("Validating qcow2 disk via qemu-img check: %s", disk_path)
        try:
            self._runner.run(["qemu-img", "check", disk_path], check=True)
        except LocalCommandError as exc:
            raise ImageFinalizeError(
                f"qcow2 validation failed for {disk_path}: {exc}"
            ) from exc

    def _qemu_img_info(self, disk_path: str) -> dict:
        """
        Inspect the qcow2 disk via ``qemu-img info --output=json`` (Req 8.3).

        Returns the parsed JSON mapping (notably ``virtual-size`` and
        ``actual-size``) used to populate the resulting artifact.

        Raises:
            ImageFinalizeError: If ``qemu-img info`` fails or returns output that
                cannot be parsed (Req 8.5).
        """
        logger.info("Inspecting qcow2 disk via qemu-img info: %s", disk_path)
        try:
            result = self._runner.run(
                ["qemu-img", "info", "--output=json", disk_path], check=True
            )
        except LocalCommandError as exc:
            raise ImageFinalizeError(
                f"qcow2 inspection failed for {disk_path}: {exc}"
            ) from exc

        try:
            return json.loads(result.stdout or "{}")
        except (ValueError, TypeError) as exc:
            raise ImageFinalizeError(
                f"Could not parse qemu-img info output for {disk_path}: {exc}"
            ) from exc


__all__ = ["ImageFinalizer"]
