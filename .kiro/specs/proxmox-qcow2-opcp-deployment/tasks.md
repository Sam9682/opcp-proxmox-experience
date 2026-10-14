# Implementation Plan: Proxmox qcow2 OPCP Deployment (Local KVM/libvirt Build Path)

## Overview

This plan implements the new, additive `local_build/` package inside `proxmox_install_automation` without modifying any existing `image_builder` public interface or the `build-image` CLI command. Work proceeds bottom-up: models and typed exceptions first, then the mockable command runner, then pure argv/plan builders and their components, then the orchestrator, then the CLI subcommands, and finally the `shared/` documentation. The ten Correctness Properties from the design are implemented as `hypothesis` property-based tests (≥100 iterations each, tagged `Feature: proxmox-qcow2-opcp-deployment, Property N`), complemented by `pytest` example/unit tests. All tests mock `LocalCommandRunner` and the OpenStack SDK; no real `qemu-img`/`virt-install`/`virsh`/`openstack` processes are spawned in unit or property tests.

## Tasks

- [x] 1. Scaffold the `local_build` package foundation (models + exceptions)
  - [x] 1.1 Create package scaffolding and typed exceptions
    - Create `proxmox_install_automation/local_build/__init__.py` with public exports (populated incrementally as components land)
    - Create `proxmox_install_automation/local_build/exceptions.py` defining `LocalBuildError`, `LocalCommandError`, `PrerequisiteError`, `ISOStagingError`, `SystemDiskError`, `BuildVMError`, `ImageCleanError`, `ImageFinalizeError`, `BootTestError`, `GlanceImportError`, `IronicDeployError`, `FirstBootScaffoldError`, each extending `ProxmoxAutomationError`
    - _Requirements: 1.3, 2.5, 3.5, 4.3, 5.3, 8.5, 9.3, 10.4, 11.4, 14.2_

  - [x] 1.2 Create configuration and result dataclasses
    - Create `proxmox_install_automation/local_build/models.py` with `LocalBuildConfig`, `DeployConfig`, `ImageBuildArtifact`, `DeployResult`, `PrerequisiteReport` (with `ok` property), `CleaningPlan`, `CleaningOp`, and `CommandResult`, mirroring `image_builder/models.py` conventions
    - Reuse `proxmox_install_automation.models.Credentials` in `DeployConfig`
    - _Requirements: 2.5, 3.1, 4.1, 5.2, 8.4, 10.1, 11.2, 12.1_

  - [x]* 1.3 Write unit tests for models and exceptions
    - Assert dataclass defaults (e.g. `system_disk_size_gb == 64`, `ram_mib == 16384`, `vcpus == 8`, `build_vm_name == "proxmox-image-builder"`, `final_image_name == "proxmox-opcp-final.qcow2"`)
    - Assert `PrerequisiteReport.ok` logic and that every exception subclasses `ProxmoxAutomationError`
    - _Requirements: 1.3, 4.1, 5.2, 8.4_

- [x] 2. Implement the mockable local command runner
  - [x] 2.1 Implement `LocalCommandRunner`
    - Create `proxmox_install_automation/local_build/command_runner.py` with `LocalCommandRunner.run(argv, timeout=None, check=True) -> CommandResult`
    - Execute argv as a list via `subprocess` (never shell string interpolation); raise `LocalCommandError` on non-zero exit when `check=True` and on timeout
    - _Requirements: 2.5, 4.3, 5.3, 8.5_

  - [x]* 2.2 Write unit tests for `LocalCommandRunner`
    - Mock `subprocess` to simulate success, non-zero exit (raises `LocalCommandError`), and timeout (raises `LocalCommandError`)
    - Assert argv is passed as a list and `CommandResult` fields are populated
    - _Requirements: 2.5, 4.3, 5.3_

- [x] 3. Implement prerequisite checking (pure helpers + check)
  - [x] 3.1 Implement `PrerequisiteChecker`
    - Create `proxmox_install_automation/local_build/prerequisites.py` with `REQUIRED_PACKAGES`, pure `detect_os_family(os_release)`, pure `compute_missing_packages(installed)`, and `check() -> PrerequisiteReport`
    - `check()` parses `/etc/os-release`, probes packages via `dpkg-query`, verifies `/dev/kvm` and OVMF firmware; orchestrator raises `PrerequisiteError` when `report.ok` is False
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x]* 3.2 Write property test for OS family detection
    - **Property 2: OS family detection correctness**
    - **Validates: Requirements 2.1**
    - hypothesis, ≥100 iterations, tagged `Feature: proxmox-qcow2-opcp-deployment, Property 2`

  - [x]* 3.3 Write property test for missing-package computation
    - **Property 3: Missing-package computation correctness**
    - **Validates: Requirements 2.2, 2.5**
    - hypothesis, ≥100 iterations, tagged `Feature: proxmox-qcow2-opcp-deployment, Property 3`

  - [x]* 3.4 Write unit tests for `PrerequisiteChecker.check`
    - Mock `LocalCommandRunner` and filesystem probes to exercise missing-package, missing-KVM, and missing-OVMF paths
    - _Requirements: 2.3, 2.4, 2.5_

- [x] 4. Implement ISO staging (pure select + stage)
  - [x] 4.1 Implement `ISOStager`
    - Create `proxmox_install_automation/local_build/iso_stager.py` with `ISO_BY_ARCH`, pure `select_iso(architecture, available)`, and `stage(config) -> str`
    - `stage()` copies the ISO into `libvirt_images_dir`, sets libvirt-readable ownership/permissions, raises `ISOStagingError` if source ISO is absent
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x]* 4.2 Write property test for ISO architecture selection
    - **Property 4: ISO architecture selection is a total mapping**
    - **Validates: Requirements 3.3, 3.4**
    - hypothesis, ≥100 iterations, tagged `Feature: proxmox-qcow2-opcp-deployment, Property 4`

  - [x]* 4.3 Write unit tests for `ISOStager.stage`
    - Mock `LocalCommandRunner`/filesystem; assert permission setup and that a missing source raises `ISOStagingError`
    - _Requirements: 3.1, 3.2, 3.5_

- [x] 5. Implement system disk creation (pure argv + create)
  - [x] 5.1 Implement `SystemDiskCreator`
    - Create `proxmox_install_automation/local_build/system_disk.py` with pure `build_argv(path, size_gb)` producing `['qemu-img','create','-f','qcow2',path,f'{size_gb}G']` and `create(config) -> str`
    - `create()` builds the 64GB qcow2 independent of data disks; raises `SystemDiskError` on failure
    - _Requirements: 4.1, 4.2, 4.3_

  - [x]* 5.2 Write unit tests for `SystemDiskCreator`
    - Assert argv shape and `64G` sizing; mock runner failure to assert `SystemDiskError`
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 6. Implement build VM creation (pure argv + create)
  - [x] 6.1 Implement `BuildVMCreator`
    - Create `proxmox_install_automation/local_build/build_vm.py` with pure `build_argv(config, iso_path, disk_path)` and `create(config, iso_path, disk_path)`
    - argv must guarantee `--name proxmox-image-builder`, `--vcpus 8`, `--memory 16384`, `--cpu host-passthrough`, UEFI boot (OVMF loader), VirtIO system disk, VirtIO network, and the staged ISO as `--cdrom`; `create()` raises `BuildVMError` on failure
    - _Requirements: 5.1, 5.2, 5.3_

  - [x]* 6.2 Write property test for build VM argv
    - **Property 5: Build VM argv contains all mandated resources**
    - **Validates: Requirements 5.1, 5.2**
    - hypothesis, ≥100 iterations, tagged `Feature: proxmox-qcow2-opcp-deployment, Property 5`

  - [x]* 6.3 Write unit tests for `BuildVMCreator.create`
    - Mock runner to assert `virt-install` invocation and `BuildVMError` on failure
    - _Requirements: 5.1, 5.3_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement image cleaning (pure plan + libguestfs apply)
  - [x] 8.1 Implement `ImageCleaner`
    - Create `proxmox_install_automation/local_build/image_cleaner.py` with pure `build_plan() -> CleaningPlan` and `apply(disk_path, plan)`
    - Plan operations: loopback-only `/etc/network/interfaces`, hostname `pve-template`, remove SSH host keys, reset machine-id + recreate dbus symlink, remove DHCP leases, rotate/vacuum journal + remove archived logs, `apt clean`, and removal of any cluster/Corosync/Ceph/shared-storage config; `apply()` runs via libguestfs (`virt-customize`/`guestfish`) and raises `ImageCleanError` on failure
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 13.2_

  - [x]* 8.2 Write property test for generic-image cleaning
    - **Property 6: Cleaning produces a generic image**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 13.2**
    - hypothesis, ≥100 iterations, tagged `Feature: proxmox-qcow2-opcp-deployment, Property 6`

  - [x]* 8.3 Write unit tests for `ImageCleaner.apply`
    - Mock runner/libguestfs; assert single mocked apply call and `ImageCleanError` on failure
    - _Requirements: 7.1, 7.8_

- [x] 9. Implement image finalization (pure argv builders + shutdown/finalize)
  - [x] 9.1 Implement `ImageFinalizer`
    - Create `proxmox_install_automation/local_build/image_finalizer.py` with pure `build_undefine_argv(vm_name)` → `['virsh','undefine',vm_name,'--nvram']` (never storage-removal flags), pure `build_convert_argv(src, dst)` → `['qemu-img','convert','-O','qcow2','-c',src,dst]`, `shutdown(vm_name)`, and `finalize(config, disk_path) -> ImageBuildArtifact`
    - `finalize()` undefines `--nvram`, validates via `qemu-img check`/`info`, compresses to `proxmox-opcp-final.qcow2`; raises `ImageFinalizeError` if validation fails
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x]* 9.2 Write unit tests for `ImageFinalizer`
    - Assert undefine argv includes `--nvram` and omits storage-removal flags; assert convert argv includes `-c`; mock validation failure to assert `ImageFinalizeError`
    - _Requirements: 8.2, 8.3, 8.4, 8.5_

- [x] 10. Implement boot testing (pure argv + sequence detection + run)
  - [x] 10.1 Implement `BootTester`
    - Create `proxmox_install_automation/local_build/boot_tester.py` with `BOOT_MARKERS`, pure `build_argv(image_path, config)` (contains `--import`, never a `--cdrom`/ISO), pure `detect_boot_sequence(console_log)`, and `run(image_path, config) -> bool`
    - `run()` import-boots the final image, captures serial console, confirms UEFI→GRUB→kernel→Proxmox VE; raises `BootTestError` if not reached
    - _Requirements: 9.1, 9.2, 9.3_

  - [x]* 10.2 Write property test for boot test argv and sequence detection
    - **Property 7: Boot test imports without an ISO and detects the ordered sequence**
    - **Validates: Requirements 9.1, 9.2**
    - hypothesis, ≥100 iterations, tagged `Feature: proxmox-qcow2-opcp-deployment, Property 7`

  - [x]* 10.3 Write unit tests for `BootTester.run`
    - Mock runner/console output to assert pass path and `BootTestError` on failure
    - _Requirements: 9.1, 9.3_

  - [x]* 10.4 Write integration test for final image positive content guarantee
    - Boot-test the finalized image and inspect the booted system / disk manifest to confirm the Final_Image includes Proxmox VE, Debian base, an EFI partition, a bootloader, standard packages, and admin tools
    - Combine the import-boot console check with a package/manifest assertion (e.g. libguestfs/`virt-ls` + `dpkg`/manifest inspection) rather than property-based testing, per the design's integration-test strategy
    - _Requirements: 13.1_

- [x] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Implement Glance import (pure request builder + import)
  - [x] 12.1 Implement `GlanceImporter`
    - Create `proxmox_install_automation/local_build/glance_importer.py` with pure `build_import_request(name, path)` (disk_format `qcow2`, container_format `bare`, never `kernel_id`/`ramdisk_id`) and `import_image(config) -> str`
    - `import_image()` creates the Glance image and waits for status `active`; raises `GlanceImportError` on timeout
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x]* 12.2 Write property test for Glance import request
    - **Property 8: Glance import request is whole-disk without kernel/ramdisk**
    - **Validates: Requirements 10.1, 10.2**
    - hypothesis, ≥100 iterations, tagged `Feature: proxmox-qcow2-opcp-deployment, Property 8`

  - [x]* 12.3 Write unit tests for `GlanceImporter.import_image`
    - Mock the OpenStack SDK to assert active-status wait and `GlanceImportError` on timeout
    - _Requirements: 10.3, 10.4_

- [x] 13. Implement Ironic deployment (reuses provisioner/orchestrator/gpu)
  - [x] 13.1 Implement `IronicDeployer`
    - Create `proxmox_install_automation/local_build/ironic_deployer.py` with `configure_node(node)` (sets `boot_mode=uefi`) and `deploy(config, glance_image_id) -> str`
    - `deploy()` uses `openstack server create` reusing `auth`, `provisioner`, `orchestrator`, and `gpu` modules; raises `IronicDeployError` on failure
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x]* 13.2 Write unit tests for `IronicDeployer`
    - Mock the OpenStack SDK and reused modules to assert `boot_mode=uefi` is set, `server create` is called, and `IronicDeployError` on failure
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 14. Implement first-boot scaffolding
  - [x] 14.1 Implement `FirstBootScaffolder`
    - Create `proxmox_install_automation/local_build/firstboot_scaffolder.py` with `REQUIRED_TOPICS` and `generate(config) -> list[str]`
    - `generate()` writes cloud-init / systemd first-boot / Ansible artifacts containing a scaffolding section for every required topic (hostname, IP, DNS, NTP, network interfaces, vmbr0 bridge, bonds, VLANs, storage network, cluster/Corosync, ZFS/Ceph); raises `FirstBootScaffoldError` on failure
    - _Requirements: 12.1, 12.2, 12.3_

  - [x]* 14.2 Write property test for first-boot topic coverage
    - **Property 9: First-boot scaffolding covers all required topics**
    - **Validates: Requirements 12.2, 12.3**
    - hypothesis, ≥100 iterations, tagged `Feature: proxmox-qcow2-opcp-deployment, Property 9`

- [x] 15. Implement config loading and validation
  - [x] 15.1 Implement config loader and validator
    - Create `proxmox_install_automation/local_build/config_loader.py` with `load_local_build_config` (YAML → `LocalBuildConfig`/`DeployConfig`)
    - Create `proxmox_install_automation/local_build/config_validator.py` with `LocalBuildConfigValidator`, mirroring `image_builder/config_validator.py`
    - _Requirements: 2.5, 3.5, 14.3_

  - [x]* 15.2 Write unit tests for config loader and validator
    - Assert valid YAML loads into configs and invalid inputs raise typed validation errors
    - _Requirements: 14.3_

- [x] 16. Implement the `LocalImageBuilder` orchestrator
  - [x] 16.1 Implement orchestrator build + deploy sequences
    - Create `proxmox_install_automation/local_build/builder.py` with `LocalImageBuilder.build(config) -> ImageBuildArtifact` and `LocalImageBuilder.deploy(deploy_config) -> DeployResult`
    - `build()` sequences prerequisites → ISO stage → system disk → build VM → operator pause (unless `assume_install_complete`) → clean → finalize → boot test with `try/finally` cleanup of the transient Build_VM; catches and re-raises as `LocalBuildError`
    - `deploy()` sequences Glance import → Ironic deploy → first-boot scaffolding
    - Update `local_build/__init__.py` exports to expose the orchestrator and public components
    - _Requirements: 2.5, 3.5, 4.3, 5.3, 6.1, 7.8, 8.5, 9.3, 10.4, 11.4, 12.1_

  - [x]* 16.2 Write unit tests for the orchestrator
    - Mock all step components to assert ordering, the operator pause gate, `try/finally` Build_VM cleanup on failure, and `LocalBuildError` propagation
    - _Requirements: 2.5, 5.3, 6.3, 8.5_

- [x] 17. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 18. Add the `local-build` CLI subcommand group
  - [x] 18.1 Register `local-build` group and subcommands on the existing `main` group
    - In `proxmox_install_automation/cli.py`, add `@main.group("local-build")` with `check`, `run`, and `deploy` subcommands wired to `PrerequisiteChecker` and `LocalImageBuilder`
    - Each handler loads YAML config, runs the orchestrator, prints a concise result, and uses `sys.exit(0)` on success / non-zero on failure; do NOT modify the existing `install` or `build-image` commands
    - _Requirements: 1.1, 1.2, 14.1, 14.2, 14.3_

  - [x]* 18.2 Write unit tests for the CLI subcommands
    - Assert `build-image` and `install` remain present and unchanged; assert `local-build check/run/deploy` exist
    - _Requirements: 1.1, 1.2, 14.1_

  - [x]* 18.3 Write property test for the CLI exit-code contract
    - **Property 10: CLI exit-code contract**
    - **Validates: Requirements 2.5, 3.5, 4.3, 5.3, 8.5, 9.3, 10.4, 11.4, 14.2**
    - hypothesis, ≥100 iterations, tagged `Feature: proxmox-qcow2-opcp-deployment, Property 10`

  - [x]* 18.4 Write property test for preserved `image_builder` public API
    - **Property 1: Existing image_builder public API is preserved**
    - **Validates: Requirements 1.3**
    - hypothesis, ≥100 iterations, tagged `Feature: proxmox-qcow2-opcp-deployment, Property 1`

- [x] 19. Update `shared/` documentation
  - [x] 19.1 Author `shared/LOCAL_BUILD_context.md` and update existing docs
    - Create `shared/LOCAL_BUILD_context.md` documenting the full pipeline (prerequisites → ISO staging → disk/VM creation → documented interactive install → cleaning → finalization → boot test → Glance import → Ironic deploy → first-boot scaffolding), the interactive install steps (UEFI boot, GPT partitioning, ext4/LVM EFI+root+swap+data, VirtIO disk, explicit ZFS avoidance, not-automated statement), and the generic-image content policy
    - Update `shared/SPECIFY_context.md` and `shared/MODIFY_CODE_context.md` to reference the new `local_build` package and `local-build` subcommands
    - Update `shared/README.md` to link the new procedure
    - _Requirements: 6.1, 6.2, 6.3, 13.1, 13.2, 15.1, 15.2_

- [x] 20. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (unit/property/integration tests) and can be skipped for a faster MVP; core implementation sub-tasks are never optional.
- The plan is strictly additive: no `image_builder` public interface and no `build-image`/`install` CLI command is modified.
- Pure functions (argv builders, plan builders, selectors, detectors) are implemented before the components that use them, so property tests exercise them directly without spawning processes.
- All ten Correctness Properties are implemented as `hypothesis` tests at ≥100 iterations, each tagged `Feature: proxmox-qcow2-opcp-deployment, Property N`, and every test mocks `LocalCommandRunner` and the OpenStack SDK.
- Each task references the specific requirements it satisfies for traceability.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "2.1"] },
    { "id": 3, "tasks": ["2.2", "3.1", "4.1", "5.1", "6.1", "8.1", "9.1", "10.1", "12.1", "13.1", "14.1", "15.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "3.4", "4.2", "4.3", "5.2", "6.2", "6.3", "8.2", "8.3", "9.2", "10.2", "10.3", "10.4", "12.2", "12.3", "13.2", "14.2", "15.2"] },
    { "id": 5, "tasks": ["16.1"] },
    { "id": 6, "tasks": ["16.2"] },
    { "id": 7, "tasks": ["18.1"] },
    { "id": 8, "tasks": ["18.2", "18.3", "18.4", "19.1"] }
  ]
}
```
