"""
Tests for the FirstBootScaffolder component (local_build, Requirement 12).

Covers:
- generate() produces an artifact in each supported format: cloud-init,
  systemd first-boot, and Ansible (Req 12.1).
- Every generated artifact contains a scaffolding section for every entry in
  REQUIRED_TOPICS: hostname, IP, DNS, NTP, network interfaces, vmbr0 bridge,
  bonds, VLANs, storage network, cluster/Corosync, ZFS/Ceph (Req 12.2, 12.3).
- generate() raises FirstBootScaffoldError on an unsupported format and when
  the output directory cannot be written.
"""

import os

import pytest
from hypothesis import given, settings, strategies as st

from proxmox_install_automation.local_build.exceptions import FirstBootScaffoldError
from proxmox_install_automation.local_build.firstboot_scaffolder import (
    REQUIRED_TOPICS,
    FirstBootScaffolder,
)
from proxmox_install_automation.local_build.models import DeployConfig
from proxmox_install_automation.models import Credentials

SUPPORTED_FORMATS = ("cloud-init", "systemd", "ansible")


def _credentials() -> Credentials:
    return Credentials(auth_url="https://keystone.example/v3", region="RegionOne")


def _deploy_config(output_dir: str, **overrides) -> DeployConfig:
    base = dict(
        final_image_path="/var/lib/libvirt/images/proxmox-opcp-final.qcow2",
        glance_image_name="proxmox-opcp",
        credentials=_credentials(),
        ironic_node="node-1",
        bare_metal_flavor="baremetal",
        firstboot_output_dir=output_dir,
    )
    base.update(overrides)
    return DeployConfig(**base)


class TestGenerate:
    """generate() writes a scaffolding artifact covering all topics."""

    @pytest.mark.parametrize("fmt", SUPPORTED_FORMATS)
    def test_writes_artifact_for_each_format(self, tmp_path, fmt):
        out = str(tmp_path / "firstboot")
        scaffolder = FirstBootScaffolder()

        paths = scaffolder.generate(_deploy_config(out, firstboot_format=fmt))

        assert len(paths) == 1
        assert os.path.exists(paths[0])
        assert paths[0].startswith(out)

    @pytest.mark.parametrize("fmt", SUPPORTED_FORMATS)
    def test_artifact_covers_every_required_topic(self, tmp_path, fmt):
        out = str(tmp_path / "firstboot")
        scaffolder = FirstBootScaffolder()

        paths = scaffolder.generate(_deploy_config(out, firstboot_format=fmt))
        content = open(paths[0], encoding="utf-8").read()

        missing = [topic for topic in REQUIRED_TOPICS if topic not in content]
        assert not missing, f"{fmt} artifact missing topics: {missing}"

    def test_creates_output_directory_if_absent(self, tmp_path):
        out = str(tmp_path / "nested" / "firstboot")
        scaffolder = FirstBootScaffolder()

        paths = scaffolder.generate(_deploy_config(out, firstboot_format="cloud-init"))

        assert os.path.isdir(out)
        assert os.path.exists(paths[0])

    def test_required_topics_has_all_expected_entries(self):
        assert REQUIRED_TOPICS == (
            "hostname",
            "ip_address",
            "dns",
            "ntp",
            "network_interfaces",
            "vmbr0_bridge",
            "bonds",
            "vlans",
            "storage_network",
            "cluster_corosync",
            "zfs_ceph",
        )

    def test_raises_on_unsupported_format(self, tmp_path):
        scaffolder = FirstBootScaffolder()

        with pytest.raises(FirstBootScaffoldError, match="Unsupported first-boot format"):
            scaffolder.generate(
                _deploy_config(str(tmp_path), firstboot_format="bogus")
            )

    def test_raises_when_output_dir_cannot_be_created(self, tmp_path):
        # A regular file occupies the path where a directory is expected, so
        # os.makedirs fails and generate() surfaces FirstBootScaffoldError.
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir")
        out = str(blocker / "firstboot")
        scaffolder = FirstBootScaffolder()

        with pytest.raises(FirstBootScaffoldError):
            scaffolder.generate(_deploy_config(out, firstboot_format="cloud-init"))


class TestGenerateProperty:
    """Property: any supported format yields full-topic scaffolding (Req 12)."""

    # Feature: proxmox-qcow2-opcp-deployment, Property 9
    @settings(max_examples=100)
    @given(fmt=st.sampled_from(SUPPORTED_FORMATS))
    def test_property_all_topics_present_for_any_format(self, tmp_path_factory, fmt):
        """Validates: Requirements 12.2, 12.3

        For every supported format, the generated artifact exists and contains
        a scaffolding reference to every REQUIRED_TOPICS entry.
        """
        out = str(tmp_path_factory.mktemp("firstboot"))
        scaffolder = FirstBootScaffolder()

        paths = scaffolder.generate(_deploy_config(out, firstboot_format=fmt))

        assert len(paths) == 1 and os.path.exists(paths[0])
        content = open(paths[0], encoding="utf-8").read()
        assert all(topic in content for topic in REQUIRED_TOPICS)
