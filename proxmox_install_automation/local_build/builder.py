"""
LocalImageBuilder orchestrator for the local KVM/libvirt build and OPCP deploy path.

Sequences the discrete step components with ``try/finally`` cleanup of the
transient Build_VM, mirroring ``image_builder.ImageBuilder.build()`` and
``orchestrator.ProxmoxBuilder.run()``.

Build pipeline (Req 2-9):
    prerequisites -> ISO stage -> system disk -> build VM ->
    operator pause (documented interactive install, unless
    ``assume_install_complete``) -> clean -> finalize -> boot test.

Deploy pipeline (Req 10-12):
    Glance import -> Ironic deploy -> first-boot scaffolding.

All step components are injectable (constructor params defaulting to real
instances sharing a single ``LocalCommandRunner``) so the orchestrator is
unit-testable with mocks. The documented interactive install is gated by an
injectable confirmation callback so the operator pause is testable without
blocking on stdin.
"""

import time
from typing import Callable, Optional

from ..logging_config import get_logger
from .boot_tester import BootTester
from .build_vm import BuildVMCreator
from .command_runner import LocalCommandRunner
from .exceptions import LocalBuildError
from .firstboot_scaffolder import FirstBootScaffolder
from .glance_importer import GlanceImporter
from .image_cleaner import ImageCleaner
from .image_finalizer import ImageFinalizer
from .ironic_deployer import IronicDeployer
from .iso_stager import ISOStager
from .models import (
    DeployConfig,
    DeployResult,
    ImageBuildArtifact,
    LocalBuildConfig,
)
from .prerequisites import PrerequisiteChecker
from .system_disk import SystemDiskCreator

logger = get_logger("local_build.builder")

# Default operator-pause message pointing to the documented interactive install
# (Req 6). The install is interactive and NOT automated.
_INSTALL_PROMPT = (
    "\n"
    "============================================================\n"
    "The transient Build_VM '{vm_name}' has been created.\n"
    "Perform the DOCUMENTED INTERACTIVE Proxmox VE install now\n"
    "(see shared/LOCAL_BUILD_context.md). The install is interactive\n"
    "and is NOT automated.\n"
    "Press ENTER once the install is complete to continue the build...\n"
    "============================================================\n"
)


def _default_confirm_install(config: LocalBuildConfig) -> None:
    """Default operator-pause confirmation: prompt on stdin (Req 6.1).

    Blocks until the operator confirms the documented interactive install is
    complete. Replaceable via dependency injection so the pause is testable.
    """
    input(_INSTALL_PROMPT.format(vm_name=config.build_vm_name))


class LocalImageBuilder:
    """Orchestrates the local KVM/libvirt build and the OPCP deploy phases."""

    def __init__(
        self,
        runner: Optional[LocalCommandRunner] = None,
        prerequisite_checker: Optional[PrerequisiteChecker] = None,
        iso_stager: Optional[ISOStager] = None,
        system_disk_creator: Optional[SystemDiskCreator] = None,
        build_vm_creator: Optional[BuildVMCreator] = None,
        image_cleaner: Optional[ImageCleaner] = None,
        image_finalizer: Optional[ImageFinalizer] = None,
        boot_tester: Optional[BootTester] = None,
        glance_importer: Optional[GlanceImporter] = None,
        ironic_deployer: Optional[IronicDeployer] = None,
        firstboot_scaffolder: Optional[FirstBootScaffolder] = None,
        confirm_install: Optional[Callable[[LocalBuildConfig], None]] = None,
    ) -> None:
        """
        Args:
            runner: Shared local command runner injected into every
                tool-invoking step component. A fresh ``LocalCommandRunner`` is
                created when not supplied.
            prerequisite_checker: Overrides the default ``PrerequisiteChecker``.
            iso_stager: Overrides the default ``ISOStager``.
            system_disk_creator: Overrides the default ``SystemDiskCreator``.
            build_vm_creator: Overrides the default ``BuildVMCreator``.
            image_cleaner: Overrides the default ``ImageCleaner``.
            image_finalizer: Overrides the default ``ImageFinalizer``.
            boot_tester: Overrides the default ``BootTester``.
            glance_importer: Overrides the default ``GlanceImporter``.
            ironic_deployer: Overrides the default ``IronicDeployer``.
            firstboot_scaffolder: Overrides the default ``FirstBootScaffolder``.
            confirm_install: Operator-pause confirmation callback invoked
                between "VM created" and "cleaning" unless
                ``config.assume_install_complete`` is True (Req 6.1). Defaults
                to a stdin prompt; injectable so the pause is unit-testable.
        """
        self._runner = runner or LocalCommandRunner()

        # Build-phase step components (Req 2-9), each sharing the single runner
        # so the whole pipeline is mockable through one dependency.
        self._prerequisite_checker = prerequisite_checker or PrerequisiteChecker(
            self._runner
        )
        self._iso_stager = iso_stager or ISOStager(self._runner)
        self._system_disk_creator = system_disk_creator or SystemDiskCreator(
            self._runner
        )
        self._build_vm_creator = build_vm_creator or BuildVMCreator(self._runner)
        self._image_cleaner = image_cleaner or ImageCleaner(self._runner)
        self._image_finalizer = image_finalizer or ImageFinalizer(self._runner)
        self._boot_tester = boot_tester or BootTester(self._runner)

        # Deploy-phase step components (Req 10-12).
        self._glance_importer = glance_importer or GlanceImporter()
        self._ironic_deployer = ironic_deployer or IronicDeployer(self._runner)
        self._firstboot_scaffolder = (
            firstboot_scaffolder or FirstBootScaffolder()
        )

        self._confirm_install = confirm_install or _default_confirm_install

    def build(self, config: LocalBuildConfig) -> ImageBuildArtifact:
        """
        Execute the full local build pipeline (Req 2-9).

        Steps executed in order:
          1. PrerequisiteChecker.check() -> raise if report is not ok (Req 2.5)
          2. ISOStager.stage(config)                                 (Req 3.5)
          3. SystemDiskCreator.create(config)                        (Req 4.3)
          4. BuildVMCreator.create(config, iso_path, disk_path)      (Req 5.3)
          5. Operator pause for the documented interactive install
             unless ``config.assume_install_complete``               (Req 6.1)
          6. ImageCleaner.build_plan() + apply(disk_path, plan)      (Req 7.8)
          7. ImageFinalizer.shutdown + finalize(config, disk_path)   (Req 8.5)
          8. BootTester.run(final_image_path, config) -> set
             artifact.boot_test_passed                               (Req 9.3)

        The transient Build_VM is cleaned up in a ``finally`` block even on
        failure. Step errors are caught, logged, and re-raised as
        ``LocalBuildError``.

        Args:
            config: Complete local build configuration.

        Returns:
            An ``ImageBuildArtifact`` describing the produced Final_Image, with
            ``boot_test_passed`` reflecting the import boot test outcome.

        Raises:
            LocalBuildError: If any build step fails.
        """
        start_seconds = time.time()

        # Tracks whether ImageFinalizer already undefined the Build_VM so the
        # finally-block cleanup stays idempotent and does not double-undefine.
        vm_defined = False

        try:
            # Step 1: Prerequisites (Req 2.5)
            logger.info("Step 1: Checking build-host prerequisites")
            report = self._prerequisite_checker.check()
            if not report.ok:
                raise LocalBuildError(
                    "Build-host prerequisites not satisfied: "
                    f"os_supported={report.os_supported}, "
                    f"missing_packages={report.missing_packages}, "
                    f"kvm_available={report.kvm_available}, "
                    f"uefi_available={report.uefi_available}"
                )

            # Step 2: Stage the installer ISO (Req 3.5)
            logger.info("Step 2: Staging installer ISO")
            iso_path = self._iso_stager.stage(config)

            # Step 3: Create the 64GB qcow2 System_Disk (Req 4.3)
            logger.info("Step 3: Creating system disk")
            disk_path = self._system_disk_creator.create(config)

            # Step 4: Create the transient Build_VM (Req 5.3)
            logger.info("Step 4: Creating build VM")
            self._build_vm_creator.create(config, iso_path, disk_path)
            vm_defined = True

            # Step 5: Documented interactive install pause (Req 6.1)
            if config.assume_install_complete:
                logger.info(
                    "Step 5: Skipping operator pause "
                    "(assume_install_complete=True)"
                )
            else:
                logger.info(
                    "Step 5: Pausing for documented interactive install"
                )
                self._confirm_install(config)

            # Step 6: Clean the installed guest image (Req 7.8)
            logger.info("Step 6: Cleaning installed image")
            plan = self._image_cleaner.build_plan()
            self._image_cleaner.apply(disk_path, plan)

            # Step 7: Finalize — shutdown, undefine, validate, compress (Req 8.5)
            logger.info("Step 7: Finalizing image")
            self._image_finalizer.shutdown(config.build_vm_name)
            artifact = self._image_finalizer.finalize(config, disk_path)
            # finalize() undefined the Build_VM; no further cleanup needed.
            vm_defined = False

            # Step 8: ISO-less import boot test (Req 9.3)
            logger.info("Step 8: Boot-testing final image")
            boot_passed = self._boot_tester.run(
                artifact.final_image_path, config
            )
            artifact.boot_test_passed = boot_passed

            build_duration = time.time() - start_seconds
            artifact.build_duration_seconds = build_duration
            logger.info(
                "Local image build completed successfully in %.1f seconds. "
                "Final image: %s (boot_test_passed=%s)",
                build_duration,
                artifact.final_image_path,
                artifact.boot_test_passed,
            )
            return artifact

        except LocalBuildError:
            raise
        except Exception as exc:
            logger.error("Local build pipeline failed: %s", exc)
            raise LocalBuildError(
                f"Local build pipeline failed: {exc}"
            ) from exc

        finally:
            # Clean up the transient Build_VM even on failure (Req 5, 8.2).
            if vm_defined:
                self._cleanup_build_vm(config.build_vm_name)

    def deploy(self, deploy_config: DeployConfig) -> DeployResult:
        """
        Execute the OPCP deploy pipeline (Req 10-12).

        Steps executed in order:
          1. GlanceImporter.import_image(deploy_config) -> glance_image_id
             (Req 10.4)
          2. IronicDeployer.deploy(deploy_config, glance_image_id) ->
             server_id                                               (Req 11.4)
          3. FirstBootScaffolder.generate(deploy_config) -> artifact paths
             (Req 12.1)

        Args:
            deploy_config: Complete Glance import + Ironic deploy + first-boot
                configuration.

        Returns:
            A populated ``DeployResult``.

        Raises:
            LocalBuildError: If any deploy step fails.
        """
        start_seconds = time.time()

        try:
            # Step 1: Import the final image into Glance (Req 10.4)
            logger.info("Step 1: Importing final image into Glance")
            glance_image_id = self._glance_importer.import_image(deploy_config)

            # Step 2: Deploy to the Ironic bare-metal node (Req 11.4)
            logger.info("Step 2: Deploying to Ironic bare-metal node")
            server_id = self._ironic_deployer.deploy(
                deploy_config, glance_image_id
            )

            # Step 3: Generate first-boot scaffolding (Req 12.1)
            logger.info("Step 3: Generating first-boot scaffolding")
            firstboot_artifacts = self._firstboot_scaffolder.generate(
                deploy_config
            )

            deploy_duration = time.time() - start_seconds
            logger.info(
                "Deploy completed successfully in %.1f seconds. "
                "Glance image: %s, server: %s, node: %s",
                deploy_duration,
                glance_image_id,
                server_id,
                deploy_config.ironic_node,
            )

            return DeployResult(
                glance_image_id=glance_image_id,
                server_id=server_id,
                ironic_node=deploy_config.ironic_node,
                firstboot_artifacts=firstboot_artifacts,
                deploy_duration_seconds=deploy_duration,
            )

        except LocalBuildError:
            raise
        except Exception as exc:
            logger.error("Deploy pipeline failed: %s", exc)
            raise LocalBuildError(f"Deploy pipeline failed: {exc}") from exc

    def _cleanup_build_vm(self, vm_name: str) -> None:
        """
        Best-effort cleanup of the transient Build_VM (Req 5, 8.2).

        Undefines the Build_VM while retaining the System_Disk qcow2 (never a
        storage-removal flag), reusing ``ImageFinalizer.build_undefine_argv`` so
        the cleanup argv matches finalization. Cleanup failures are logged and
        swallowed so the original build failure is not masked.
        """
        logger.info("Cleaning up transient build VM '%s'", vm_name)
        try:
            undefine_argv = self._image_finalizer.build_undefine_argv(vm_name)
            self._runner.run(undefine_argv, check=False)
        except Exception as exc:  # best-effort; never mask the original error
            logger.warning(
                "Failed to clean up build VM '%s': %s", vm_name, exc
            )


__all__ = ["LocalImageBuilder"]
