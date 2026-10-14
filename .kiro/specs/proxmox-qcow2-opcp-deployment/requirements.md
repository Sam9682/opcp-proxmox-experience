# Requirements Document

## Introduction

This feature adds a new local KVM/libvirt build path to the `proxmox_install_automation` project for producing a generic, reusable Proxmox VE qcow2 image. The new path runs end to end on a local Debian/Ubuntu build host — staging the Proxmox ISO, creating a temporary build VM with virt-install, guiding a documented interactive install, cleaning and compressing the resulting disk, boot-testing it, importing it into OpenStack Glance, and deploying it to an Ironic bare-metal node — followed by post-deployment first-boot configuration scaffolding.

The local build path is added alongside the existing remote OpenStack-instance `image_builder` flow. The existing `image_builder` behavior is preserved unchanged. New capabilities are exposed as new subcommands on the existing Click CLI group (`cli.py`) and reuse the existing provisioner, orchestrator, and gpu modules where applicable. The shared lab and procedure documents under `shared/` are updated to reflect this documented workflow.

The produced image is intentionally generic: it contains Proxmox VE, Debian, an EFI partition, a bootloader, and standard admin tooling, but excludes any server-specific or hardware-dependent configuration so that one image can be deployed to many bare-metal nodes.

## Glossary

- **Local_Build_Host**: A Debian- or Ubuntu-based machine with KVM, libvirt, and virtualization tooling installed, on which the local qcow2 image is built.
- **Prerequisite_Checker**: The component that verifies required packages, KVM acceleration, and UEFI/OVMF firmware availability on the Local_Build_Host.
- **ISO_Stager**: The component that places the Proxmox installation ISO into the libvirt images directory with correct ownership and permissions.
- **Build_VM**: The temporary virtual machine, named `proxmox-image-builder`, created via virt-install to perform the Proxmox interactive install.
- **System_Disk**: The 64GB qcow2 disk created as the Build_VM boot and system volume.
- **Image_Cleaner**: The component that removes host-specific and installation-specific state from the installed image after installation.
- **Image_Finalizer**: The component that undefines the Build_VM, validates the qcow2 disk, and compresses it into the final image.
- **Boot_Tester**: The component that performs an ISO-less import boot test of the final image.
- **Glance_Importer**: The component that imports the final qcow2 image into OpenStack Glance as a whole-disk image.
- **Ironic_Deployer**: The component that configures an Ironic bare-metal node for UEFI boot and deploys the imported image to it.
- **FirstBoot_Scaffolder**: The component that generates post-deployment first-boot automation artifacts (cloud-init, systemd first-boot, or Ansible) for applying node-specific configuration.
- **Final_Image**: The compressed, generic qcow2 image file named `proxmox-opcp-final.qcow2`.
- **CLI**: The existing Click command group defined in `proxmox_install_automation/cli.py`.
- **libvirt_images_dir**: The directory `/var/lib/libvirt/images`.

## Requirements

### Requirement 1: Preserve Existing Image Builder Flow

**User Story:** As a maintainer, I want the existing remote OpenStack-instance image_builder flow to remain intact, so that current build pipelines continue to work after the local build path is added.

#### Acceptance Criteria

1. THE CLI SHALL retain the existing `build-image` command with unchanged behavior.
2. THE CLI SHALL expose the local build path through new subcommands that are distinct from the existing `build-image` command.
3. WHERE the local build path is added, THE System SHALL preserve the existing `image_builder` module public interfaces.

### Requirement 2: Local Build Host Prerequisites Check

**User Story:** As an operator, I want the build host prerequisites verified before a build starts, so that failures from missing tooling are caught early.

#### Acceptance Criteria

1. WHEN a local build is requested, THE Prerequisite_Checker SHALL verify that the Local_Build_Host runs a Debian- or Ubuntu-based operating system.
2. WHEN a local build is requested, THE Prerequisite_Checker SHALL verify that the packages qemu-utils, qemu-system-x86, libvirt-daemon-system, libvirt-clients, virtinst, and ovmf are installed.
3. WHEN a local build is requested, THE Prerequisite_Checker SHALL verify that KVM hardware acceleration is available.
4. WHEN a local build is requested, THE Prerequisite_Checker SHALL verify that UEFI/OVMF firmware is available.
5. IF a required package, KVM acceleration, or UEFI/OVMF firmware is unavailable, THEN THE Prerequisite_Checker SHALL report the missing prerequisite and stop the build with a non-zero exit code.

### Requirement 3: ISO Staging

**User Story:** As an operator, I want the Proxmox ISO staged into the libvirt images directory with correct permissions, so that the Build_VM can boot from it.

#### Acceptance Criteria

1. WHEN a local build is requested, THE ISO_Stager SHALL place the Proxmox installation ISO into the libvirt_images_dir.
2. WHEN the ISO is staged, THE ISO_Stager SHALL set ownership and permissions that allow libvirt to read the staged ISO.
3. WHERE the target architecture is x86_64 or amd64, THE ISO_Stager SHALL stage the standard x86_64/amd64 ISO.
4. WHERE the target architecture is ARM64, THE ISO_Stager SHALL stage the ARM64 ISO.
5. IF the ISO is not present at the configured source, THEN THE ISO_Stager SHALL report the missing ISO and stop the build with a non-zero exit code.

### Requirement 4: System Disk Creation

**User Story:** As an operator, I want a 64GB qcow2 system disk created independently of data disks, so that the generic image contains only the operating system.

#### Acceptance Criteria

1. WHEN a local build is requested, THE System SHALL create a qcow2 System_Disk with a capacity of 64GB.
2. THE System SHALL create the System_Disk independently of any future data disks.
3. IF the System_Disk cannot be created, THEN THE System SHALL report the failure and stop the build with a non-zero exit code.

### Requirement 5: Build VM Creation

**User Story:** As an operator, I want a temporary build VM created via virt-install with defined resources, so that the Proxmox installer can run in a UEFI environment.

#### Acceptance Criteria

1. WHEN the System_Disk and staged ISO are ready, THE System SHALL create the Build_VM via virt-install named `proxmox-image-builder`.
2. THE System SHALL configure the Build_VM with 8 vCPU, 16GB RAM, host CPU passthrough, UEFI boot, a VirtIO disk, a VirtIO network interface, and the staged ISO attached as a CD-ROM.
3. IF the Build_VM cannot be created, THEN THE System SHALL report the failure and stop the build with a non-zero exit code.

### Requirement 6: Documented Interactive Install

**User Story:** As an operator, I want documented interactive install guidance, so that I can produce a template-friendly Proxmox installation consistently.

#### Acceptance Criteria

1. THE System SHALL provide documented steps for the interactive Proxmox install covering UEFI boot, GPT partitioning, a simple ext4/LVM layout with EFI, LVM root, LVM swap, and LVM data, and a VirtIO disk.
2. THE System SHALL document that ZFS is avoided for the template image.
3. WHERE the install is interactive, THE System SHALL document that the install is not automated.

### Requirement 7: Post-Install Image Cleaning

**User Story:** As an operator, I want the installed image cleaned of host-specific state, so that the resulting image is generic and safe to reuse across nodes.

#### Acceptance Criteria

1. WHEN post-install cleaning runs, THE Image_Cleaner SHALL write a generic loopback-only `/etc/network/interfaces`.
2. WHEN post-install cleaning runs, THE Image_Cleaner SHALL set the hostname to `pve-template`.
3. WHEN post-install cleaning runs, THE Image_Cleaner SHALL remove SSH host keys.
4. WHEN post-install cleaning runs, THE Image_Cleaner SHALL reset machine-id and recreate the dbus machine-id symlink.
5. WHEN post-install cleaning runs, THE Image_Cleaner SHALL remove DHCP lease files.
6. WHEN post-install cleaning runs, THE Image_Cleaner SHALL rotate and vacuum the systemd journal and remove archived log files.
7. WHEN post-install cleaning runs, THE Image_Cleaner SHALL run apt clean.
8. THE Image_Cleaner SHALL exclude cluster, Corosync, Ceph, and shared-storage configuration from the cleaned image.

### Requirement 8: Image Finalization

**User Story:** As an operator, I want the build VM undefined and the disk validated and compressed, so that I obtain a verified, compact final image.

#### Acceptance Criteria

1. WHEN cleaning is complete, THE System SHALL perform a clean shutdown of the Build_VM.
2. WHEN the Build_VM is shut down, THE Image_Finalizer SHALL run `virsh undefine proxmox-image-builder --nvram` while retaining the System_Disk qcow2 file.
3. WHEN the Build_VM is undefined, THE Image_Finalizer SHALL validate the qcow2 disk using qemu-img check and qemu-img info.
4. WHEN validation passes, THE Image_Finalizer SHALL compress the disk via `qemu-img convert -O qcow2 -c` to produce the Final_Image named `proxmox-opcp-final.qcow2`.
5. IF qcow2 validation fails, THEN THE Image_Finalizer SHALL report the validation error and stop the build with a non-zero exit code.

### Requirement 9: ISO-less Boot Test

**User Story:** As an operator, I want the final image boot-tested without the ISO, so that I can confirm it boots to Proxmox VE on its own.

#### Acceptance Criteria

1. WHEN the Final_Image is produced, THE Boot_Tester SHALL boot the Final_Image using virt-install import mode without attaching an ISO.
2. WHEN the boot test runs, THE Boot_Tester SHALL confirm the boot sequence reaches UEFI, then GRUB, then the Debian kernel, then Proxmox VE.
3. IF the boot test does not reach Proxmox VE, THEN THE Boot_Tester SHALL report the boot test failure and stop the build with a non-zero exit code.

### Requirement 10: Glance Import

**User Story:** As an operator, I want the final image imported into Glance as a whole-disk image, so that it can be deployed by OpenStack.

#### Acceptance Criteria

1. WHEN the boot test passes, THE Glance_Importer SHALL create a Glance image from the Final_Image using disk-format qcow2 and container-format bare.
2. THE Glance_Importer SHALL import the Final_Image as a whole-disk image without setting kernel_id or ramdisk_id.
3. WHEN the Glance import completes, THE Glance_Importer SHALL verify that the image status is active.
4. IF the Glance image status does not become active within the configured timeout, THEN THE Glance_Importer SHALL report the failure and stop the build with a non-zero exit code.

### Requirement 11: Ironic Bare-Metal Deployment

**User Story:** As an operator, I want to deploy the imported image to an Ironic bare-metal node configured for UEFI, so that the generic image runs on physical hardware.

#### Acceptance Criteria

1. WHEN a bare-metal deployment is requested, THE Ironic_Deployer SHALL configure the Ironic node boot_mode to uefi.
2. WHEN the node is configured, THE Ironic_Deployer SHALL deploy the imported image via `openstack server create`.
3. THE Ironic_Deployer SHALL reuse the existing provisioner, orchestrator, and gpu modules where applicable for deployment.
4. IF the deployment fails, THEN THE Ironic_Deployer SHALL report the failure and stop with a non-zero exit code.

### Requirement 12: Post-Deployment First-Boot Scaffolding

**User Story:** As an operator, I want first-boot automation scaffolding generated, so that node-specific configuration is applied after deployment without baking it into the generic image.

#### Acceptance Criteria

1. WHEN a deployment completes, THE FirstBoot_Scaffolder SHALL generate first-boot automation artifacts using cloud-init, systemd first-boot, or Ansible.
2. THE FirstBoot_Scaffolder SHALL include scaffolding for hostname, IP address, DNS, NTP, network interfaces, the vmbr0 bridge, bonds, VLANs, and the storage network.
3. THE FirstBoot_Scaffolder SHALL include scaffolding for cluster/Corosync and ZFS/Ceph configuration.

### Requirement 13: Generic Image Content Policy

**User Story:** As an operator, I want the image to stay generic, so that a single image can be deployed to many nodes without rework.

#### Acceptance Criteria

1. THE Final_Image SHALL include Proxmox VE, Debian, an EFI partition, a bootloader, standard packages, and admin tools.
2. THE Final_Image SHALL exclude the final IP address, the final hostname, hardware-dependent NIC configuration, bonds, final bridges, cluster configuration, Corosync, Ceph, a data ZFS pool, and server-specific configuration.

### Requirement 14: CLI Integration

**User Story:** As an operator, I want the local build and deployment steps exposed as CLI subcommands, so that I can run the workflow through the existing tooling.

#### Acceptance Criteria

1. THE CLI SHALL expose the local build path as new subcommands on the existing Click command group in `cli.py`.
2. WHEN a new subcommand is invoked, THE CLI SHALL report success with a zero exit code and failure with a non-zero exit code.
3. THE CLI SHALL implement new subcommands in Python consistent with the existing command structure.

### Requirement 15: Lab Procedure Documentation Alignment

**User Story:** As a maintainer, I want the shared lab and procedure documents updated, so that the documented workflow reflects the local build path.

#### Acceptance Criteria

1. WHEN the local build path is added, THE System SHALL update the lab and procedure documents under `shared/` to describe the documented local KVM/libvirt build workflow.
2. THE System SHALL document the full pipeline from prerequisites check through post-deployment first-boot scaffolding in the shared documents.
