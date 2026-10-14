"""
Unit tests for the LocalImageBuilder orchestrator (local_build, Req 2-12).

The orchestrator sequences the discrete step components with try/finally
cleanup of the transient Build_VM. Every step component is injectable, so the
orchestrator is exercised here with mocks for all dependencies — no real
subprocesses, libvirt, or OpenStack calls occur.

Covers:
- build() invokes the step components in the documented order and sets
  artifact.boot_test_passed from the boot test (Req 2.5, 5.3, 8.5, 9.3).
- The operator pause gate (confirm_install) runs only when
  config.assume_install_complete is False (Req 6.1/6.3).
- A failing PrerequisiteReport (ok False) raises LocalBuildError (Req 2.5).
- A step raising its typed error is caught and re-raised as LocalBuildError.
- The transient Build_VM is cleaned up (undefine via the runner) in the
  finally block when a failure occurs after VM creation (Req 5.3, 8.5).
- deploy() invokes glance import -> ironic deploy -> first-boot scaffolding in
  order and returns a populated DeployResult (Req 10-12).

_Requirements: 2.5, 5.3, 6.3, 8.5_
"""

from unittest.mock import MagicMock

import pytest

from proxmox_install_automation.local_build.builder import LocalImageBuilder
from proxmox_install_automation.local_build.exceptions import (
    BuildVMError,
    ISOStagingError,
    LocalBuildError,
)
from proxmox_install_automation.local_build.models import (
    DeployConfig,
    DeployResult,
    ImageBuildArtifact,
    LocalBuildConfig,
    PrerequisiteReport,
)
from proxmox_install_automation.models import Credentials


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def _ok_report() -> PrerequisiteReport:
    """A PrerequisiteReport whose .ok property is True (happy path)."""
    return PrerequisiteReport(
        os_supported=True,
        missing_packages=[],
        kvm_available=True,
        uefi_available=True,
    )


def _artifact(path: str = "/var/lib/libvirt/images/proxmox-opcp-final.qcow2"):
    """An ImageBuildArtifact as returned by ImageFinalizer.finalize()."""
    return ImageBuildArtifact(
        final_image_path=path,
        virtual_size_bytes=64 * 1024**3,
        actual_size_bytes=4 * 1024**3,
        build_duration_seconds=0.0,
        boot_test_passed=False,
    )


def _build_config(**overrides) -> LocalBuildConfig:
    base = dict(
        iso_source_path="/isos/proxmox-ve.iso",
        build_vm_name="proxmox-image-builder",
        final_image_name="proxmox-opcp-final.qcow2",
        output_dir="/var/lib/libvirt/images",
    )
    base.update(overrides)
    return LocalBuildConfig(**base)


def _deploy_config(**overrides) -> DeployConfig:
    credentials = Credentials(
        auth_url="https://auth.cloud.ovh.net/v3",
        region="GRA7",
        auth_type="v3applicationcredential",
        application_credential_id="cred-id",
        application_credential_secret="secret",
        project_name="proj",
    )
    base = dict(
        final_image_path="/var/lib/libvirt/images/proxmox-opcp-final.qcow2",
        glance_image_name="proxmox-opcp",
        credentials=credentials,
        ironic_node="node-01",
        bare_metal_flavor="bm-large",
    )
    base.update(overrides)
    return DeployConfig(**base)


def _make_builder(
    *,
    report: PrerequisiteReport,
    artifact: ImageBuildArtifact,
    boot_passed: bool = True,
):
    """
    Build a LocalImageBuilder with every component mocked.

    Returns a (builder, mocks) tuple where ``mocks`` is a dict of the injected
    MagicMocks plus a shared ``manager`` mock onto which the component mocks are
    attached so call ordering across components can be asserted.
    """
    manager = MagicMock()

    runner = MagicMock(name="runner")
    prereq = MagicMock(name="prereq")
    iso = MagicMock(name="iso")
    system_disk = MagicMock(name="system_disk")
    build_vm = MagicMock(name="build_vm")
    cleaner = MagicMock(name="cleaner")
    finalizer = MagicMock(name="finalizer")
    boot_tester = MagicMock(name="boot_tester")
    glance = MagicMock(name="glance")
    ironic = MagicMock(name="ironic")
    firstboot = MagicMock(name="firstboot")
    confirm_install = MagicMock(name="confirm_install")

    # Wire up return values for the happy path.
    prereq.check.return_value = report
    iso.stage.return_value = "/var/lib/libvirt/images/proxmox-ve.iso"
    system_disk.create.return_value = (
        "/var/lib/libvirt/images/proxmox-image-builder.qcow2"
    )
    plan = MagicMock(name="plan")
    cleaner.build_plan.return_value = plan
    finalizer.finalize.return_value = artifact
    finalizer.build_undefine_argv.return_value = [
        "virsh",
        "undefine",
        "proxmox-image-builder",
        "--nvram",
    ]
    boot_tester.run.return_value = boot_passed

    # Attach every component to the shared manager so call order is recorded
    # across components (manager.mock_calls preserves global order).
    manager.attach_mock(runner, "runner")
    manager.attach_mock(prereq, "prereq")
    manager.attach_mock(iso, "iso")
    manager.attach_mock(system_disk, "system_disk")
    manager.attach_mock(build_vm, "build_vm")
    manager.attach_mock(cleaner, "cleaner")
    manager.attach_mock(finalizer, "finalizer")
    manager.attach_mock(boot_tester, "boot_tester")
    manager.attach_mock(glance, "glance")
    manager.attach_mock(ironic, "ironic")
    manager.attach_mock(firstboot, "firstboot")
    manager.attach_mock(confirm_install, "confirm_install")

    builder = LocalImageBuilder(
        runner=runner,
        prerequisite_checker=prereq,
        iso_stager=iso,
        system_disk_creator=system_disk,
        build_vm_creator=build_vm,
        image_cleaner=cleaner,
        image_finalizer=finalizer,
        boot_tester=boot_tester,
        glance_importer=glance,
        ironic_deployer=ironic,
        firstboot_scaffolder=firstboot,
        confirm_install=confirm_install,
    )

    return builder, {
        "manager": manager,
        "runner": runner,
        "prereq": prereq,
        "iso": iso,
        "system_disk": system_disk,
        "build_vm": build_vm,
        "cleaner": cleaner,
        "finalizer": finalizer,
        "boot_tester": boot_tester,
        "glance": glance,
        "ironic": ironic,
        "firstboot": firstboot,
        "confirm_install": confirm_install,
        "plan": plan,
    }


# --------------------------------------------------------------------------- #
# build() — ordering & wiring
# --------------------------------------------------------------------------- #


class TestBuildOrdering:
    def test_build_calls_components_in_documented_order(self):
        """prereq -> iso -> system_disk -> build_vm -> confirm -> clean ->
        finalize -> boot_test, with the right args threaded between steps."""
        config = _build_config()
        artifact = _artifact()
        builder, m = _make_builder(report=_ok_report(), artifact=artifact)

        result = builder.build(config)

        # Each step was invoked exactly as the orchestrator documents.
        m["prereq"].check.assert_called_once_with()
        m["iso"].stage.assert_called_once_with(config)
        m["system_disk"].create.assert_called_once_with(config)
        m["build_vm"].create.assert_called_once_with(
            config,
            "/var/lib/libvirt/images/proxmox-ve.iso",
            "/var/lib/libvirt/images/proxmox-image-builder.qcow2",
        )
        m["confirm_install"].assert_called_once_with(config)
        m["cleaner"].build_plan.assert_called_once_with()
        m["cleaner"].apply.assert_called_once_with(
            "/var/lib/libvirt/images/proxmox-image-builder.qcow2", m["plan"]
        )
        m["finalizer"].shutdown.assert_called_once_with(config.build_vm_name)
        m["finalizer"].finalize.assert_called_once_with(
            config, "/var/lib/libvirt/images/proxmox-image-builder.qcow2"
        )
        m["boot_tester"].run.assert_called_once_with(
            artifact.final_image_path, config
        )

        # The returned artifact is the finalizer's, with the boot result set.
        assert result is artifact

    def test_build_global_call_order(self):
        """The cross-component call order matches the documented pipeline."""
        config = _build_config()
        builder, m = _make_builder(report=_ok_report(), artifact=_artifact())

        builder.build(config)

        # Reduce the manager's recorded calls to the ordered sequence of the
        # key step entry points we care about.
        tracked = {
            "prereq.check",
            "iso.stage",
            "system_disk.create",
            "build_vm.create",
            "confirm_install",
            "cleaner.build_plan",
            "cleaner.apply",
            "finalizer.shutdown",
            "finalizer.finalize",
            "boot_tester.run",
        }
        observed = [
            name for name, _args, _kwargs in m["manager"].mock_calls
            if name in tracked
        ]
        expected = [
            "prereq.check",
            "iso.stage",
            "system_disk.create",
            "build_vm.create",
            "confirm_install",
            "cleaner.build_plan",
            "cleaner.apply",
            "finalizer.shutdown",
            "finalizer.finalize",
            "boot_tester.run",
        ]
        assert observed == expected

    def test_build_sets_boot_test_passed_true(self):
        """artifact.boot_test_passed reflects a passing boot test (Req 9.3)."""
        artifact = _artifact()
        builder, _m = _make_builder(
            report=_ok_report(), artifact=artifact, boot_passed=True
        )

        result = builder.build(_build_config())

        assert result.boot_test_passed is True

    def test_build_sets_boot_test_passed_false(self):
        """artifact.boot_test_passed reflects a failing boot test (Req 9.3)."""
        artifact = _artifact()
        builder, _m = _make_builder(
            report=_ok_report(), artifact=artifact, boot_passed=False
        )

        result = builder.build(_build_config())

        assert result.boot_test_passed is False


# --------------------------------------------------------------------------- #
# build() — operator pause gate (Req 6)
# --------------------------------------------------------------------------- #


class TestOperatorPauseGate:
    def test_confirm_install_invoked_when_not_assuming_complete(self):
        config = _build_config(assume_install_complete=False)
        builder, m = _make_builder(report=_ok_report(), artifact=_artifact())

        builder.build(config)

        m["confirm_install"].assert_called_once_with(config)

    def test_confirm_install_not_invoked_when_assuming_complete(self):
        """With assume_install_complete=True the operator pause is skipped."""
        config = _build_config(assume_install_complete=True)
        builder, m = _make_builder(report=_ok_report(), artifact=_artifact())

        builder.build(config)

        m["confirm_install"].assert_not_called()
        # The rest of the pipeline still runs.
        m["cleaner"].build_plan.assert_called_once()
        m["finalizer"].finalize.assert_called_once()
        m["boot_tester"].run.assert_called_once()


# --------------------------------------------------------------------------- #
# build() — failure handling (Req 2.5, 5.3, 8.5)
# --------------------------------------------------------------------------- #


class TestBuildFailures:
    def test_failing_prereq_report_raises_local_build_error(self):
        """report.ok False stops the pipeline with LocalBuildError (Req 2.5)."""
        bad_report = PrerequisiteReport(
            os_supported=False,
            missing_packages=["ovmf"],
            kvm_available=False,
            uefi_available=False,
        )
        builder, m = _make_builder(report=bad_report, artifact=_artifact())

        with pytest.raises(LocalBuildError):
            builder.build(_build_config())

        # Pipeline stops right after the prerequisite check.
        m["iso"].stage.assert_not_called()
        m["system_disk"].create.assert_not_called()
        m["build_vm"].create.assert_not_called()
        # No VM was created, so no cleanup via the runner.
        m["runner"].run.assert_not_called()

    def test_typed_step_error_rewrapped_as_local_build_error(self):
        """A typed step error (e.g. ISOStagingError) surfaces as
        LocalBuildError. The failure occurs before VM creation, so no
        Build_VM cleanup runs."""
        builder, m = _make_builder(report=_ok_report(), artifact=_artifact())
        m["iso"].stage.side_effect = ISOStagingError("iso missing")

        with pytest.raises(LocalBuildError):
            builder.build(_build_config())

        m["build_vm"].create.assert_not_called()
        m["runner"].run.assert_not_called()

    def test_build_vm_cleaned_up_on_failure_after_creation(self):
        """When a step after VM creation fails, the finally block undefines the
        transient Build_VM through the runner (Req 5.3, 8.5)."""
        config = _build_config()
        builder, m = _make_builder(report=_ok_report(), artifact=_artifact())
        # Fail during cleaning — i.e. after the Build_VM is created but before
        # finalize() would have undefined it.
        m["cleaner"].apply.side_effect = BuildVMError("clean failed")

        with pytest.raises(LocalBuildError):
            builder.build(config)

        # finalize() never ran, so vm_defined stayed True and the finally block
        # cleans up: build_undefine_argv is used and the runner undefines.
        m["finalizer"].finalize.assert_not_called()
        m["finalizer"].build_undefine_argv.assert_called_once_with(
            config.build_vm_name
        )
        m["runner"].run.assert_called_once_with(
            ["virsh", "undefine", "proxmox-image-builder", "--nvram"],
            check=False,
        )

    def test_no_cleanup_when_failure_before_vm_creation(self):
        """A failure before the Build_VM exists performs no undefine."""
        builder, m = _make_builder(report=_ok_report(), artifact=_artifact())
        m["system_disk"].create.side_effect = ISOStagingError("disk failed")

        with pytest.raises(LocalBuildError):
            builder.build(_build_config())

        m["finalizer"].build_undefine_argv.assert_not_called()
        m["runner"].run.assert_not_called()

    def test_no_cleanup_on_success(self):
        """On success finalize() undefines the VM, so the finally block does
        not undefine it again via the runner."""
        builder, m = _make_builder(report=_ok_report(), artifact=_artifact())

        builder.build(_build_config())

        m["runner"].run.assert_not_called()


# --------------------------------------------------------------------------- #
# deploy() — ordering & result (Req 10-12)
# --------------------------------------------------------------------------- #


class TestDeploy:
    def test_deploy_calls_components_in_order_and_returns_result(self):
        config = _deploy_config()
        builder, m = _make_builder(report=_ok_report(), artifact=_artifact())

        m["glance"].import_image.return_value = "glance-image-123"
        m["ironic"].deploy.return_value = "server-456"
        m["firstboot"].generate.return_value = [
            "./firstboot/user-data",
            "./firstboot/meta-data",
        ]

        result = builder.deploy(config)

        m["glance"].import_image.assert_called_once_with(config)
        m["ironic"].deploy.assert_called_once_with(config, "glance-image-123")
        m["firstboot"].generate.assert_called_once_with(config)

        # Cross-component ordering of the deploy pipeline.
        tracked = {"glance.import_image", "ironic.deploy", "firstboot.generate"}
        observed = [
            name for name, _args, _kwargs in m["manager"].mock_calls
            if name in tracked
        ]
        assert observed == [
            "glance.import_image",
            "ironic.deploy",
            "firstboot.generate",
        ]

        # A fully populated DeployResult is returned.
        assert isinstance(result, DeployResult)
        assert result.glance_image_id == "glance-image-123"
        assert result.server_id == "server-456"
        assert result.ironic_node == config.ironic_node
        assert result.firstboot_artifacts == [
            "./firstboot/user-data",
            "./firstboot/meta-data",
        ]

    def test_deploy_rewraps_step_error_as_local_build_error(self):
        """A deploy-step failure surfaces as LocalBuildError (Req 10-12)."""
        config = _deploy_config()
        builder, m = _make_builder(report=_ok_report(), artifact=_artifact())
        m["glance"].import_image.side_effect = RuntimeError("glance down")

        with pytest.raises(LocalBuildError):
            builder.deploy(config)

        m["ironic"].deploy.assert_not_called()
        m["firstboot"].generate.assert_not_called()
