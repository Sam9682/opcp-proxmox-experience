"""
Tests for the SystemDiskCreator component (local_build, Requirements 4.1, 4.2, 4.3).

Covers:
- build_argv is pure and produces exactly
  ['qemu-img', 'create', '-f', 'qcow2', path, '<size>G'] with 64G sizing.
- create() computes the disk path from libvirt_images_dir + system_disk_name,
  invokes the injected runner with that argv, and returns the path.
- a runner that raises LocalCommandError causes create() to raise SystemDiskError.
"""

from posixpath import join as posix_join
from unittest.mock import MagicMock

import pytest

from proxmox_install_automation.local_build.exceptions import (
    LocalCommandError,
    SystemDiskError,
)
from proxmox_install_automation.local_build.models import LocalBuildConfig
from proxmox_install_automation.local_build.system_disk import SystemDiskCreator


def _config(**overrides) -> LocalBuildConfig:
    """Build a LocalBuildConfig with sensible defaults for these tests."""
    defaults = dict(
        iso_source_path="/isos/proxmox.iso",
        libvirt_images_dir="/var/lib/libvirt/images",
        system_disk_name="proxmox-image-builder.qcow2",
        system_disk_size_gb=64,
    )
    defaults.update(overrides)
    return LocalBuildConfig(**defaults)


class TestBuildArgv:
    def test_build_argv_shape_and_64g_sizing(self):
        path = "/var/lib/libvirt/images/proxmox-image-builder.qcow2"
        argv = SystemDiskCreator(MagicMock()).build_argv(path, 64)
        assert argv == ["qemu-img", "create", "-f", "qcow2", path, "64G"]

    def test_build_argv_sizing_reflects_size_gb(self):
        path = "/tmp/disk.qcow2"
        argv = SystemDiskCreator(MagicMock()).build_argv(path, 128)
        assert argv == ["qemu-img", "create", "-f", "qcow2", path, "128G"]

    def test_build_argv_is_pure_does_not_touch_runner(self):
        runner = MagicMock()
        SystemDiskCreator(runner).build_argv("/tmp/disk.qcow2", 64)
        runner.run.assert_not_called()


class TestCreate:
    def test_create_computes_path_invokes_runner_and_returns_path(self):
        config = _config()
        expected_path = posix_join(
            config.libvirt_images_dir, config.system_disk_name
        )
        runner = MagicMock()

        result = SystemDiskCreator(runner).create(config)

        assert result == expected_path
        runner.run.assert_called_once()
        call_args, call_kwargs = runner.run.call_args
        passed_argv = call_args[0] if call_args else call_kwargs["argv"]
        assert passed_argv == [
            "qemu-img",
            "create",
            "-f",
            "qcow2",
            expected_path,
            "64G",
        ]

    def test_create_uses_build_timeout_and_check_true(self):
        config = _config(build_timeout=1234)
        runner = MagicMock()

        SystemDiskCreator(runner).create(config)

        _, call_kwargs = runner.run.call_args
        assert call_kwargs.get("timeout") == 1234
        assert call_kwargs.get("check") is True

    def test_create_respects_custom_dir_and_name(self):
        config = _config(
            libvirt_images_dir="/custom/images",
            system_disk_name="my-disk.qcow2",
        )
        runner = MagicMock()

        result = SystemDiskCreator(runner).create(config)

        assert result == "/custom/images/my-disk.qcow2"
        passed_argv = runner.run.call_args[0][0]
        assert passed_argv[4] == "/custom/images/my-disk.qcow2"
        assert passed_argv[5] == "64G"

    def test_create_wraps_runner_failure_in_system_disk_error(self):
        config = _config()
        runner = MagicMock()
        runner.run.side_effect = LocalCommandError("qemu-img boom")

        with pytest.raises(SystemDiskError) as exc_info:
            SystemDiskCreator(runner).create(config)

        expected_path = posix_join(
            config.libvirt_images_dir, config.system_disk_name
        )
        assert expected_path in str(exc_info.value)
