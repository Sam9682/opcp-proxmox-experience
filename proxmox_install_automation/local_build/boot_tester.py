"""
ISO-less import boot test for the local KVM/libvirt build path (Req 9).

`BootTester` import-boots the Final_Image with ``virt-install --import`` and
confirms the boot sequence reaches UEFI, then GRUB, then the Debian kernel,
then Proxmox VE by parsing the captured serial console (Req 9.1, 9.2, 9.3).

Two helpers are kept genuinely pure so they can be asserted by tests without
spawning any process or performing any I/O:

- ``build_argv(image_path, config)`` produces a deterministic
  ``virt-install --import`` argv. It ALWAYS contains ``--import`` and NEVER a
  ``--cdrom`` / ISO attachment (Req 9.1).
- ``detect_boot_sequence(console_log)`` returns True iff ``BOOT_MARKERS``
  appear in order within the log (Req 9.2).

Execution is delegated to the injected `LocalCommandRunner`, mirroring the
other local_build components.
"""

from typing import List

from ..logging_config import get_logger
from .command_runner import LocalCommandRunner
from .exceptions import BootTestError, LocalCommandError
from .models import LocalBuildConfig

logger = get_logger("local_build.boot_tester")

# Ordered boot-sequence markers: UEFI firmware -> GRUB bootloader ->
# Debian/Linux kernel -> Proxmox VE userspace (Req 9.2).
BOOT_MARKERS = ("UEFI", "GRUB", "Linux", "Proxmox VE")


class BootTester:
    """Perform the ISO-less import boot test of the Final_Image (Req 9)."""

    def __init__(self, runner: LocalCommandRunner) -> None:
        """
        Args:
            runner: The mockable local command runner used to invoke
                ``virt-install`` for the import boot test.
        """
        self._runner = runner

    def build_argv(self, image_path: str, config: LocalBuildConfig) -> List[str]:
        """
        Build the ``virt-install --import`` argv (pure, deterministic).

        This function performs no I/O and depends only on its arguments, so it
        is safe to call from property tests. The returned argv ALWAYS contains
        ``--import`` and NEVER a ``--cdrom`` / ISO attachment, so the final
        image is booted entirely on its own (Req 9.1).

        Args:
            image_path: Path to the Final_Image qcow2 disk to import-boot.
            config: The local build configuration supplying the throwaway boot
                VM resources and VirtIO disk model.

        Returns:
            The ``virt-install`` command and its arguments as a list of strings.
        """
        return [
            "virt-install",
            "--name",
            f"{config.build_vm_name}-boottest",
            "--vcpus",
            str(config.vcpus),
            "--memory",
            str(config.ram_mib),
            "--cpu",
            config.cpu_mode,
            "--boot",
            "uefi",
            "--import",
            "--disk",
            f"path={image_path},format=qcow2,bus={config.disk_bus}",
            "--network",
            f"network=default,model={config.network_model}",
            "--graphics",
            "none",
            "--serial",
            "pty",
            "--noautoconsole",
            "--transient",
            "--wait",
            str(max(1, config.boot_test_timeout // 60)),
        ]

    def detect_boot_sequence(self, console_log: str) -> bool:
        """
        Return True iff ``BOOT_MARKERS`` appear in order in ``console_log``.

        Pure: performs no I/O and depends only on its argument. Each marker
        must be found at or after the position where the previous marker ended,
        so the markers must occur in the required order (Req 9.2).

        Args:
            console_log: The captured serial-console output of the boot test.

        Returns:
            True iff every marker in ``BOOT_MARKERS`` appears in sequence.
        """
        cursor = 0
        for marker in BOOT_MARKERS:
            found = console_log.find(marker, cursor)
            if found == -1:
                return False
            cursor = found + len(marker)
        return True

    def run(self, image_path: str, config: LocalBuildConfig) -> bool:
        """
        Import-boot the Final_Image and confirm it reaches Proxmox VE (Req 9).

        Boots the image with ``virt-install --import`` (no ISO attached),
        captures the serial console, and applies ``detect_boot_sequence`` to
        confirm the boot reaches UEFI -> GRUB -> Debian kernel -> Proxmox VE.

        Args:
            image_path: Path to the Final_Image qcow2 disk to boot.
            config: The local build configuration.

        Returns:
            True when the full boot sequence is reached.

        Raises:
            BootTestError: If ``virt-install`` cannot be executed, or the boot
                sequence does not reach Proxmox VE (Req 9.3).
        """
        argv = self.build_argv(image_path, config)
        logger.info(
            "Boot-testing final image '%s' via virt-install --import", image_path
        )
        try:
            result = self._runner.run(
                argv, timeout=config.boot_test_timeout, check=True
            )
        except LocalCommandError as exc:
            raise BootTestError(
                f"Import boot test failed to run for '{image_path}': {exc}"
            ) from exc

        console_log = f"{result.stdout}\n{result.stderr}"
        if not self.detect_boot_sequence(console_log):
            raise BootTestError(
                f"Import boot test for '{image_path}' did not reach Proxmox VE; "
                f"expected boot sequence {' -> '.join(BOOT_MARKERS)} was not "
                "observed on the serial console"
            )

        logger.info("Boot test passed for final image '%s'", image_path)
        return True


__all__ = ["BOOT_MARKERS", "BootTester"]
