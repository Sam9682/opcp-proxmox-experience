# Implementation Plan: Proxmox qcow2 OpenStack SDK

## Overview

This implementation plan breaks down the Proxmox qcow2 image building feature into incremental coding tasks. The pipeline orchestrates: authenticate → create instance → download ISO → convert to qcow2 → snapshot → upload to Glance → cleanup. A CLI subcommand (`build-image`) exposes the pipeline, and a SkillHub chapter documents the approach.

All code is Python, using the existing project patterns (dataclasses, openstacksdk, Click CLI, hypothesis for property tests).

## Tasks

- [x] 1. Set up module structure and data models
  - [x] 1.1 Create the `image_builder` package directory and core data models
    - Create `proxmox_install_automation/image_builder/__init__.py`
    - Create `proxmox_install_automation/image_builder/models.py` with `ImageBuildConfig`, `ImageBuildResult`, `ImageMetadata`, `CleanupResource`, and `CleanupReport` dataclasses
    - Add default values for optional fields: `target_visibility="private"`, `build_timeout=1800`, `iso_download_dir="/tmp"`, `iso_download_timeout=1800`, `conversion_timeout=600`, `snapshot_timeout=1800`
    - _Requirements: 9.1, 9.2_

  - [x] 1.2 Create custom exception classes
    - Create `proxmox_install_automation/image_builder/exceptions.py`
    - Define `ImageBuildError`, `ISODownloadError`, `ISOConversionError`, `SnapshotError`, `GlanceUploadError` extending `ProxmoxAutomationError`
    - Ensure `ConfigurationError` and `AuthenticationError` are available (extend existing or create if needed)
    - _Requirements: 1.2, 3.3, 4.3, 5.4, 6.5_

  - [x] 1.3 Create the configuration validator
    - Create `proxmox_install_automation/image_builder/config_validator.py` with `ImageBuildConfigValidator` class
    - Validate all required fields present and non-empty (iso_url, base_image_name, flavor_name, target_image_name)
    - Validate iso_url starts with `https://`
    - Validate target_visibility ∈ {"private", "shared", "public"}
    - Validate build_timeout ∈ [60, 7200]
    - Raise a single `ConfigurationError` listing all validation failures
    - _Requirements: 9.3, 9.4, 9.5, 9.6, 1.4_

  - [ ]* 1.4 Write property tests for configuration validation
    - **Property 1: Missing required fields validation** — Generate random subsets of required fields to omit, verify error lists exactly those missing fields
    - **Property 2: Configuration rejects invalid values** — Generate invalid URLs, invalid visibility strings, out-of-range timeouts, verify rejection
    - **Validates: Requirements 1.4, 9.3, 9.4, 9.5, 9.6**

  - [ ]* 1.5 Write unit tests for data models and defaults
    - Test that `ImageBuildConfig` defaults are correctly applied
    - Test that `ImageBuildResult` and `ImageMetadata` instantiate properly
    - _Requirements: 9.1, 9.2_

- [x] 2. Implement authentication and service verification
  - [x] 2.1 Implement authentication extension for image building
    - Create `proxmox_install_automation/image_builder/auth.py`
    - Implement `ImageBuildAuthManager` that wraps the existing `OpenStackAuthManager`
    - After authentication, verify connectivity to Compute, Image, and Network services by issuing a test API call to each
    - Support both application credential and username/password authentication methods
    - Raise `AuthenticationError` with auth_url, failing service name, and failure reason on failure
    - Authentication must complete within 30 seconds
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 2.2 Write property test for authentication error context
    - **Property 8: Authentication error includes full context** — Generate random (auth_url, service_name, failure_reason) tuples, verify the error message contains all three values
    - **Validates: Requirements 1.2**

  - [ ]* 2.3 Write unit tests for authentication
    - Test application credential authentication path (mock OpenStack SDK)
    - Test username/password authentication path (mock OpenStack SDK)
    - Test missing credential field detection
    - Test service endpoint verification failure
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 3. Implement instance provisioning for image building
  - [x] 3.1 Implement the instance creation component
    - Create `proxmox_install_automation/image_builder/instance.py`
    - Implement `ImageBuildInstanceManager` that uses OpenStack SDK Compute API to create instances
    - Generate instance name using format `proxmox-installer-{unix_timestamp}`
    - Poll instance status every 10 seconds until ACTIVE or timeout (default 600s)
    - Delete instance on ERROR status or timeout
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 3.2 Write property test for instance naming
    - **Property 3: Instance naming format** — Generate random positive integers as timestamps, verify name matches `proxmox-installer-{timestamp}` pattern exactly
    - **Validates: Requirements 2.5**

  - [ ]* 3.3 Write unit tests for instance provisioning
    - Test instance creation with correct parameters
    - Test polling until ACTIVE
    - Test timeout triggers deletion
    - Test ERROR status triggers deletion
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 4. Implement ISO download and verification
  - [x] 4.1 Implement the ISO downloader component
    - Create `proxmox_install_automation/image_builder/iso_downloader.py`
    - Implement `ISODownloader` class with `check_disk_space()`, `download()`, and `verify_integrity()` methods
    - Execute download via SSH on the build instance (wget/curl) with configurable timeout (default 1800s)
    - Verify integrity by comparing downloaded file size to expected size from config
    - Retry up to 3 times with 10-second delay on failure
    - Check disk space before download, raise error with available vs required bytes
    - Store ISO in configurable directory (default `/tmp`)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 4.2 Write property tests for ISO integrity and disk space errors
    - **Property 6: ISO integrity check is strict equality** — Generate random (actual_size, expected_size) pairs, verify pass iff equal
    - **Property 9: Disk space error includes both values** — Generate random (available, required) where available < required, verify error contains both values
    - **Validates: Requirements 3.2, 3.5**

  - [ ]* 4.3 Write unit tests for ISO downloader
    - Test successful download flow (mock SSH)
    - Test retry logic on download failure
    - Test integrity check pass/fail
    - Test disk space check failure
    - Test timeout handling
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 5. Implement ISO to qcow2 conversion
  - [x] 5.1 Implement the ISO converter component
    - Create `proxmox_install_automation/image_builder/iso_converter.py`
    - Implement `ISOConverter` class with `convert()` and `verify_output()` methods
    - Execute `qemu-img convert -f raw -O qcow2 <iso_path> <qcow2_path>` via SSH
    - Kill process and raise timeout error if conversion exceeds 600 seconds
    - Raise `ISOConversionError` with stderr on non-zero exit code
    - Verify output file exists and has size > 0
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 5.2 Write property tests for ISO converter
    - **Property 5: qemu-img command construction** — Generate random valid file path pairs, verify command is exactly `qemu-img convert -f raw -O qcow2 {iso_path} {qcow2_path}`
    - **Property 10: Conversion error propagates stderr** — Generate random non-empty stderr strings, verify `ISOConversionError` contains that stderr string
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 5.3 Write unit tests for ISO converter
    - Test successful conversion (mock SSH)
    - Test non-zero exit code handling
    - Test timeout handling and process kill
    - Test output verification (file not found, zero size)
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6_

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement snapshot management
  - [x] 7.1 Implement the snapshot manager component
    - Create `proxmox_install_automation/image_builder/snapshot.py`
    - Implement `SnapshotManager` class with `create_snapshot()`, `wait_for_active()`, and `delete_snapshot()` methods
    - Use OpenStack SDK Compute API to create server snapshots
    - Name snapshots using format `proxmox-{version}-{YYYYMMDD-HHMMSS}` (UTC build start time)
    - Poll every 10 seconds, timeout configurable (default 1800s)
    - Raise `SnapshotError` with snapshot name, last status, and elapsed time on failure
    - Delete failed snapshot and instance on failure
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 7.2 Write property test for snapshot naming
    - **Property 4: Snapshot naming format** — Generate random version strings and UTC datetimes, verify snapshot name matches `proxmox-{version}-{YYYYMMDD-HHMMSS}` with correct zero-padding
    - **Validates: Requirements 5.2**

  - [ ]* 7.3 Write unit tests for snapshot manager
    - Test successful snapshot creation and wait
    - Test timeout handling with deletion
    - Test snapshot failure status handling
    - _Requirements: 5.1, 5.3, 5.4_

- [x] 8. Implement Glance image upload
  - [x] 8.1 Implement the Glance uploader component
    - Create `proxmox_install_automation/image_builder/glance_uploader.py`
    - Implement `GlanceUploader` class with `upload()` and `wait_for_active()` methods
    - Upload qcow2 image using OpenStack SDK Image API
    - Set disk_format="qcow2", container_format="bare"
    - Set metadata: name, proxmox_version, build_timestamp (ISO 8601), visibility
    - Poll every 10 seconds until ACTIVE or timeout
    - Retry upload up to 3 times on failure
    - Raise `GlanceUploadError` with HTTP status and response body on final failure
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 8.2 Write property test for Glance metadata completeness
    - **Property 7: Glance image metadata completeness** — Generate random valid configs, verify metadata contains all required fields with correct values
    - **Validates: Requirements 6.2, 6.3**

  - [ ]* 8.3 Write unit tests for Glance uploader
    - Test successful upload flow (mock OpenStack SDK)
    - Test retry logic on upload failure
    - Test image status polling (ACTIVE, ERROR, timeout)
    - Test metadata is correctly set
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 9. Implement cleanup manager
  - [x] 9.1 Implement the cleanup manager component
    - Create `proxmox_install_automation/image_builder/cleanup.py`
    - Implement `ImageBuildCleanupManager` class with `cleanup()` method
    - Destroy resources in reverse creation order: snapshots → instances → floating IPs
    - Retry each destruction up to 3 times
    - Log each operation with resource type, identifier, and outcome
    - On failure after retries, log warning and continue to next resource
    - Return `CleanupReport` with totals and failures
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ]* 9.2 Write property test for cleanup ordering
    - **Property 11: Cleanup ordering invariant** — Generate random sets of resources (snapshot, instance, floating_ip), verify cleanup processes them in order: snapshots first, then instances, then floating IPs
    - **Validates: Requirements 7.6**

  - [ ]* 9.3 Write unit tests for cleanup manager
    - Test successful cleanup of all resources
    - Test partial failure with retry and continue
    - Test logging of each operation
    - Test cleanup within 120 second budget
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 10. Implement the orchestrator and CLI
  - [x] 10.1 Implement the ImageBuilder orchestrator
    - Create `proxmox_install_automation/image_builder/builder.py`
    - Implement `ImageBuilder` class with `build()` and `validate_config()` methods
    - Orchestrate all pipeline steps in sequence: validate → auth → create instance → wait → SSH → disk space check → download ISO → verify → convert → verify → snapshot → wait → upload → wait → cleanup
    - Use try/finally pattern to ensure cleanup runs on any failure
    - Return `ImageBuildResult` on success with image_id, image_name, and build_duration_seconds
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1, 7.3_

  - [x] 10.2 Implement the YAML configuration loader
    - Create `proxmox_install_automation/image_builder/config_loader.py`
    - Implement `load_image_build_config(path: str) -> ImageBuildConfig` function
    - Parse YAML file and map to `ImageBuildConfig` dataclass
    - Raise error if file does not exist or contains invalid YAML
    - _Requirements: 8.2, 8.6_

  - [x] 10.3 Implement the `build-image` CLI subcommand
    - Add `build-image` command to the existing Click CLI in `proxmox_install_automation/cli.py`
    - Accept required `--config` option (path to YAML file)
    - Accept `--dry-run` flag that validates config and exits (code 0 valid, code 1 invalid)
    - On success: print Glance image ID and name to stdout, exit 0
    - On failure: print error to stderr, exit non-zero
    - Direct informational output to stdout, errors to stderr
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 10.4 Write unit tests for CLI and orchestrator
    - Test `--dry-run` with valid config (exit 0)
    - Test `--dry-run` with invalid config (exit 1)
    - Test CLI output format on success (image ID + name on stdout)
    - Test CLI error output on failure (stderr, non-zero exit)
    - Test missing/invalid YAML file handling
    - Test orchestrator pipeline integration (mock all components)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Implement SkillHub chapter
  - [x] 12.1 Create the SkillHub HTML lesson pages (EN and FR)
    - Create `skillhub/en/qcow2-image-building.html` and `skillhub/fr/qcow2-image-building.html`
    - Reuse existing document structure: header with language toggle and progress bar, sidebar navigation, main content area with breadcrumbs
    - Include sections in order: overview, prerequisites, step-by-step workflow (instance creation, ISO download, conversion to qcow2, snapshot creation, upload to Glance), configuration reference, CLI usage
    - Include at least one Python code example using OpenStack SDK for each of the 5 workflow steps
    - Follow accessibility patterns: ARIA labels, semantic HTML (`header`, `main`, `aside`, `nav`), keyboard-focusable links
    - _Requirements: 10.1, 10.2, 10.4, 10.5_

  - [x] 12.2 Register the lesson in the SkillHub lessons registry
    - Update `skillhub/assets/js/lessons.js` to add a new entry in the LESSONS array
    - Set id: `qcow2-image-building`, slug: `qcow2-image-building`, titles in EN and FR
    - Set difficulty level, estimatedMinutes, and prerequisites array referencing at least one existing lesson id
    - Verify the lesson appears in sidebar navigation on all pages
    - _Requirements: 10.3, 10.6_

  - [ ]* 12.3 Write tests for SkillHub HTML and registry
    - Test HTML structure validation (semantic elements, ARIA labels)
    - Test lessons.js entry has all required fields
    - Test both EN and FR pages exist and follow the same structure
    - _Requirements: 10.1, 10.3, 10.5_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation uses Python with openstacksdk, Click, dataclasses, and hypothesis (all existing project dependencies)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5"] },
    { "id": 2, "tasks": ["2.1", "3.1", "4.1", "5.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "3.2", "3.3", "4.2", "4.3", "5.2", "5.3"] },
    { "id": 4, "tasks": ["7.1", "8.1", "9.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "8.2", "8.3", "9.2", "9.3"] },
    { "id": 6, "tasks": ["10.1", "10.2"] },
    { "id": 7, "tasks": ["10.3", "10.4"] },
    { "id": 8, "tasks": ["12.1", "12.2"] },
    { "id": 9, "tasks": ["12.3"] }
  ]
}
```
