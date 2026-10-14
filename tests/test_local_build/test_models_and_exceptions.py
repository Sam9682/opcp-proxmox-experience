"""
Unit tests for local_build data models and typed exceptions
(local_build, Requirements 1.3, 4.1, 5.2, 8.4).

Covers:
- LocalBuildConfig mandated defaults (system_disk_size_gb, ram_mib, vcpus,
  build_vm_name, final_image_name, and the remaining documented defaults).
- PrerequisiteReport.ok truth table: all-True -> ok; any failing probe -> not ok;
  non-empty missing_packages -> not ok.
- Supporting dataclass construction (DeployConfig, ImageBuildArtifact,
  DeployResult, CleaningPlan, CleaningOp, CommandResult) and the CommandResult
  success property.
- Every one of the 12 local_build exceptions subclasses
  proxmox_install_automation.exceptions.ProxmoxAutomationError.
"""

import itertools

import pytest

from proxmox_install_automation.exceptions import ProxmoxAutomationError
from proxmox_install_automation.local_build import exceptions as lb_exc
from proxmox_install_automation.local_build.exceptions import (
    BootTestError,
    BuildVMError,
    FirstBootScaffoldError,
    GlanceImportError,
    ImageCleanError,
    ImageFinalizeError,
    IronicDeployError,
    ISOStagingError,
    LocalBuildError,
    LocalCommandError,
    PrerequisiteError,
    SystemDiskError,
)
from proxmox_install_automation.local_build.models import (
    CleaningOp,
    CleaningPlan,
    CommandResult,
    DeployConfig,
    DeployResult,
    ImageBuildArtifact,
    LocalBuildConfig,
    PrerequisiteReport,
)
from proxmox_install_automation.models import Credentials


ALL_LOCAL_BUILD_EXCEPTIONS = [
    BootTestError,
    BuildVMError,
    FirstBootScaffoldError,
    GlanceImportError,
    ImageCleanError,
    ImageFinalizeError,
    IronicDeployError,
    ISOStagingError,
    LocalBuildError,
    LocalCommandError,
    PrerequisiteError,
    SystemDiskError,
]


def _credentials() -> Credentials:
    return Credentials(auth_url="https://keystone.example/v3", region="RegionOne")


class TestLocalBuildConfigDefaults:
    """LocalBuildConfig default values mandated by the design (Req 4.1, 5.2, 8.4)."""

    def _config(self) -> LocalBuildConfig:
        # iso_source_path is the only required (no-default) field.
        return LocalBuildConfig(iso_source_path="/isos/proxmox-ve.iso")

    def test_mandated_defaults(self):
        config = self._config()
        assert config.system_disk_size_gb == 64
        assert config.ram_mib == 16384
        assert config.vcpus == 8
        assert config.build_vm_name == "proxmox-image-builder"
        assert config.final_image_name == "proxmox-opcp-final.qcow2"

    def test_remaining_defaults(self):
        config = self._config()
        assert config.architecture == "x86_64"
        assert config.libvirt_images_dir == "/var/lib/libvirt/images"
        assert config.system_disk_name == "proxmox-image-builder.qcow2"
        assert config.cpu_mode == "host-passthrough"
        assert config.network_model == "virtio"
        assert config.disk_bus == "virtio"
        assert config.output_dir == "/var/lib/libvirt/images"
        assert config.build_timeout == 3600
        assert config.convert_timeout == 1800
        assert config.boot_test_timeout == 600
        assert config.assume_install_complete is False

    def test_overrides_are_respected(self):
        config = LocalBuildConfig(
            iso_source_path="/isos/custom.iso",
            system_disk_size_gb=128,
            vcpus=16,
            ram_mib=32768,
            assume_install_complete=True,
        )
        assert config.iso_source_path == "/isos/custom.iso"
        assert config.system_disk_size_gb == 128
        assert config.vcpus == 16
        assert config.ram_mib == 32768
        assert config.assume_install_complete is True
        # Untouched fields keep their defaults.
        assert config.build_vm_name == "proxmox-image-builder"


class TestPrerequisiteReportOk:
    """PrerequisiteReport.ok truth table (Req 2 aggregate logic)."""

    def _report(
        self,
        os_supported=True,
        missing_packages=None,
        kvm_available=True,
        uefi_available=True,
    ) -> PrerequisiteReport:
        return PrerequisiteReport(
            os_supported=os_supported,
            missing_packages=list(missing_packages or []),
            kvm_available=kvm_available,
            uefi_available=uefi_available,
        )

    def test_all_satisfied_is_ok(self):
        assert self._report().ok is True

    def test_non_empty_missing_packages_is_not_ok(self):
        assert self._report(missing_packages=["qemu-utils"]).ok is False

    def test_os_unsupported_is_not_ok(self):
        assert self._report(os_supported=False).ok is False

    def test_no_kvm_is_not_ok(self):
        assert self._report(kvm_available=False).ok is False

    def test_no_uefi_is_not_ok(self):
        assert self._report(uefi_available=False).ok is False

    def test_full_boolean_truth_table(self):
        # ok is True iff all three booleans are True AND missing_packages is empty.
        for os_sup, kvm, uefi, has_missing in itertools.product(
            [True, False], repeat=4
        ):
            missing = ["pkg"] if has_missing else []
            report = self._report(
                os_supported=os_sup,
                kvm_available=kvm,
                uefi_available=uefi,
                missing_packages=missing,
            )
            expected = os_sup and kvm and uefi and not has_missing
            assert report.ok is expected, (os_sup, kvm, uefi, has_missing)


class TestSupportingDataclasses:
    """Construction/field sanity for the remaining models."""

    def test_deploy_config_reuses_credentials_and_defaults(self):
        creds = _credentials()
        config = DeployConfig(
            final_image_path="/images/final.qcow2",
            glance_image_name="proxmox-opcp",
            credentials=creds,
            ironic_node="node-1",
            bare_metal_flavor="baremetal",
        )
        assert config.credentials is creds
        assert config.network_name == "Ext-Net"
        assert config.glance_timeout == 1800
        assert config.deploy_timeout == 3600
        assert config.firstboot_format == "cloud-init"
        assert config.firstboot_output_dir == "./firstboot"

    def test_image_build_artifact_fields(self):
        artifact = ImageBuildArtifact(
            final_image_path="/images/final.qcow2",
            virtual_size_bytes=68719476736,
            actual_size_bytes=2147483648,
            build_duration_seconds=123.4,
            boot_test_passed=True,
        )
        assert artifact.final_image_path == "/images/final.qcow2"
        assert artifact.boot_test_passed is True

    def test_deploy_result_defaults(self):
        result = DeployResult(
            glance_image_id="img-1",
            server_id="srv-1",
            ironic_node="node-1",
        )
        assert result.firstboot_artifacts == []
        assert result.deploy_duration_seconds == 0.0

    def test_cleaning_plan_and_op(self):
        plan = CleaningPlan()
        assert plan.operations == []
        op = CleaningOp(action="set-hostname", params={"hostname": "pve-template"})
        plan.operations.append(op)
        assert plan.operations[0].action == "set-hostname"
        assert plan.operations[0].params == {"hostname": "pve-template"}
        assert op.description == ""

    def test_command_result_success_property(self):
        ok = CommandResult(argv=["qemu-img", "info"], exit_code=0, stdout="", stderr="")
        bad = CommandResult(
            argv=["qemu-img", "info"], exit_code=1, stdout="", stderr="boom"
        )
        assert ok.success is True
        assert bad.success is False


class TestExceptionHierarchy:
    """Every local_build exception must subclass ProxmoxAutomationError (Req 1.3)."""

    def test_exactly_twelve_exceptions_defined(self):
        assert len(ALL_LOCAL_BUILD_EXCEPTIONS) == 12

    @pytest.mark.parametrize("exc_cls", ALL_LOCAL_BUILD_EXCEPTIONS)
    def test_subclasses_base_error(self, exc_cls):
        assert issubclass(exc_cls, ProxmoxAutomationError)

    @pytest.mark.parametrize("exc_cls", ALL_LOCAL_BUILD_EXCEPTIONS)
    def test_instances_are_catchable_as_base_error(self, exc_cls):
        with pytest.raises(ProxmoxAutomationError):
            raise exc_cls("failure")

    def test_module_all_lists_all_twelve(self):
        # The module's __all__ should enumerate exactly the 12 exception names.
        assert set(lb_exc.__all__) == {
            cls.__name__ for cls in ALL_LOCAL_BUILD_EXCEPTIONS
        }
