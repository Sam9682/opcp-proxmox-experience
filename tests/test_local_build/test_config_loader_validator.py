"""
Unit tests for the local_build YAML config loader and validator
(local_build, Requirement 14.3).

Covers:
- load_local_build_config parsing valid YAML into the right dataclasses with
  expected values, including the optional openstack + deploy sections.
- A config without a ``deploy`` section yields ``deploy_config is None``.
- Missing file / empty file / invalid YAML raise the typed LocalBuildError.
- LocalBuildConfigValidator.validate raises ConfigurationError for invalid
  inputs (empty required fields, bad architecture, non-positive numeric
  constraints, bad firstboot_format) and aggregates multiple failures into a
  single message.
"""

import textwrap

import pytest

from proxmox_install_automation.exceptions import ConfigurationError
from proxmox_install_automation.local_build.config_loader import (
    load_local_build_config,
)
from proxmox_install_automation.local_build.config_validator import (
    LocalBuildConfigValidator,
)
from proxmox_install_automation.local_build.exceptions import LocalBuildError
from proxmox_install_automation.local_build.models import (
    DeployConfig,
    LocalBuildConfig,
)
from proxmox_install_automation.models import Credentials


def _write(tmp_path, text, name="config.yaml"):
    """Write YAML text to a temp file and return its path as a string."""
    path = tmp_path / name
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# load_local_build_config - valid YAML
# ---------------------------------------------------------------------------


def test_loads_local_build_section_into_dataclass(tmp_path):
    """A valid local_build section loads into a LocalBuildConfig with values."""
    path = _write(
        tmp_path,
        """
        local_build:
          iso_source_path: /isos/proxmox.iso
          architecture: amd64
          libvirt_images_dir: /custom/images
          system_disk_size_gb: 128
          system_disk_name: disk.qcow2
          build_vm_name: my-builder
          vcpus: 4
          ram_mib: 8192
          final_image_name: final.qcow2
          output_dir: /out
          build_timeout: 1200
          convert_timeout: 900
          boot_test_timeout: 300
          assume_install_complete: true
        """,
    )

    local_build_config, deploy_config = load_local_build_config(path)

    assert isinstance(local_build_config, LocalBuildConfig)
    assert local_build_config.iso_source_path == "/isos/proxmox.iso"
    assert local_build_config.architecture == "amd64"
    assert local_build_config.libvirt_images_dir == "/custom/images"
    assert local_build_config.system_disk_size_gb == 128
    assert local_build_config.system_disk_name == "disk.qcow2"
    assert local_build_config.build_vm_name == "my-builder"
    assert local_build_config.vcpus == 4
    assert local_build_config.ram_mib == 8192
    assert local_build_config.final_image_name == "final.qcow2"
    assert local_build_config.output_dir == "/out"
    assert local_build_config.build_timeout == 1200
    assert local_build_config.convert_timeout == 900
    assert local_build_config.boot_test_timeout == 300
    assert local_build_config.assume_install_complete is True
    # No deploy section -> None
    assert deploy_config is None


def test_missing_fields_fall_back_to_dataclass_defaults(tmp_path):
    """Only iso_source_path given; everything else uses documented defaults."""
    path = _write(
        tmp_path,
        """
        local_build:
          iso_source_path: /isos/proxmox.iso
        """,
    )

    local_build_config, deploy_config = load_local_build_config(path)

    defaults = LocalBuildConfig(iso_source_path="")
    assert local_build_config.iso_source_path == "/isos/proxmox.iso"
    assert local_build_config.architecture == defaults.architecture
    assert (
        local_build_config.libvirt_images_dir == defaults.libvirt_images_dir
    )
    assert (
        local_build_config.system_disk_size_gb == defaults.system_disk_size_gb
    )
    assert local_build_config.vcpus == defaults.vcpus
    assert local_build_config.ram_mib == defaults.ram_mib
    assert (
        local_build_config.assume_install_complete
        == defaults.assume_install_complete
    )
    assert deploy_config is None


def test_loads_deploy_and_openstack_sections(tmp_path):
    """A deploy + openstack section builds a DeployConfig with Credentials."""
    path = _write(
        tmp_path,
        """
        local_build:
          iso_source_path: /isos/proxmox.iso

        openstack:
          auth_url: https://keystone.example.com/v3
          region: RegionOne
          application_credential_id: ac-id
          application_credential_secret: ac-secret

        deploy:
          final_image_path: /out/final.qcow2
          glance_image_name: proxmox-opcp
          ironic_node: node-1
          bare_metal_flavor: baremetal.large
          network_name: Internal-Net
          glance_timeout: 600
          deploy_timeout: 1200
          firstboot_format: systemd
          firstboot_output_dir: /out/firstboot
        """,
    )

    local_build_config, deploy_config = load_local_build_config(path)

    assert isinstance(local_build_config, LocalBuildConfig)
    assert isinstance(deploy_config, DeployConfig)
    assert deploy_config.final_image_path == "/out/final.qcow2"
    assert deploy_config.glance_image_name == "proxmox-opcp"
    assert deploy_config.ironic_node == "node-1"
    assert deploy_config.bare_metal_flavor == "baremetal.large"
    assert deploy_config.network_name == "Internal-Net"
    assert deploy_config.glance_timeout == 600
    assert deploy_config.deploy_timeout == 1200
    assert deploy_config.firstboot_format == "systemd"
    assert deploy_config.firstboot_output_dir == "/out/firstboot"

    assert isinstance(deploy_config.credentials, Credentials)
    assert deploy_config.credentials.auth_url == (
        "https://keystone.example.com/v3"
    )
    assert deploy_config.credentials.region == "RegionOne"
    assert deploy_config.credentials.application_credential_id == "ac-id"
    assert (
        deploy_config.credentials.application_credential_secret == "ac-secret"
    )


def test_missing_deploy_section_yields_none(tmp_path):
    """A config with openstack but no deploy section yields deploy_config None."""
    path = _write(
        tmp_path,
        """
        local_build:
          iso_source_path: /isos/proxmox.iso

        openstack:
          auth_url: https://keystone.example.com/v3
          region: RegionOne
        """,
    )

    _, deploy_config = load_local_build_config(path)
    assert deploy_config is None


# ---------------------------------------------------------------------------
# load_local_build_config - error paths (typed LocalBuildError)
# ---------------------------------------------------------------------------


def test_missing_file_raises_local_build_error(tmp_path):
    """A non-existent path raises LocalBuildError."""
    missing = str(tmp_path / "does_not_exist.yaml")
    with pytest.raises(LocalBuildError):
        load_local_build_config(missing)


def test_empty_file_raises_local_build_error(tmp_path):
    """An empty YAML file raises LocalBuildError."""
    path = _write(tmp_path, "")
    with pytest.raises(LocalBuildError):
        load_local_build_config(path)


def test_invalid_yaml_raises_local_build_error(tmp_path):
    """Malformed YAML raises LocalBuildError."""
    path = _write(
        tmp_path,
        """
        local_build:
          iso_source_path: "/isos/proxmox.iso
          architecture: [unclosed
        """,
    )
    with pytest.raises(LocalBuildError):
        load_local_build_config(path)


# ---------------------------------------------------------------------------
# LocalBuildConfigValidator - valid config passes
# ---------------------------------------------------------------------------


def _valid_config(**overrides):
    base = dict(
        iso_source_path="/isos/proxmox.iso",
        architecture="x86_64",
        libvirt_images_dir="/var/lib/libvirt/images",
        system_disk_size_gb=64,
        system_disk_name="disk.qcow2",
        build_vm_name="builder",
        vcpus=8,
        ram_mib=16384,
        final_image_name="final.qcow2",
        output_dir="/out",
    )
    base.update(overrides)
    return LocalBuildConfig(**base)


def test_validator_accepts_valid_config():
    """A well-formed LocalBuildConfig passes without raising."""
    LocalBuildConfigValidator().validate(_valid_config())


def test_validator_accepts_valid_config_with_deploy():
    """A valid config + valid deploy config passes without raising."""
    deploy = DeployConfig(
        final_image_path="/out/final.qcow2",
        glance_image_name="proxmox-opcp",
        credentials=Credentials(
            auth_url="https://keystone.example.com/v3",
            region="RegionOne",
        ),
        ironic_node="node-1",
        bare_metal_flavor="baremetal.large",
    )
    LocalBuildConfigValidator().validate(_valid_config(), deploy_config=deploy)


# ---------------------------------------------------------------------------
# LocalBuildConfigValidator - invalid inputs raise ConfigurationError
# ---------------------------------------------------------------------------


def test_validator_rejects_empty_required_field():
    """An empty required field raises ConfigurationError."""
    with pytest.raises(ConfigurationError) as exc:
        LocalBuildConfigValidator().validate(_valid_config(iso_source_path=""))
    assert "iso_source_path" in str(exc.value)


def test_validator_rejects_bad_architecture():
    """An architecture outside {x86_64, amd64, arm64} is rejected."""
    with pytest.raises(ConfigurationError) as exc:
        LocalBuildConfigValidator().validate(
            _valid_config(architecture="ppc64le")
        )
    assert "architecture" in str(exc.value)


def test_validator_rejects_non_positive_disk_size():
    """A non-positive system_disk_size_gb is rejected."""
    with pytest.raises(ConfigurationError) as exc:
        LocalBuildConfigValidator().validate(
            _valid_config(system_disk_size_gb=0)
        )
    assert "system_disk_size_gb" in str(exc.value)


def test_validator_rejects_non_positive_vcpus_and_ram():
    """Non-positive vcpus and ram_mib are both reported."""
    with pytest.raises(ConfigurationError) as exc:
        LocalBuildConfigValidator().validate(
            _valid_config(vcpus=0, ram_mib=-1)
        )
    message = str(exc.value)
    assert "vcpus" in message
    assert "ram_mib" in message


def test_validator_rejects_bad_firstboot_format():
    """A deploy firstboot_format outside the allowed set is rejected."""
    deploy = DeployConfig(
        final_image_path="/out/final.qcow2",
        glance_image_name="proxmox-opcp",
        credentials=Credentials(
            auth_url="https://keystone.example.com/v3",
            region="RegionOne",
        ),
        ironic_node="node-1",
        bare_metal_flavor="baremetal.large",
        firstboot_format="not-a-format",
    )
    with pytest.raises(ConfigurationError) as exc:
        LocalBuildConfigValidator().validate(
            _valid_config(), deploy_config=deploy
        )
    assert "firstboot_format" in str(exc.value)


def test_validator_aggregates_multiple_failures():
    """A config with several problems lists every failure in one error."""
    bad = _valid_config(
        iso_source_path="",
        architecture="ppc64le",
        system_disk_size_gb=0,
        vcpus=-2,
        ram_mib=0,
    )
    with pytest.raises(ConfigurationError) as exc:
        LocalBuildConfigValidator().validate(bad)

    message = str(exc.value)
    # The aggregate message should enumerate all distinct failures.
    assert "iso_source_path" in message
    assert "architecture" in message
    assert "system_disk_size_gb" in message
    assert "vcpus" in message
    assert "ram_mib" in message
    # At least five bullet points collected.
    assert message.count("  - ") >= 5
