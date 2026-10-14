# Local KVM/libvirt Proxmox Image Build and OPCP Deployment

This guide documents the local build path for producing a generic, reusable Proxmox VE
qcow2 image and deploying it to bare-metal hardware on OPCP (OpenStack Glance + Ironic).

The whole pipeline runs on a local Debian/Ubuntu build host: it stages the Proxmox ISO,
creates a temporary build VM with virt-install, guides a documented interactive install,
cleans and compresses the resulting disk, boot-tests it, imports it into Glance, deploys
it to an Ironic bare-metal node, and then scaffolds first-boot configuration.

This local path is **added alongside** the existing remote OpenStack-instance
`image_builder` flow (the `build-image` command). The existing `build-image` behavior is
preserved unchanged. The local path lives in the sibling `local_build` package inside
`proxmox_install_automation` and is driven by the `local-build` CLI subcommands:

- `local-build check -c config.yaml` — verify build-host prerequisites.
- `local-build run -c config.yaml` — run the full image build and produce the final image.
- `local-build deploy -c config.yaml` — import into Glance, deploy via Ironic, and scaffold first boot.

## Pipeline Overview

```
prerequisites check
  -> ISO staging
  -> system disk + build VM creation
  -> documented interactive install (NOT automated)
  -> image cleaning
  -> finalization (undefine, validate, compress)
  -> boot test (no ISO)
  -> Glance import
  -> Ironic deploy
  -> first-boot scaffolding
```

The build phase (through boot test) and the deploy phase (Glance import onward) are
separate subcommands so an operator can build once and deploy the generic image to many
bare-metal nodes.

## Step 1: Prerequisites

**Purpose**: Confirm the build host can run a UEFI KVM guest before anything else starts.

Requirements on the Local Build Host:
- A Debian- or Ubuntu-based operating system.
- Packages: `qemu-utils`, `qemu-system-x86`, `libvirt-daemon-system`, `libvirt-clients`,
  `virtinst`, `ovmf`.

  ```bash
  sudo apt install qemu-utils qemu-system-x86 libvirt-daemon-system \
    libvirt-clients virtinst ovmf
  ```
- KVM hardware acceleration available (`/dev/kvm` present).
- UEFI/OVMF firmware available at `/usr/share/OVMF/OVMF_CODE.fd`.

If any package, KVM acceleration, or the OVMF firmware is missing, the check reports the
missing prerequisite and stops with a non-zero exit code.

**Command**: `local-build check -c config.yaml`

## Step 2: ISO Staging

**Purpose**: Place the Proxmox installation ISO where libvirt can read it.

- Copy the ISO into the libvirt images directory `/var/lib/libvirt/images`.
- Set ownership and permissions so libvirt can read it (`chmod 644`).
- Architecture selection:
  - `x86_64` / `amd64`: stage the standard amd64 ISO.
  - `arm64`: stage the ARM64 ISO (only for ARM build hosts).
- If the source ISO is absent, staging reports the missing ISO and stops with a non-zero
  exit code.

## Step 3: System Disk Creation

**Purpose**: Create the 64GB qcow2 system disk, independent of any data disks.

```bash
qemu-img create -f qcow2 /var/lib/libvirt/images/proxmox-image-builder.qcow2 64G
```

The system disk holds only the operating system; data disks are never part of the generic
image. If the disk cannot be created, the build stops with a non-zero exit code.

## Step 4: Build VM Creation

**Purpose**: Create the temporary `proxmox-image-builder` VM in a UEFI environment.

```bash
virt-install \
  --name proxmox-image-builder \
  --vcpus 8 \
  --memory 16384 \
  --cpu host-passthrough \
  --boot uefi \
  --disk /var/lib/libvirt/images/proxmox-image-builder.qcow2,bus=virtio \
  --network model=virtio \
  --cdrom /var/lib/libvirt/images/<proxmox>.iso
```

The VM is configured with 8 vCPU, 16GB RAM, host CPU passthrough, UEFI boot, a VirtIO
system disk, a VirtIO network interface, and the staged ISO attached as a CD-ROM. If the
VM cannot be created, the build stops with a non-zero exit code.

## Step 5: Documented Interactive Install (NOT automated)

**Purpose**: Produce a template-friendly Proxmox installation consistently.

This install is **interactive and not automated**. Follow these steps in the Proxmox
installer running inside the build VM:

1. **Boot**: UEFI boot (the firmware -> GRUB -> installer).
2. **Partitioning**: GPT partition table.
3. **Filesystem**: ext4 with LVM. Use a simple layout:
   - an EFI system partition,
   - an LVM root volume,
   - an LVM swap volume,
   - an LVM data volume.
4. **Disk**: install onto the VirtIO disk.
5. **Avoid ZFS**: do **not** choose ZFS for the template system disk. ZFS is intentionally
   avoided for the generic image.

When the install completes and the system is ready, confirm to the orchestrator so the
pipeline can continue with cleaning.

## Step 6: Image Cleaning

**Purpose**: Remove host-specific and install-specific state so the image is generic and
safe to reuse across nodes.

Cleaning operations:
- Write a loopback-only `/etc/network/interfaces` (lo only).
- Set the hostname to `pve-template`.
- Remove SSH host keys: `rm -f /etc/ssh/ssh_host_*`.
- Reset machine-id: truncate `/etc/machine-id` and recreate the
  `/var/lib/dbus/machine-id` symlink.
- Remove DHCP lease files: `rm -f /var/lib/dhcp/*`.
- Rotate and vacuum the systemd journal, then remove archived logs:
  `journalctl --rotate`, `journalctl --vacuum-time=1s`, `rm -f /var/log/*.gz`.
- Run `apt clean`.
- Remove any cluster, Corosync, Ceph, or shared-storage configuration. The generic image
  contains no cluster.

## Step 7: Finalization

**Purpose**: Undefine the build VM, validate the disk, and compress the final image.

```bash
# Clean shutdown of the build VM
shutdown -h now

# Undefine the VM but KEEP the system disk qcow2 file
virsh undefine proxmox-image-builder --nvram

# Validate the qcow2 disk
qemu-img check /var/lib/libvirt/images/proxmox-image-builder.qcow2
qemu-img info  /var/lib/libvirt/images/proxmox-image-builder.qcow2

# Compress into the final image
qemu-img convert -O qcow2 -c \
  /var/lib/libvirt/images/proxmox-image-builder.qcow2 \
  proxmox-opcp-final.qcow2
```

The `--nvram` undefine removes the VM definition without deleting the system disk. If
qcow2 validation fails, finalization reports the error and stops with a non-zero exit code.
The final image is named `proxmox-opcp-final.qcow2`.

## Step 8: Boot Test (no ISO)

**Purpose**: Confirm the final image boots to Proxmox VE on its own.

```bash
virt-install --import --boot uefi \
  --name proxmox-boot-test \
  --disk proxmox-opcp-final.qcow2,bus=virtio \
  --network model=virtio
```

The import boot attaches no ISO. The expected boot sequence is UEFI -> GRUB -> Debian
kernel -> Proxmox VE. If the sequence does not reach Proxmox VE, the boot test reports the
failure and stops with a non-zero exit code.

**Command**: `local-build run -c config.yaml` runs the build phase end to end (prerequisites
through boot test).

## Step 9: Glance Import

**Purpose**: Import the final image into OpenStack Glance as a whole-disk image.

```bash
openstack image create \
  --disk-format qcow2 \
  --container-format bare \
  --file proxmox-opcp-final.qcow2 \
  proxmox-opcp
```

This is a whole-disk image: do **not** set `kernel_id` or `ramdisk_id`. After creating the
image, verify its status becomes `active`. If it does not become active within the
configured timeout, the import stops with a non-zero exit code.

## Step 10: Ironic Bare-Metal Deployment

**Purpose**: Deploy the imported image to an Ironic bare-metal node configured for UEFI.

- Configure the Ironic node `boot_mode` to `uefi`.
- Deploy with `openstack server create`:

  ```bash
  openstack server create \
    --flavor <bare-metal-flavor> \
    --image proxmox-opcp \
    --network <network-id> \
    pveNN
  ```

The deploy phase reuses the existing provisioner, orchestrator, and gpu modules where
applicable. If deployment fails, it reports the failure and stops with a non-zero exit code.

**Command**: `local-build deploy -c config.yaml` runs Glance import, Ironic deploy, and
first-boot scaffolding.

## Step 11: Post-Deployment First-Boot Scaffolding

**Purpose**: Apply node-specific configuration after deployment without baking it into the
generic image.

First-boot automation is generated as cloud-init, systemd first-boot, or Ansible
artifacts. The scaffolding covers:
- hostname, IP address, DNS, NTP,
- network interfaces, the `vmbr0` bridge, bonds, VLANs, the storage network,
- cluster/Corosync,
- ZFS/Ceph.

These settings are deliberately kept out of the image and applied per node on first boot.

## Generic Image Content Policy

The final image is intentionally generic so one image can be deployed to many nodes.

**Include** (baked into the image):
- Proxmox VE
- Debian base
- EFI partition
- Bootloader
- Standard packages
- Admin tools

**Exclude** (applied per node at first boot, never baked in):
- Final IP address
- Final hostname
- Hardware-dependent NIC configuration
- Bonds
- Final bridges
- Cluster configuration
- Corosync
- Ceph
- Data ZFS pool
- Any server-specific configuration

## Relationship to the Existing `build-image` Flow

The local build path is additive. The existing remote OpenStack-instance `image_builder`
flow, exposed through the `build-image` command, is preserved and continues to work
unchanged. Use `build-image` for the remote flow and the `local-build` subcommands for the
local KVM/libvirt flow described here.
