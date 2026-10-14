"""
Tests for the BuildVMCreator component (local_build, Requirements 5.1, 5.2, 5.3).

Covers:
- Task 6.2 property test for the virt-install argv (Property 5): for any
  LocalBuildConfig the generated argv contains every mandated resource — the
  VM name, 8 vCPUs, 16384 MiB RAM, host CPU passthrough, UEFI boot, a VirtIO
  system disk, a VirtIO network interface, and the staged ISO as --cdrom.
- Task 6.3 unit tests for BuildVMCreator.create: the injected
  LocalCommandRunner is invoked with the build_argv (virt-install), and a
  runner raising LocalCommandError causes create() to raise BuildVMError.

The LocalCommandRunner is always mocked, so no real virt-install process is
spawned.
"""

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from proxmox_install_automation.local_build.build_vm import BuildVMCreator
from proxmox_install_automation.local_build.exceptions import (
    BuildVMError,
    LocalCommandError,
)
from proxmox_install_automation.local_build.models import LocalBuildConfig


def _config(**overrides) -> LocalBuildConfig:
    """Build a LocalBuildConfig with sensible defaults for these tests."""
    defaults = dict(
        iso_source_path="/isos/proxmox.iso",
        libvirt_images_dir="/var/lib/libvirt/images",
    )
    defaults.update(overrides)
    return LocalBuildConfig(**defaults)


def _adjacent_value(argv, flag):
    """Return the token immediately following ``flag`` in ``argv``.

    Returns None if the flag is absent or has no following token.
    """
    for i, token in enumerate(argv):
        if token == flag and i + 1 < len(argv):
            return argv[i + 1]
    return None


# ---------------------------------------------------------------------------
# Task 6.2 — Property 5: Build VM argv contains all mandated resources
# Feature: proxmox-qcow2-opcp-deployment, Property 5
# Validates: Requirements 5.1, 5.2
# ---------------------------------------------------------------------------


# Path-ish tokens that are safe to interpolate into argv values.
_path_token = st.from_regex(r"/[A-Za-z0-9_./-]{1,40}", fullmatch=True)


@settings(max_examples=100)
@given(
    vcpus=st.integers(min_value=1, max_value=256),
    ram_mib=st.integers(min_value=512, max_value=1_048_576),
    build_vm_name=st.from_regex(r"[A-Za-z0-9_-]{1,30}", fullmatch=True),
    cpu_mode=st.sampled_from(
        ["host-passthrough", "host-model", "custom", "qemu64"]
    ),
    network_model=st.sampled_from(["virtio", "e1000", "rtl8139"]),
    disk_bus=st.sampled_from(["virtio", "sata", "scsi"]),
    iso_path=_path_token,
    disk_path=_path_token,
)
def test_property_build_argv_contains_all_mandated_resources(
    vcpus,
    ram_mib,
    build_vm_name,
    cpu_mode,
    network_model,
    disk_bus,
    iso_path,
    disk_path,
):
    """
    Feature: proxmox-qcow2-opcp-deployment, Property 5

    For any LocalBuildConfig, build_argv produces a virt-install command line
    that contains every mandated resource:
    - the VM name (config.build_vm_name)
    - the vCPU count (config.vcpus)
    - the RAM in MiB (config.ram_mib)
    - the host CPU passthrough mode (config.cpu_mode)
    - UEFI boot (--boot uefi)
    - a VirtIO system disk (bus=<disk_bus> and the disk_path)
    - a VirtIO network interface (model=<network_model>)
    - the staged ISO attached as --cdrom <iso_path>

    Validates: Requirements 5.1, 5.2
    """
    config = _config(
        vcpus=vcpus,
        ram_mib=ram_mib,
        build_vm_name=build_vm_name,
        cpu_mode=cpu_mode,
        network_model=network_model,
        disk_bus=disk_bus,
    )

    argv = BuildVMCreator(MagicMock()).build_argv(config, iso_path, disk_path)

    # The command itself is virt-install.
    assert argv[0] == "virt-install"

    # --name carries the configured build VM name (Req 5.1).
    assert _adjacent_value(argv, "--name") == config.build_vm_name

    # vCPUs and RAM reflect the configured sizing (Req 5.2).
    assert _adjacent_value(argv, "--vcpus") == str(config.vcpus)
    assert _adjacent_value(argv, "--memory") == str(config.ram_mib)

    # Host CPU passthrough mode (Req 5.2).
    assert _adjacent_value(argv, "--cpu") == config.cpu_mode

    # UEFI boot (Req 5.2).
    assert _adjacent_value(argv, "--boot") == "uefi"

    # VirtIO system disk: a --disk value that references the disk_path and the
    # configured bus (Req 5.2).
    disk_value = _adjacent_value(argv, "--disk")
    assert disk_value is not None
    assert disk_path in disk_value
    assert f"bus={config.disk_bus}" in disk_value

    # VirtIO network interface: a --network value with the configured model
    # (Req 5.2).
    network_value = _adjacent_value(argv, "--network")
    assert network_value is not None
    assert f"model={config.network_model}" in network_value

    # The staged ISO is attached as the CD-ROM (Req 5.2).
    assert _adjacent_value(argv, "--cdrom") == iso_path


@settings(max_examples=100)
@given(
    iso_path=_path_token,
    disk_path=_path_token,
)
def test_property_default_config_mandates_8_vcpu_16gb_virtio_uefi(
    iso_path, disk_path
):
    """
    Feature: proxmox-qcow2-opcp-deployment, Property 5

    With the default LocalBuildConfig sizing, the argv mandates exactly the
    designed Build_VM profile: name proxmox-image-builder, 8 vCPUs, 16384 MiB
    RAM, host-passthrough CPU, UEFI boot, a VirtIO system disk, and a VirtIO
    network interface.

    Validates: Requirements 5.1, 5.2
    """
    config = _config()  # defaults: 8 vCPUs, 16384 MiB, virtio, host-passthrough

    argv = BuildVMCreator(MagicMock()).build_argv(config, iso_path, disk_path)

    assert _adjacent_value(argv, "--name") == "proxmox-image-builder"
    assert _adjacent_value(argv, "--vcpus") == "8"
    assert _adjacent_value(argv, "--memory") == "16384"
    assert _adjacent_value(argv, "--cpu") == "host-passthrough"
    assert _adjacent_value(argv, "--boot") == "uefi"
    assert "bus=virtio" in _adjacent_value(argv, "--disk")
    assert "model=virtio" in _adjacent_value(argv, "--network")
    assert _adjacent_value(argv, "--cdrom") == iso_path


# ---------------------------------------------------------------------------
# Task 6.3 — Unit tests for BuildVMCreator.create
# Validates: Requirements 5.1, 5.3
# ---------------------------------------------------------------------------


class TestCreateInvokesRunner:
    def test_create_invokes_runner_with_build_argv(self):
        """create() runs virt-install with exactly build_argv (Req 5.1)."""
        config = _config()
        iso_path = "/var/lib/libvirt/images/proxmox.iso"
        disk_path = "/var/lib/libvirt/images/proxmox-image-builder.qcow2"
        runner = MagicMock()
        creator = BuildVMCreator(runner)

        expected_argv = creator.build_argv(config, iso_path, disk_path)

        creator.create(config, iso_path, disk_path)

        runner.run.assert_called_once()
        call_args, call_kwargs = runner.run.call_args
        passed_argv = call_args[0] if call_args else call_kwargs["argv"]
        assert passed_argv == expected_argv
        # It is a virt-install invocation.
        assert passed_argv[0] == "virt-install"

    def test_create_passes_build_timeout_and_check_true(self):
        """create() forwards build_timeout and check=True to the runner (Req 5.1)."""
        config = _config(build_timeout=4321)
        runner = MagicMock()

        BuildVMCreator(runner).create(config, "/isos/p.iso", "/disks/d.qcow2")

        _, call_kwargs = runner.run.call_args
        assert call_kwargs.get("timeout") == 4321
        assert call_kwargs.get("check") is True


class TestCreateErrorHandling:
    def test_runner_failure_raises_build_vm_error(self):
        """A runner raising LocalCommandError makes create() raise BuildVMError (Req 5.3)."""
        config = _config()
        runner = MagicMock()
        runner.run.side_effect = LocalCommandError("virt-install boom")

        with pytest.raises(BuildVMError) as exc_info:
            BuildVMCreator(runner).create(config, "/isos/p.iso", "/disks/d.qcow2")

        # The error names the build VM for operator diagnosis.
        assert config.build_vm_name in str(exc_info.value)

    def test_build_vm_error_chains_the_underlying_cause(self):
        """BuildVMError preserves the originating LocalCommandError as its cause."""
        config = _config()
        runner = MagicMock()
        original = LocalCommandError("exit 1")
        runner.run.side_effect = original

        with pytest.raises(BuildVMError) as exc_info:
            BuildVMCreator(runner).create(config, "/isos/p.iso", "/disks/d.qcow2")

        assert exc_info.value.__cause__ is original
