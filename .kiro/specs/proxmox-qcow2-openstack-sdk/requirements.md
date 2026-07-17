# Requirements Document

## Introduction

This feature adds Python SDK automation for building Proxmox VE images in qcow2 format on OVH OpenStack. The workflow creates a base instance from a standard SLES image, downloads the Proxmox ISO, converts it to qcow2 format using qemu-img, creates a snapshot, and uploads the final qcow2 image to OpenStack Glance. A new SkillHub chapter documents this approach for training purposes.

## Glossary

- **Image_Builder**: The Python module responsible for orchestrating the qcow2 image creation pipeline
- **Glance_Uploader**: The component that uploads qcow2 images to the OpenStack Glance image service
- **ISO_Converter**: The component that converts a Proxmox ISO file to qcow2 format using qemu-img
- **Base_Instance**: A temporary OpenStack compute instance created from a SLES image, used as the build environment
- **Qcow2_Image**: The final disk image in qcow2 format containing Proxmox VE, ready for OpenStack deployment
- **OpenStack_SDK**: The openstacksdk Python library providing programmatic access to OpenStack services
- **SkillHub_Page**: An HTML lesson page within the SkillHub training website
- **Lessons_Registry**: The JavaScript LESSONS array in lessons.js that defines the navigation and metadata for all chapters

## Requirements

### Requirement 1: Authenticate to OpenStack for Image Building

**User Story:** As a platform engineer, I want to reuse existing OpenStack credentials to build qcow2 images, so that I do not need separate authentication for image operations.

#### Acceptance Criteria

1. WHEN OpenStack credentials are provided with all required fields for the configured authentication method, THE Image_Builder SHALL authenticate using the OpenStack_SDK within 30 seconds and verify connectivity to Compute, Image, and Network services by issuing a test API call to each service endpoint
2. IF authentication fails or any service endpoint is unreachable, THEN THE Image_Builder SHALL raise an error that includes the auth_url, the name of the failing service, and the failure reason returned by the OpenStack_SDK
3. THE Image_Builder SHALL support both application credential (requiring auth_url, region, application_credential_id, and application_credential_secret) and username/password (requiring auth_url, region, username, password, and project_name) authentication methods
4. IF one or more required credential fields for the configured authentication method are missing or empty, THEN THE Image_Builder SHALL raise a validation error listing all missing fields before attempting connection

### Requirement 2: Create Base Instance for Image Building

**User Story:** As a platform engineer, I want to provision a temporary SLES instance, so that it serves as the build environment for the Proxmox qcow2 image.

#### Acceptance Criteria

1. WHEN the image build is initiated, THE Image_Builder SHALL create a Base_Instance from the configured SLES image using the OpenStack_SDK Compute API with the configured flavor, network, and SSH key name
2. WHEN the Base_Instance has been created, THE Image_Builder SHALL poll the instance status at intervals of no more than 10 seconds until the instance reaches ACTIVE status or the configured timeout (default: 600 seconds) is exceeded
3. IF the Base_Instance does not reach ACTIVE status within the configured timeout, THEN THE Image_Builder SHALL raise a timeout error and delete the Base_Instance via the OpenStack_SDK Compute API
4. IF the Base_Instance enters ERROR status during provisioning, THEN THE Image_Builder SHALL raise an instance error indicating the failure and delete the Base_Instance via the OpenStack_SDK Compute API
5. THE Image_Builder SHALL assign a unique name to each Base_Instance using the format `proxmox-installer-{unix_timestamp}` where unix_timestamp is the integer seconds since epoch at creation time

### Requirement 3: Download Proxmox ISO to Base Instance

**User Story:** As a platform engineer, I want the Proxmox ISO to be downloaded to the build instance, so that it can be converted to qcow2 format.

#### Acceptance Criteria

1. WHEN the Base_Instance has reached ACTIVE status and SSH connectivity is established, THE Image_Builder SHALL download the Proxmox ISO from the configured HTTPS URL by executing a download command on the Base_Instance via SSH within a timeout of 1800 seconds
2. WHEN the ISO download completes, THE Image_Builder SHALL verify the ISO download integrity by comparing the downloaded file size in bytes against the expected file size value specified in the build configuration
3. IF the ISO download fails, the download times out, or the integrity check fails, THEN THE Image_Builder SHALL retry the download up to 3 times with a 10-second delay between attempts before raising an error that includes the failure reason and the number of attempts made
4. THE Image_Builder SHALL store the downloaded ISO in a configurable directory on the Base_Instance, defaulting to `/tmp` if no directory is specified in the configuration
5. IF the Base_Instance does not have sufficient disk space to store the ISO file before download begins, THEN THE Image_Builder SHALL raise an error indicating the available space and the required space based on the expected file size

### Requirement 4: Convert ISO to qcow2 Format

**User Story:** As a platform engineer, I want the Proxmox ISO to be converted to qcow2, so that it is compatible with OpenStack Glance.

#### Acceptance Criteria

1. WHEN the ISO download is verified, THE ISO_Converter SHALL execute qemu-img convert to produce a qcow2 file from the ISO within a maximum of 600 seconds
2. THE ISO_Converter SHALL use the command format: `qemu-img convert -f raw -O qcow2 <iso_path> <qcow2_path>`
3. IF the qemu-img conversion fails with a non-zero exit code, THEN THE ISO_Converter SHALL raise an error containing the stderr output
4. WHEN the conversion completes, THE ISO_Converter SHALL verify that the output qcow2 file exists and has a size greater than zero
5. IF the conversion does not complete within 600 seconds, THEN THE ISO_Converter SHALL terminate the qemu-img process and raise a timeout error indicating the elapsed time
6. IF the output qcow2 file does not exist or has a size of zero bytes after conversion, THEN THE ISO_Converter SHALL raise an error indicating the verification failure

### Requirement 5: Create Snapshot from Converted Image

**User Story:** As a platform engineer, I want to create an OpenStack snapshot from the converted image, so that it can serve as an intermediate artifact before final upload.

#### Acceptance Criteria

1. WHEN the qcow2 conversion is complete, THE Image_Builder SHALL create a server snapshot of the Base_Instance using the OpenStack_SDK Compute API
2. THE Image_Builder SHALL assign a name to the snapshot following the format `proxmox-<version>-<YYYYMMDD-HHMMSS>` where `<version>` is the configured Proxmox version and the timestamp represents the build start time in UTC
3. THE Image_Builder SHALL poll the snapshot status at intervals of no more than 10 seconds and wait for it to reach ACTIVE status within the configured timeout (default: 1800 seconds) before proceeding
4. IF the snapshot creation fails or does not reach ACTIVE status within the configured timeout, THEN THE Image_Builder SHALL raise an error indicating the snapshot name, last observed status, and elapsed wait time, and SHALL delete the failed snapshot and the Base_Instance

### Requirement 6: Upload qcow2 Image to Glance

**User Story:** As a platform engineer, I want the final qcow2 image uploaded to OpenStack Glance, so that it is available as a bootable image in the local repository.

#### Acceptance Criteria

1. WHEN the qcow2 file exists on the Base_Instance and the conversion has completed successfully, THE Glance_Uploader SHALL upload the image to OpenStack Glance using the OpenStack_SDK Image API
2. THE Glance_Uploader SHALL set the image disk format to "qcow2" and the container format to "bare"
3. THE Glance_Uploader SHALL set image metadata with at minimum: name (matching the target image name from configuration), Proxmox version, build timestamp in ISO 8601 format, and visibility (private by default)
4. WHEN the upload completes, THE Glance_Uploader SHALL poll the image status until it reaches ACTIVE, with a polling interval of 10 seconds and a maximum wait time equal to the configured build timeout
5. IF the image status becomes ERROR or does not reach ACTIVE within the configured timeout, THEN THE Glance_Uploader SHALL raise an error indicating the final image status and image ID
6. IF the upload fails, THEN THE Glance_Uploader SHALL retry up to 3 times before raising an error with the HTTP status code and response body

### Requirement 7: Cleanup Build Resources

**User Story:** As a platform engineer, I want all temporary resources cleaned up after image building, so that I do not incur unnecessary costs.

#### Acceptance Criteria

1. WHEN the image build completes successfully, THE Image_Builder SHALL destroy the Base_Instance and its associated floating IP within 120 seconds
2. WHEN the image build completes successfully, THE Image_Builder SHALL destroy the intermediate snapshot created during the build process
3. WHEN the image build fails at any step, THE Image_Builder SHALL attempt to destroy the Base_Instance, its associated floating IP, and any intermediate snapshots, retrying each destruction operation up to 3 times before moving to the next resource
4. THE Image_Builder SHALL log each cleanup operation with the resource type, resource identifier, and outcome (success or failure)
5. IF cleanup of a resource fails after all retry attempts, THEN THE Image_Builder SHALL log a warning with the resource type and resource identifier and continue cleaning up remaining resources
6. THE Image_Builder SHALL clean up resources in reverse creation order: intermediate snapshots first, then the Base_Instance, then the floating IP

### Requirement 8: CLI Integration for Image Building

**User Story:** As a platform engineer, I want to trigger the qcow2 image build from the command line, so that I can integrate it into my automation scripts.

#### Acceptance Criteria

1. THE CLI SHALL expose a `build-image` subcommand that triggers the qcow2 image building pipeline
2. THE CLI SHALL accept a required `--config` option pointing to a YAML configuration file containing image build parameters
3. THE CLI SHALL accept a `--dry-run` option that validates the configuration and outputs a validation success or failure message to stdout without executing the build, exiting with code 0 on valid configuration and code 1 on invalid configuration
4. WHEN the build completes successfully, THE CLI SHALL print the Glance image ID and image name to stdout and exit with code 0
5. IF the build fails, THEN THE CLI SHALL print the error message to stderr and exit with a non-zero status code
6. IF the `--config` file does not exist or contains invalid YAML, THEN THE CLI SHALL print an error message indicating the file path and the nature of the failure to stderr, and exit with a non-zero status code
7. THE CLI SHALL direct all informational build output to stdout and all error messages to stderr, so that automation scripts can parse stdout independently of error output

### Requirement 9: Configuration Model for Image Building

**User Story:** As a platform engineer, I want a structured configuration for the image build, so that I can customize the ISO URL, flavor, and target image properties.

#### Acceptance Criteria

1. THE Image_Builder SHALL accept configuration via a dataclass model including the following required fields: ISO URL, base image name, flavor name, and target image name; and the following optional fields: target image visibility and build timeouts
2. THE Image_Builder SHALL provide defaults for optional configuration fields: visibility set to "private", and build timeout set to 1800 seconds
3. IF one or more required configuration fields (ISO URL, base image name, flavor name, or target image name) are missing, THEN THE Image_Builder SHALL raise a validation error listing all missing field names in a single error
4. IF the ISO URL does not use the HTTPS protocol, THEN THE Image_Builder SHALL raise a validation error indicating the URL must use HTTPS
5. THE Image_Builder SHALL validate that the target image visibility value is one of "private", "shared", or "public"
6. THE Image_Builder SHALL validate that the build timeout value is between 60 and 7200 seconds inclusive

### Requirement 10: SkillHub Chapter for Proxmox qcow2 Image Building

**User Story:** As a learner, I want a SkillHub lesson explaining the Python SDK approach for building Proxmox qcow2 images, so that I can understand and replicate the process.

#### Acceptance Criteria

1. THE SkillHub_Page SHALL be created as an HTML file named `qcow2-image-building.html` in both `skillhub/en/` and `skillhub/fr/` directories, reusing the same document structure as existing lesson pages (header with language toggle and progress bar, sidebar navigation, main content area with breadcrumbs)
2. THE SkillHub_Page SHALL include the following sections in order: overview, prerequisites, step-by-step workflow (instance creation, ISO download, conversion to qcow2, snapshot creation, upload to Glance), configuration reference, and CLI usage
3. THE Lessons_Registry SHALL include a new entry in `skillhub/assets/js/lessons.js` for the qcow2 image building lesson with id `qcow2-image-building`, slug `qcow2-image-building`, titles in EN and FR, difficulty set to one of the valid values (`beginner`, `intermediate`, `advanced`), estimatedMinutes as a positive integer, and a prerequisites array referencing at least one existing lesson id
4. THE SkillHub_Page SHALL include at least one Python code example using the OpenStack_SDK Python API for each of the 5 workflow steps (instance creation, ISO download, conversion, snapshot, upload)
5. THE SkillHub_Page SHALL follow the existing accessibility patterns including ARIA labels on interactive elements, semantic HTML elements (`header`, `main`, `aside`, `nav`), and keyboard-focusable navigation links
6. WHEN the Lessons_Registry is updated with the new entry, THE SkillHub_Page SHALL appear in the sidebar navigation on all lesson pages without requiring additional configuration
