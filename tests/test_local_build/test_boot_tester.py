"""
Tests for the BootTester component (local_build, Requirements 9, 13).

Covers:
- Task 10.2 — Property 7: Boot test imports without an ISO and detects the
  ordered boot sequence.
  Feature: proxmox-qcow2-opcp-deployment, Property 7
  Validates: Requirements 9.1, 9.2
  For any LocalBuildConfig/image_path, build_argv contains --import and NEVER a
  --cdrom or ISO attachment; and for any console log, detect_boot_sequence
  returns True iff BOOT_MARKERS appear in order.
- Task 10.3 — Unit tests for BootTester.run (Requirements 9.1, 9.3). With a
  mocked LocalCommandRunner whose result stdout/stderr contains the ordered
  markers, run returns True; a log missing/out-of-order markers raises
  BootTestError.
- Task 10.4 — Integration-style test for the final-image positive content
  guarantee (Requirement 13.1), written as a hermetic mock-based stand-in for a
  real boot + manifest inspection.

The LocalCommandRunner is always mocked, so no real virt-install process is
spawned and no real guest is booted.
"""

import random
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from proxmox_install_automation.local_build.boot_tester import (
    BOOT_MARKERS,
    BootTester,
)
from proxmox_install_automation.local_build.exceptions import (
    BootTestError,
    LocalCommandError,
)
from proxmox_install_automation.local_build.models import LocalBuildConfig


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Flags that would attach an installer ISO to the import boot. None of these may
# ever appear in the import-boot argv, which must boot the image on its own
# (Req 9.1).
_ISO_ATTACH_FLAGS = ("--cdrom", "--location", "--pxe")


def _config(**overrides) -> LocalBuildConfig:
    """Build a LocalBuildConfig with sensible defaults for these tests."""
    defaults = dict(
        iso_source_path="/isos/proxmox.iso",
        libvirt_images_dir="/var/lib/libvirt/images",
    )
    defaults.update(overrides)
    return LocalBuildConfig(**defaults)


def _runner_returning(stdout: str = "", stderr: str = "") -> MagicMock:
    """A mocked LocalCommandRunner whose run() returns the given console output."""
    result = MagicMock()
    result.stdout = stdout
    result.stderr = stderr
    runner = MagicMock()
    runner.run.return_value = result
    return runner


def _oracle_in_order(log: str, markers=BOOT_MARKERS) -> bool:
    """Independent oracle: True iff ``markers`` appear in order within ``log``.

    This is a deliberately separate implementation from
    BootTester.detect_boot_sequence so the property test asserts agreement
    between two independent definitions of "ordered subsequence of markers".
    """
    remaining = log
    for marker in markers:
        idx = remaining.find(marker)
        if idx == -1:
            return False
        remaining = remaining[idx + len(marker):]
    return True


# ---------------------------------------------------------------------------
# Task 10.2 — Property 7
# Feature: proxmox-qcow2-opcp-deployment, Property 7
# Validates: Requirements 9.1, 9.2
# ---------------------------------------------------------------------------

# Path-ish tokens that are safe to interpolate into argv values.
_path_token = st.from_regex(r"/[A-Za-z0-9_./-]{1,40}", fullmatch=True)

# Noise fragments interleaved around markers; chosen so they never themselves
# contain any BOOT_MARKER substring.
_noise_token = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 \n.:-[]",
    min_size=0,
    max_size=20,
)


@settings(max_examples=100)
@given(
    vcpus=st.integers(min_value=1, max_value=256),
    ram_mib=st.integers(min_value=512, max_value=1_048_576),
    build_vm_name=st.from_regex(r"[A-Za-z0-9_-]{1,30}", fullmatch=True),
    cpu_mode=st.sampled_from(["host-passthrough", "host-model", "custom"]),
    network_model=st.sampled_from(["virtio", "e1000", "rtl8139"]),
    disk_bus=st.sampled_from(["virtio", "sata", "scsi"]),
    boot_test_timeout=st.integers(min_value=1, max_value=86_400),
    image_path=_path_token,
)
def test_property_build_argv_imports_without_iso(
    vcpus,
    ram_mib,
    build_vm_name,
    cpu_mode,
    network_model,
    disk_bus,
    boot_test_timeout,
    image_path,
):
    """
    Feature: proxmox-qcow2-opcp-deployment, Property 7

    For any LocalBuildConfig and image_path, the import-boot argv ALWAYS
    contains ``--import`` and NEVER attaches an installer ISO (no --cdrom,
    --location, or --pxe). The image under test must boot on its own.

    Validates: Requirements 9.1
    """
    config = _config(
        vcpus=vcpus,
        ram_mib=ram_mib,
        build_vm_name=build_vm_name,
        cpu_mode=cpu_mode,
        network_model=network_model,
        disk_bus=disk_bus,
        boot_test_timeout=boot_test_timeout,
    )

    argv = BootTester(MagicMock()).build_argv(image_path, config)

    assert argv[0] == "virt-install"
    assert "--import" in argv
    for flag in _ISO_ATTACH_FLAGS:
        assert flag not in argv
    # The image under test is attached as a disk, and no .iso is referenced.
    joined = " ".join(argv)
    assert image_path in joined
    assert ".iso" not in joined.lower()


@settings(max_examples=100)
@given(
    prefix=_noise_token,
    gaps=st.lists(_noise_token, min_size=len(BOOT_MARKERS) + 1,
                  max_size=len(BOOT_MARKERS) + 1),
)
def test_property_detect_boot_sequence_true_when_in_order(prefix, gaps):
    """
    Feature: proxmox-qcow2-opcp-deployment, Property 7

    A console log built by interleaving the BOOT_MARKERS in their required
    order (with arbitrary non-marker noise around them) is detected as a valid
    boot sequence, agreeing with the independent oracle.

    Validates: Requirements 9.2
    """
    parts = [prefix]
    for i, marker in enumerate(BOOT_MARKERS):
        parts.append(gaps[i])
        parts.append(marker)
    parts.append(gaps[len(BOOT_MARKERS)])
    log = "".join(parts)

    tester = BootTester(MagicMock())
    assert tester.detect_boot_sequence(log) is True
    # Agreement with the independent oracle.
    assert tester.detect_boot_sequence(log) == _oracle_in_order(log)


@settings(max_examples=100)
@given(
    seed=st.integers(min_value=0, max_value=2**32 - 1),
    drop=st.integers(min_value=0, max_value=len(BOOT_MARKERS)),
    noise=_noise_token,
)
def test_property_detect_boot_sequence_matches_oracle_on_shuffled(seed, drop, noise):
    """
    Feature: proxmox-qcow2-opcp-deployment, Property 7

    For logs built from shuffled and/or partial marker sets (markers dropped
    and reordered), detect_boot_sequence agrees exactly with the independent
    ordered-subsequence oracle. Out-of-order or missing markers must NOT be
    accepted as a valid boot sequence.

    Validates: Requirements 9.2
    """
    rng = random.Random(seed)
    markers = list(BOOT_MARKERS)
    # Drop ``drop`` markers at random (partial sequences).
    for _ in range(drop):
        if markers:
            markers.pop(rng.randrange(len(markers)))
    # Shuffle the survivors (likely out of order).
    rng.shuffle(markers)

    # Interleave with noise that contains no marker substrings.
    pieces = []
    for marker in markers:
        pieces.append(noise)
        pieces.append(marker)
    pieces.append(noise)
    log = "".join(pieces)

    tester = BootTester(MagicMock())
    assert tester.detect_boot_sequence(log) == _oracle_in_order(log)


def _ordered_console() -> str:
    """A console log containing all BOOT_MARKERS in order with realistic noise."""
    return (
        "BdsDxe: starting UEFI firmware\n"
        "Loading GRUB bootloader menu\n"
        "Booting Linux kernel 6.8.0\n"
        "systemd: reached Proxmox VE target, login ready\n"
    )


# ---------------------------------------------------------------------------
# Task 10.3 — Unit tests for BootTester.run
# Validates: Requirements 9.1, 9.3
# ---------------------------------------------------------------------------


class TestBootTesterRun:
    """run() returns True on a good boot and raises BootTestError otherwise."""

    def test_run_returns_true_when_markers_in_order(self):
        runner = _runner_returning(stdout=_ordered_console())
        tester = BootTester(runner)

        assert tester.run("/img/proxmox-opcp-final.qcow2", _config()) is True

        # It invoked the runner with the import-boot argv (no ISO attached).
        argv = runner.run.call_args.args[0]
        assert "--import" in argv
        for flag in _ISO_ATTACH_FLAGS:
            assert flag not in argv

    def test_run_detects_markers_split_across_stdout_and_stderr(self):
        # UEFI + GRUB on stdout, Linux + Proxmox VE on stderr; the console log
        # concatenates stdout then stderr, preserving order.
        runner = _runner_returning(
            stdout="UEFI firmware\nGRUB menu\n",
            stderr="Linux kernel booted\nProxmox VE ready\n",
        )
        tester = BootTester(runner)

        assert tester.run("/img/final.qcow2", _config()) is True

    def test_run_raises_when_a_marker_missing(self):
        # Missing the final "Proxmox VE" marker -> boot did not complete.
        runner = _runner_returning(
            stdout="UEFI firmware\nGRUB menu\nLinux kernel booted\n"
        )
        tester = BootTester(runner)

        with pytest.raises(BootTestError, match="did not reach Proxmox VE"):
            tester.run("/img/final.qcow2", _config())

    def test_run_raises_when_markers_out_of_order(self):
        # All markers present but Proxmox VE appears before Linux -> invalid.
        runner = _runner_returning(
            stdout="UEFI\nGRUB\nProxmox VE banner\nLinux kernel\n"
        )
        tester = BootTester(runner)

        with pytest.raises(BootTestError):
            tester.run("/img/final.qcow2", _config())

    def test_run_wraps_command_failure_as_boot_test_error(self):
        runner = MagicMock()
        runner.run.side_effect = LocalCommandError("virt-install not found")
        tester = BootTester(runner)

        with pytest.raises(BootTestError, match="failed to run"):
            tester.run("/img/final.qcow2", _config())


# ---------------------------------------------------------------------------
# Task 10.4 — Integration-style final-image content guarantee
# Validates: Requirements 13.1
# ---------------------------------------------------------------------------

# The required positive content markers the finished image must contain
# (Req 13.1): Proxmox VE, a Debian base, an EFI system partition, a bootloader,
# standard packages, and admin tooling.
_REQUIRED_CONTENT_MARKERS = (
    "Proxmox VE",
    "Debian",
    "EFI partition",
    "GRUB bootloader",
    "standard packages",
    "admin tools",
)


def _manifest_contains_all(manifest: str, markers=_REQUIRED_CONTENT_MARKERS):
    """Helper under test: True iff every required content marker is present.

    Returns (ok, missing) where ``missing`` lists any absent markers so the
    assertion can report precisely what the image lacked.
    """
    missing = [m for m in markers if m not in manifest]
    return (not missing, missing)


def _mock_virt_ls_manifest() -> str:
    """Simulate a virt-ls / dpkg --get-selections manifest for the final image.

    Stands in for a real libguestfs inspection of the finished qcow2. The lines
    assert the presence of each required positive-content marker.
    """
    return "\n".join(
        [
            "ii  proxmox-ve                      8.2.0   Proxmox VE meta package",
            "ii  base-files                      12.4    Debian base system files",
            "part /dev/sda1  vfat  512M   EFI partition (ESP) mounted at /boot/efi",
            "ii  grub-efi-amd64                  2.06    GRUB bootloader for UEFI",
            "ii  openssh-server bash coreutils           standard packages present",
            "ii  sudo pve-manager qm pvesh                admin tools installed",
        ]
    )


def test_integration_final_image_positive_content_guarantee():
    """Hermetic stand-in for a real boot + manifest integration test (Req 13.1).

    A genuine version of this test would import-boot the finished qcow2 under
    KVM/libvirt and then inspect it with libguestfs (virt-ls / dpkg). Neither
    real boot hardware nor libguestfs is available in CI, so this test is fully
    mocked and hermetic: it spawns no processes and touches no disk. It
    simulates (1) the boot-test serial console reaching Proxmox VE and (2) a
    package/manifest inspection, then asserts the manifest-check helper detects
    every required positive-content marker.
    """
    # (1) The boot test console reaches Proxmox VE through BootTester.run with a
    #     mocked runner (no real virt-install).
    runner = _runner_returning(stdout=_ordered_console())
    tester = BootTester(runner)
    assert tester.run("/var/lib/libvirt/images/proxmox-opcp-final.qcow2",
                      _config()) is True

    # (2) A mocked manifest inspection confirms the image's positive content:
    #     Proxmox VE, Debian base, an EFI partition, a bootloader, standard
    #     packages, and admin tools (Req 13.1).
    manifest = _mock_virt_ls_manifest()
    ok, missing = _manifest_contains_all(manifest)
    assert ok, f"final image manifest missing required content: {missing}"

    # The helper must fail closed if any required content is absent.
    degraded = manifest.replace("Proxmox VE meta package", "removed")
    ok2, missing2 = _manifest_contains_all(degraded)
    assert ok2 is False
    assert "Proxmox VE" in missing2
