"""
ISO staging for the local KVM/libvirt build path (Requirement 3).

`ISOStager` places the Proxmox installation ISO into the libvirt images
directory with ownership/permissions that allow libvirt to read it, so the
transient Build_VM can boot from the staged ISO.

The architecture-to-ISO mapping is exposed as the pure, side-effect-free
``select_iso`` helper (Req 3.3, 3.4) so it can be property-tested directly.
Filesystem mutation (copy + permission setup) lives in ``stage`` and runs
through the injected ``LocalCommandRunner``, mirroring how the other
tool-invoking components isolate shell execution behind one mockable object.
"""

import os
import shutil
from typing import Dict

from ..logging_config import get_logger
from .command_runner import LocalCommandRunner
from .exceptions import ISOStagingError
from .models import LocalBuildConfig

logger = get_logger("local_build.iso_stager")


# Maps a target-architecture token to its ISO architecture family.
# x86_64 and amd64 are synonyms for the standard amd64 ISO; arm64 selects
# the ARM64 ISO (Req 3.3, 3.4).
ISO_BY_ARCH: Dict[str, str] = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "arm64": "arm64",
}


class ISOStager:
    """Stages the Proxmox installer ISO into the libvirt images directory."""

    def __init__(self, runner: LocalCommandRunner) -> None:
        """
        Args:
            runner: Injected local command runner used to apply
                libvirt-readable ownership/permissions on the staged ISO.
        """
        self._runner = runner

    def select_iso(self, architecture: str, available: Dict[str, str]) -> str:
        """
        Map an architecture token to its ISO entry (Req 3.3, 3.4).

        Pure: performs no I/O and has no side effects. The architecture token
        is normalized through ``ISO_BY_ARCH`` to an ISO architecture family,
        and the matching entry is returned from ``available``.

        Args:
            architecture: Target architecture token (``x86_64``, ``amd64``, or
                ``arm64``). Matched case-insensitively.
            available: Mapping of ISO architecture family (e.g. ``amd64``,
                ``arm64``) to the available ISO path/name for that family.

        Returns:
            The ISO entry from ``available`` for the resolved architecture
            family.

        Raises:
            ISOStagingError: If the architecture is unsupported or no ISO is
                available for the resolved family.
        """
        family = ISO_BY_ARCH.get(architecture.strip().lower())
        if family is None:
            raise ISOStagingError(
                f"Unsupported architecture '{architecture}'. "
                f"Supported: {', '.join(sorted(ISO_BY_ARCH))}"
            )
        if family not in available:
            raise ISOStagingError(
                f"No ISO available for architecture family '{family}' "
                f"(from architecture '{architecture}')"
            )
        return available[family]

    def stage(self, config: LocalBuildConfig) -> str:
        """
        Copy the installer ISO into ``libvirt_images_dir`` and make it
        libvirt-readable (Req 3.1, 3.2).

        Copies the ISO at ``config.iso_source_path`` into
        ``config.libvirt_images_dir`` (preserving the source file name), then
        sets ownership/permissions that allow libvirt to read it (``chmod
        644``). The destination directory is created if it does not exist.

        Args:
            config: Local build configuration carrying the ISO source path and
                the libvirt images directory.

        Returns:
            The absolute path to the staged ISO.

        Raises:
            ISOStagingError: If the source ISO is absent (Req 3.5) or the copy
                / permission setup fails.
        """
        source = config.iso_source_path
        if not source or not os.path.isfile(source):
            raise ISOStagingError(
                f"Source ISO not found at configured path: {source!r}"
            )

        images_dir = config.libvirt_images_dir
        staged_path = os.path.join(images_dir, os.path.basename(source))

        logger.info("Staging ISO %s -> %s", source, staged_path)

        try:
            os.makedirs(images_dir, exist_ok=True)
            shutil.copy2(source, staged_path)
        except OSError as exc:
            raise ISOStagingError(
                f"Failed to copy ISO {source} into {images_dir}: {exc}"
            ) from exc

        # Set libvirt-readable permissions (world-readable, owner-writable).
        # Run through the injected command runner so the permission step is
        # isolated behind one mockable dependency, consistent with the other
        # tool-invoking components in this package.
        self._runner.run(["chmod", "644", staged_path])

        logger.info("ISO staged at %s", staged_path)
        return staged_path


__all__ = ["ISO_BY_ARCH", "ISOStager"]
