"""
Tests for the ISOStager component (local_build, Requirements 3.1-3.5).

Covers:
- Task 4.2 property test for architecture-to-ISO selection (Property 4).
- Task 4.3 unit tests for ISOStager.stage: copy into libvirt_images_dir,
  libvirt-readable permissions via the runner, returned staged path, and the
  missing-source-ISO error path.

All filesystem effects use pytest's tmp_path, and the LocalCommandRunner is
mocked so no real chmod process is spawned.
"""

import os
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from proxmox_install_automation.local_build.exceptions import ISOStagingError
from proxmox_install_automation.local_build.iso_stager import ISO_BY_ARCH, ISOStager
from proxmox_install_automation.local_build.models import LocalBuildConfig


# ---------------------------------------------------------------------------
# Task 4.2 — Property 4: ISO architecture selection is a total mapping
# Feature: proxmox-qcow2-opcp-deployment, Property 4
# Validates: Requirements 3.3, 3.4
# ---------------------------------------------------------------------------

# The supported architecture tokens the mapping must resolve totally.
SUPPORTED_ARCH_TOKENS = ["x86_64", "amd64", "arm64"]


@settings(max_examples=100)
@given(architecture=st.sampled_from(SUPPORTED_ARCH_TOKENS))
def test_property_select_iso_is_total_mapping(architecture):
    """
    Feature: proxmox-qcow2-opcp-deployment, Property 4

    For any supported architecture token (x86_64, amd64, arm64), select_iso
    returns the ISO entry whose architecture family matches the token.

    Validates: Requirements 3.3, 3.4
    """
    stager = ISOStager(runner=MagicMock())

    # Build an `available` map keyed by every ISO family, with a distinct,
    # recognizable entry per family so we can assert the family→entry link.
    available = {
        family: f"proxmox-ve_{family}.iso" for family in set(ISO_BY_ARCH.values())
    }

    expected_family = ISO_BY_ARCH[architecture]
    result = stager.select_iso(architecture, available)

    # The returned entry is exactly the one for the resolved architecture family.
    assert result == available[expected_family]


@settings(max_examples=100)
@given(
    architecture=st.sampled_from(SUPPORTED_ARCH_TOKENS),
    casing=st.sampled_from(["lower", "upper", "pad"]),
)
def test_property_select_iso_normalizes_token(architecture, casing):
    """
    Feature: proxmox-qcow2-opcp-deployment, Property 4

    Token normalization (case/whitespace) still resolves to the same family's
    ISO entry across all supported tokens.

    Validates: Requirements 3.3, 3.4
    """
    stager = ISOStager(runner=MagicMock())
    available = {
        family: f"proxmox-ve_{family}.iso" for family in set(ISO_BY_ARCH.values())
    }

    if casing == "lower":
        token = architecture.lower()
    elif casing == "upper":
        token = architecture.upper()
    else:
        token = f"  {architecture}  "

    expected_family = ISO_BY_ARCH[architecture]
    assert stager.select_iso(token, available) == available[expected_family]


# ---------------------------------------------------------------------------
# Task 4.3 — Unit tests for ISOStager.stage
# Validates: Requirements 3.1, 3.2, 3.5
# ---------------------------------------------------------------------------


def _make_source_iso(tmp_path, name="proxmox-ve_amd64.iso", content=b"ISO-DATA"):
    """Create a real source ISO file under tmp_path and return its path."""
    source = tmp_path / name
    source.write_bytes(content)
    return str(source)


class TestStageSuccess:
    def test_stage_copies_iso_into_images_dir(self, tmp_path):
        """stage copies the source ISO into libvirt_images_dir (Req 3.1)."""
        source = _make_source_iso(tmp_path)
        images_dir = tmp_path / "images"
        runner = MagicMock()
        config = LocalBuildConfig(
            iso_source_path=source,
            libvirt_images_dir=str(images_dir),
        )

        staged = ISOStager(runner=runner).stage(config)

        expected = images_dir / os.path.basename(source)
        assert os.path.isfile(expected)
        assert expected.read_bytes() == b"ISO-DATA"
        # The staged path points at the copied file inside images_dir.
        assert staged == str(expected)

    def test_stage_returns_staged_path(self, tmp_path):
        """stage returns the absolute path to the staged ISO (Req 3.1)."""
        source = _make_source_iso(tmp_path, name="installer.iso")
        images_dir = tmp_path / "libvirt-images"
        config = LocalBuildConfig(
            iso_source_path=source,
            libvirt_images_dir=str(images_dir),
        )

        staged = ISOStager(runner=MagicMock()).stage(config)

        assert staged == str(images_dir / "installer.iso")

    def test_stage_sets_libvirt_readable_permissions_via_runner(self, tmp_path):
        """stage sets libvirt-readable perms via chmod 644 through the runner (Req 3.2)."""
        source = _make_source_iso(tmp_path)
        images_dir = tmp_path / "images"
        runner = MagicMock()
        config = LocalBuildConfig(
            iso_source_path=source,
            libvirt_images_dir=str(images_dir),
        )

        staged = ISOStager(runner=runner).stage(config)

        runner.run.assert_called_once_with(["chmod", "644", staged])

    def test_stage_creates_missing_images_dir(self, tmp_path):
        """stage creates the destination directory when it does not exist (Req 3.1)."""
        source = _make_source_iso(tmp_path)
        images_dir = tmp_path / "nested" / "images"
        assert not images_dir.exists()
        config = LocalBuildConfig(
            iso_source_path=source,
            libvirt_images_dir=str(images_dir),
        )

        ISOStager(runner=MagicMock()).stage(config)

        assert images_dir.is_dir()


class TestStageMissingSource:
    def test_missing_source_iso_raises(self, tmp_path):
        """A missing source ISO raises ISOStagingError (Req 3.5)."""
        missing = str(tmp_path / "does-not-exist.iso")
        images_dir = tmp_path / "images"
        runner = MagicMock()
        config = LocalBuildConfig(
            iso_source_path=missing,
            libvirt_images_dir=str(images_dir),
        )

        with pytest.raises(ISOStagingError):
            ISOStager(runner=runner).stage(config)

        # No permission step should run when staging fails up front.
        runner.run.assert_not_called()

    def test_directory_as_source_raises(self, tmp_path):
        """A source path that is a directory (not a file) raises ISOStagingError (Req 3.5)."""
        a_dir = tmp_path / "a-dir"
        a_dir.mkdir()
        config = LocalBuildConfig(
            iso_source_path=str(a_dir),
            libvirt_images_dir=str(tmp_path / "images"),
        )

        with pytest.raises(ISOStagingError):
            ISOStager(runner=MagicMock()).stage(config)
