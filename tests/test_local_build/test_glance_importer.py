"""
Tests for the GlanceImporter component (local_build, Requirement 10).

Covers:
- build_import_request purity/shape: disk_format=qcow2, container_format=bare,
  and NEVER kernel_id / ramdisk_id (Req 10.1, 10.2).
- import_image success path: creates image and returns id once ACTIVE (Req 10.3).
- import_image error paths: creation failure, ERROR status, and timeout
  raising GlanceImportError (Req 10.4).
"""

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, strategies as st

from proxmox_install_automation.local_build.exceptions import GlanceImportError
from proxmox_install_automation.local_build.glance_importer import GlanceImporter
from proxmox_install_automation.local_build.models import DeployConfig
from proxmox_install_automation.models import Credentials


def _credentials() -> Credentials:
    return Credentials(auth_url="https://keystone.example/v3", region="RegionOne")


def _deploy_config(**overrides) -> DeployConfig:
    base = dict(
        final_image_path="/var/lib/libvirt/images/proxmox-opcp-final.qcow2",
        glance_image_name="proxmox-opcp",
        credentials=_credentials(),
        ironic_node="node-1",
        bare_metal_flavor="baremetal",
        glance_timeout=30,
    )
    base.update(overrides)
    return DeployConfig(**base)


class TestBuildImportRequest:
    """build_import_request is pure and produces a whole-disk request."""

    def test_disk_and_container_formats(self):
        importer = GlanceImporter(auth_manager=MagicMock())
        req = importer.build_import_request("img", "/tmp/img.qcow2")

        assert req["disk_format"] == "qcow2"
        assert req["container_format"] == "bare"
        assert req["name"] == "img"
        assert req["filename"] == "/tmp/img.qcow2"

    def test_never_contains_kernel_or_ramdisk(self):
        importer = GlanceImporter(auth_manager=MagicMock())
        req = importer.build_import_request("img", "/tmp/img.qcow2")

        assert "kernel_id" not in req
        assert "ramdisk_id" not in req

    def test_is_pure_no_auth_interaction(self):
        """Building the request must not touch the auth manager/connection."""
        auth = MagicMock()
        importer = GlanceImporter(auth_manager=auth)

        importer.build_import_request("img", "/tmp/img.qcow2")

        auth.authenticate.assert_not_called()

    # Feature: proxmox-qcow2-opcp-deployment, Property 8
    @given(
        name=st.text(min_size=1, max_size=40),
        path=st.text(min_size=1, max_size=120),
    )
    @settings(max_examples=100)
    def test_property_whole_disk_invariant(self, name, path):
        """Validates: Requirements 10.1, 10.2

        For any name/path, the request is a whole-disk qcow2/bare request and
        never carries a kernel_id or ramdisk_id key.
        """
        importer = GlanceImporter(auth_manager=MagicMock())
        req = importer.build_import_request(name, path)

        assert req["disk_format"] == "qcow2"
        assert req["container_format"] == "bare"
        assert "kernel_id" not in req
        assert "ramdisk_id" not in req
        # Purity: calling twice yields an equal result.
        assert importer.build_import_request(name, path) == req


def _importer_with_statuses(statuses):
    """Build a GlanceImporter whose connection returns the given image
    statuses in sequence on get_image()."""
    created = MagicMock()
    created.id = "img-123"

    connection = MagicMock()
    connection.image.create_image.return_value = created

    status_images = []
    for s in statuses:
        img = MagicMock()
        img.status = s
        status_images.append(img)
    connection.image.get_image.side_effect = status_images

    auth = MagicMock()
    auth.authenticate.return_value = connection

    return GlanceImporter(auth_manager=auth), connection


class TestImportImage:
    """import_image creates the image and waits for ACTIVE (Req 10.3, 10.4)."""

    def test_returns_id_when_active(self, monkeypatch):
        monkeypatch.setattr(
            "proxmox_install_automation.local_build.glance_importer.time.sleep",
            lambda _s: None,
        )
        importer, connection = _importer_with_statuses(["queued", "active"])

        image_id = importer.import_image(_deploy_config())

        assert image_id == "img-123"
        # Verify the create call used whole-disk formats and no kernel/ramdisk.
        _, kwargs = connection.image.create_image.call_args
        assert kwargs["disk_format"] == "qcow2"
        assert kwargs["container_format"] == "bare"
        assert "kernel_id" not in kwargs
        assert "ramdisk_id" not in kwargs

    def test_raises_on_create_failure(self):
        connection = MagicMock()
        connection.image.create_image.side_effect = RuntimeError("boom")
        auth = MagicMock()
        auth.authenticate.return_value = connection
        importer = GlanceImporter(auth_manager=auth)

        with pytest.raises(GlanceImportError, match="Failed to create Glance image"):
            importer.import_image(_deploy_config())

    def test_raises_on_error_status(self, monkeypatch):
        monkeypatch.setattr(
            "proxmox_install_automation.local_build.glance_importer.time.sleep",
            lambda _s: None,
        )
        importer, _ = _importer_with_statuses(["queued", "error"])

        with pytest.raises(GlanceImportError, match="ERROR status"):
            importer.import_image(_deploy_config())

    def test_raises_on_timeout(self, monkeypatch):
        # Simulate the clock jumping past the timeout after the first poll so
        # the loop exits without ever seeing ACTIVE.
        times = iter([0.0, 0.0, 1000.0, 2000.0, 3000.0])
        monkeypatch.setattr(
            "proxmox_install_automation.local_build.glance_importer.time.time",
            lambda: next(times),
        )
        monkeypatch.setattr(
            "proxmox_install_automation.local_build.glance_importer.time.sleep",
            lambda _s: None,
        )
        importer, _ = _importer_with_statuses(["queued", "saving", "saving"])

        with pytest.raises(GlanceImportError, match="did not reach ACTIVE"):
            importer.import_image(_deploy_config(glance_timeout=30))


class TestActiveStatusWaitPolling:
    """The ACTIVE wait polls get_image repeatedly until ACTIVE (Req 10.3)."""

    def test_polls_get_image_multiple_times_before_active(self, monkeypatch):
        """Validates: Requirements 10.3

        The wait loop must query image status repeatedly, not just once, so a
        slow import that passes through several non-ACTIVE states still
        resolves to the image id once ACTIVE is observed.
        """
        monkeypatch.setattr(
            "proxmox_install_automation.local_build.glance_importer.time.sleep",
            lambda _s: None,
        )
        # Three non-ACTIVE polls before the terminal ACTIVE poll.
        importer, connection = _importer_with_statuses(
            ["queued", "saving", "saving", "active"]
        )

        image_id = importer.import_image(_deploy_config())

        assert image_id == "img-123"
        # The loop queried status once per emitted state (4 polls total),
        # proving it re-queries instead of trusting the first result.
        assert connection.image.get_image.call_count == 4
        # Every poll targeted the created image id.
        for call in connection.image.get_image.call_args_list:
            assert call.args[0] == "img-123"

    def test_sleeps_between_non_active_polls(self, monkeypatch):
        """Validates: Requirements 10.3

        Between non-ACTIVE polls the importer backs off via time.sleep, so the
        number of sleeps equals the number of non-ACTIVE statuses seen before
        ACTIVE (here: two).
        """
        sleep_calls = []
        monkeypatch.setattr(
            "proxmox_install_automation.local_build.glance_importer.time.sleep",
            lambda s: sleep_calls.append(s),
        )
        importer, _ = _importer_with_statuses(["queued", "saving", "active"])

        image_id = importer.import_image(_deploy_config())

        assert image_id == "img-123"
        # Two non-ACTIVE statuses -> two sleeps before ACTIVE short-circuits.
        assert len(sleep_calls) == 2
