"""
Unit tests for the ImageFinalizer component (local_build, Requirement 8).

Covers:
- build_undefine_argv purity/shape: includes --nvram and NEVER a
  storage-removal flag so the System_Disk is retained (Req 8.2).
- build_convert_argv purity/shape: includes -c for qcow2 compression (Req 8.4).
- finalize happy path: undefine -> qemu-img check -> qemu-img info ->
  qemu-img convert, returning an ImageBuildArtifact whose final_image_path is
  output_dir/final_image_name (Req 8.2-8.4).
- finalize validation failure: a qemu-img check failure (runner raises
  LocalCommandError) causes ImageFinalizeError (Req 8.3, 8.5).
"""

import json
from unittest.mock import MagicMock

import pytest

from proxmox_install_automation.local_build.exceptions import (
    ImageFinalizeError,
    LocalCommandError,
)
from proxmox_install_automation.local_build.image_finalizer import ImageFinalizer
from proxmox_install_automation.local_build.models import (
    ImageBuildArtifact,
    LocalBuildConfig,
)

# Any flag that would cause virsh undefine to delete the System_Disk. None of
# these may ever appear in the undefine argv (Req 8.2).
_STORAGE_REMOVAL_FLAGS = ("--remove-all-storage", "--storage", "--delete-storage")


def _config(**overrides) -> LocalBuildConfig:
    base = dict(
        iso_source_path="/isos/proxmox.iso",
        build_vm_name="proxmox-image-builder",
        final_image_name="proxmox-opcp-final.qcow2",
        output_dir="/var/lib/libvirt/images",
    )
    base.update(overrides)
    return LocalBuildConfig(**base)


def _info_result(virtual_size=68719476736, actual_size=4294967296):
    """A CommandResult-like object whose stdout is qemu-img info JSON."""
    result = MagicMock()
    result.stdout = json.dumps(
        {"virtual-size": virtual_size, "actual-size": actual_size}
    )
    return result


class TestBuildUndefineArgv:
    """build_undefine_argv is pure, includes --nvram, retains the disk."""

    def test_exact_argv(self):
        finalizer = ImageFinalizer(runner=MagicMock())

        argv = finalizer.build_undefine_argv("proxmox-image-builder")

        assert argv == ["virsh", "undefine", "proxmox-image-builder", "--nvram"]

    def test_includes_nvram_flag(self):
        finalizer = ImageFinalizer(runner=MagicMock())

        argv = finalizer.build_undefine_argv("vm-1")

        assert "--nvram" in argv

    def test_omits_storage_removal_flags(self):
        finalizer = ImageFinalizer(runner=MagicMock())

        argv = finalizer.build_undefine_argv("vm-1")

        for flag in _STORAGE_REMOVAL_FLAGS:
            assert flag not in argv

    def test_is_pure_no_runner_interaction(self):
        runner = MagicMock()
        finalizer = ImageFinalizer(runner=runner)

        finalizer.build_undefine_argv("vm-1")

        runner.run.assert_not_called()


class TestBuildConvertArgv:
    """build_convert_argv is pure and enables qcow2 compression via -c."""

    def test_exact_argv(self):
        finalizer = ImageFinalizer(runner=MagicMock())

        argv = finalizer.build_convert_argv("/src.qcow2", "/dst.qcow2")

        assert argv == [
            "qemu-img",
            "convert",
            "-O",
            "qcow2",
            "-c",
            "/src.qcow2",
            "/dst.qcow2",
        ]

    def test_includes_compression_flag(self):
        finalizer = ImageFinalizer(runner=MagicMock())

        argv = finalizer.build_convert_argv("/src.qcow2", "/dst.qcow2")

        assert "-c" in argv

    def test_is_pure_no_runner_interaction(self):
        runner = MagicMock()
        finalizer = ImageFinalizer(runner=runner)

        finalizer.build_convert_argv("/src.qcow2", "/dst.qcow2")

        runner.run.assert_not_called()


def _dispatch_runner(check_raises=False):
    """Build a runner whose .run dispatches by argv.

    Returns the configured runner. When ``check_raises`` is True, the
    ``qemu-img check`` invocation raises LocalCommandError to simulate a
    validation failure.
    """
    info_result = _info_result()

    def _run(argv, *args, **kwargs):
        if argv[:2] == ["qemu-img", "check"]:
            if check_raises:
                raise LocalCommandError("qemu-img check: corrupt qcow2")
            return MagicMock()
        if argv[:2] == ["qemu-img", "info"]:
            return info_result
        # virsh undefine, qemu-img convert, anything else.
        return MagicMock()

    runner = MagicMock()
    runner.run.side_effect = _run
    return runner


class TestFinalize:
    """finalize runs the full sequence and surfaces validation failures."""

    def test_happy_path_sequence_and_artifact(self):
        runner = _dispatch_runner()
        config = _config()
        finalizer = ImageFinalizer(runner=runner)
        disk_path = "/var/lib/libvirt/images/proxmox-image-builder.qcow2"

        artifact = finalizer.finalize(config, disk_path)

        # Returns a populated ImageBuildArtifact.
        assert isinstance(artifact, ImageBuildArtifact)
        assert artifact.final_image_path == (
            "/var/lib/libvirt/images/proxmox-opcp-final.qcow2"
        )
        assert artifact.virtual_size_bytes == 68719476736
        assert artifact.actual_size_bytes == 4294967296
        assert artifact.boot_test_passed is False

        # Verify the ordered sequence of invocations: undefine -> check ->
        # info -> convert.
        argvs = [call.args[0] for call in runner.run.call_args_list]
        assert argvs[0] == [
            "virsh",
            "undefine",
            "proxmox-image-builder",
            "--nvram",
        ]
        assert argvs[1][:2] == ["qemu-img", "check"]
        assert argvs[2][:2] == ["qemu-img", "info"]
        assert argvs[3] == [
            "qemu-img",
            "convert",
            "-O",
            "qcow2",
            "-c",
            disk_path,
            "/var/lib/libvirt/images/proxmox-opcp-final.qcow2",
        ]

    def test_undefine_argv_has_no_storage_removal_during_finalize(self):
        runner = _dispatch_runner()
        finalizer = ImageFinalizer(runner=runner)

        finalizer.finalize(_config(), "/disk.qcow2")

        undefine_argv = runner.run.call_args_list[0].args[0]
        for flag in _STORAGE_REMOVAL_FLAGS:
            assert flag not in undefine_argv

    def test_check_failure_raises_image_finalize_error(self):
        runner = _dispatch_runner(check_raises=True)
        finalizer = ImageFinalizer(runner=runner)

        with pytest.raises(ImageFinalizeError, match="qcow2 validation failed"):
            finalizer.finalize(_config(), "/disk.qcow2")

        # Convert must never run after a validation failure.
        argvs = [call.args[0] for call in runner.run.call_args_list]
        assert not any(argv[:2] == ["qemu-img", "convert"] for argv in argvs)
