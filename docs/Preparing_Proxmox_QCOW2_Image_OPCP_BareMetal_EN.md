# Preparing a Proxmox VE QCOW2 Image for Bare Metal Deployment on OPCP

## 1. Objective

This document describes the procedure for creating a **Proxmox VE** image in **QCOW2** format, intended to be imported into **OpenStack Glance** and then deployed to a physical server using **OPCP / Ironic Bare Metal**.

The objective is to provide a generic image that can be used to provision multiple Proxmox servers.

The image must contain:

- Proxmox VE installed;
- a GPT partition table;
- UEFI boot;
- a functional Debian / Proxmox system;
- a system disk independent from future data disks.

Server-specific settings must be configured after deployment:

- server name;
- IP address;
- network interfaces;
- bridges and bonds;
- Proxmox cluster;
- ZFS / Ceph storage;
- Corosync configuration.

---

## 2. Target Architecture

The principle is as follows:

```text
Proxmox VE ISO
      |
      v
+---------------------------+
| Temporary KVM/QEMU VM     |
|                           |
| UEFI                      |
| 8 vCPU                    |
| 16 GB RAM                 |
| 64 GB QCOW2 Disk          |
+-------------+-------------+
              |
              | Proxmox installation
              v
+---------------------------+
| proxmox-opcp.qcow2        |
|                           |
| GPT                       |
| EFI                       |
| Debian                    |
| Proxmox VE                |
+-------------+-------------+
              |
              | Glance import
              v
+---------------------------+
| OPCP / OpenStack / Ironic |
+-------------+-------------+
              |
              v
       Bare Metal Server
```

---

## 3. CPU Architecture

For servers based on Intel Xeon or AMD EPYC processors, use the standard version:

```text
Architecture: x86_64 / amd64
```

Example:

```text
proxmox-ve_9.2-1.iso
```

The ARM64 version should only be used for servers equipped with an ARM64 processor.

---

## 4. Prerequisites

The machine used to build the image must have:

- Debian or Ubuntu;
- QEMU;
- libvirt;
- virt-install;
- qemu-img;
- UEFI / OVMF support;
- preferably KVM hardware acceleration.

Install the required packages:

```bash
apt update

apt install -y \
  qemu-utils \
  qemu-system-x86 \
  libvirt-daemon-system \
  libvirt-clients \
  virtinst \
  ovmf
```

Check the tools:

```bash
qemu-img --version
virsh --version
virt-install --version
```

---

## 5. Preparing the Proxmox ISO

Copy the Proxmox ISO into the libvirt directory:

```bash
cp proxmox-ve_9.2-1.iso /var/lib/libvirt/images/
```

Set read permissions:

```bash
chmod 644 /var/lib/libvirt/images/proxmox-ve_9.2-1.iso
```

Check the file:

```bash
ls -lh /var/lib/libvirt/images/proxmox-ve_9.2-1.iso
```

---

## 6. Creating the QCOW2 Disk

Create a 64 GB system disk:

```bash
qemu-img create \
  -f qcow2 \
  /var/lib/libvirt/images/proxmox-opcp.qcow2 \
  64G
```

Check the image:

```bash
qemu-img info /var/lib/libvirt/images/proxmox-opcp.qcow2
```

Expected output example:

```text
file format: qcow2
virtual size: 64 GiB
```

> The 64 GB disk corresponds to the Proxmox system disk.  
> Future data disks, ZFS pools, or Ceph disks must not be included in this image.

---

## 7. Creating the Build VM

Create a temporary VM with:

- 8 vCPU;
- 16 GB RAM;
- UEFI;
- VirtIO disk;
- VirtIO network adapter.

Command:

```bash
virt-install \
  --name proxmox-image-builder \
  --memory 16384 \
  --vcpus 8 \
  --cpu host \
  --os-variant debian13 \
  --disk path=/var/lib/libvirt/images/proxmox-opcp.qcow2,format=qcow2,bus=virtio \
  --cdrom /var/lib/libvirt/images/proxmox-ve_9.2-1.iso \
  --network network=default,model=virtio \
  --boot uefi
```

If a dedicated network bridge is available on the host, you can also use:

```bash
--network bridge=br0,model=virtio
```

instead of:

```bash
--network network=default,model=virtio
```

---

## 8. Installing Proxmox VE

Install Proxmox normally from the ISO.

For an image intended for Bare Metal deployment, use:

```text
Boot       : UEFI
Partition  : GPT
Filesystem : ext4 / LVM
Disk       : VirtIO disk
```

A simple system disk layout is recommended:

```text
/dev/vda
 |
 +-- EFI
 |
 +-- LVM
      |
      +-- root
      +-- swap
      +-- data
```

It is preferable not to use ZFS for the template system disk.

Physical disks intended for storage can be configured after server deployment.

---

## 9. Image Network Configuration

The image should remain as generic as possible.

During creation in the VM, the network interface may have a name such as:

```text
ens18
```

On the final physical server, interfaces may have different names:

```text
eno1
eno2
ens1f0np0
ens1f1np1
```

The image must therefore not retain a network configuration that depends on the interface name used by the build VM.

Before finalizing the image, keep only a minimal configuration in:

```text
/etc/network/interfaces
```

Example:

```text
auto lo
iface lo inet loopback
```

The final network configuration will be performed after deployment.

It may include:

- management interface;
- `vmbr0` bridge;
- network bonds;
- VLANs;
- storage network;
- cluster network;
- migration network.

---

## 10. Hostname

The template must not use the final server name.

Example:

```bash
hostnamectl set-hostname pve-template
```

After deployment, each server will receive its final name:

```text
pve01
pve02
pve03
```

Example:

```bash
hostnamectl set-hostname pve01
```

Also update:

```text
/etc/hosts
```

Example:

```text
127.0.0.1 localhost
10.10.10.11 pve01.example.local pve01
```

---

## 11. Do Not Create a Cluster in the Image

The server used to generate the image must not be joined to a Proxmox cluster.

Do not configure the following in the template:

- Corosync;
- Proxmox cluster;
- Ceph;
- shared storage;
- remote nodes.

The recommended workflow is:

```text
Proxmox Image
      |
      v
Deploy pve01
Deploy pve02
Deploy pve03
      |
      v
Network configuration
      |
      v
Hostname configuration
      |
      v
Create the Proxmox cluster
```

The cluster must only be created after the servers have been deployed.

---

## 12. Cleaning the Image

Before shutting down the build VM for the last time, clean all instance-specific information.

### 12.1 SSH Keys

Remove the server SSH host keys:

```bash
rm -f /etc/ssh/ssh_host_*
```

They will be regenerated on the next boot.

---

### 12.2 Machine ID

Reset the system identifier:

```bash
truncate -s 0 /etc/machine-id
```

Then:

```bash
rm -f /var/lib/dbus/machine-id
ln -s /etc/machine-id /var/lib/dbus/machine-id
```

---

### 12.3 DHCP Leases

Remove old DHCP leases:

```bash
rm -f /var/lib/dhcp/*
```

---

### 12.4 Logs

Clean the system journal:

```bash
journalctl --rotate
journalctl --vacuum-time=1s
```

Remove old log archives:

```bash
rm -f /var/log/*.gz
```

---

### 12.5 APT Cache

Clean the package cache:

```bash
apt clean
```

---

## 13. Shutting Down the VM

Shut down Proxmox cleanly:

```bash
shutdown -h now
```

Once the VM is stopped, the following file:

```text
/var/lib/libvirt/images/proxmox-opcp.qcow2
```

is the Proxmox system image.

---

## 14. Removing the Temporary VM

The libvirt definition of the build VM is no longer required.

Remove the VM without deleting the QCOW2 disk:

```bash
virsh undefine proxmox-image-builder --nvram
```

Do not use any option that removes the storage volumes.

---

## 15. Checking the QCOW2 Image

Check the image integrity:

```bash
qemu-img check /var/lib/libvirt/images/proxmox-opcp.qcow2
```

Display image information:

```bash
qemu-img info /var/lib/libvirt/images/proxmox-opcp.qcow2
```

---

## 16. Compressing the Image

You can create a compressed copy:

```bash
qemu-img convert \
  -O qcow2 \
  -c \
  /var/lib/libvirt/images/proxmox-opcp.qcow2 \
  /var/lib/libvirt/images/proxmox-opcp-final.qcow2
```

Then check it:

```bash
qemu-img check /var/lib/libvirt/images/proxmox-opcp-final.qcow2
```

---

## 17. Testing the Image

Before importing the image into OPCP, it is recommended to test it without the ISO.

Create a new VM:

```bash
virt-install \
  --name pve-test \
  --memory 8192 \
  --vcpus 4 \
  --disk path=/var/lib/libvirt/images/proxmox-opcp-final.qcow2,format=qcow2 \
  --import \
  --boot uefi \
  --network network=default,model=virtio
```

The system must boot directly through:

```text
UEFI
 |
 v
GRUB
 |
 v
Debian Kernel
 |
 v
Proxmox VE
```

No ISO should be required.

---

## 18. Importing into OpenStack Glance

Import the image into Glance:

```bash
openstack image create "Proxmox-VE-9-Baremetal" \
  --disk-format qcow2 \
  --container-format bare \
  --file /var/lib/libvirt/images/proxmox-opcp-final.qcow2
```

Depending on the OPCP project policy, the image may then be made public or shared.

Check the image:

```bash
openstack image show Proxmox-VE-9-Baremetal
```

The main properties should be:

```text
disk_format      = qcow2
container_format = bare
status           = active
```

The image must be used as a **whole disk image**.

Do not associate it with a `kernel_id` or `ramdisk_id`.

---

## 19. Bare Metal Node UEFI Configuration

The target physical server must be configured to boot in UEFI mode.

In Ironic, the node must also use:

```text
boot_mode:uefi
```

Check with:

```bash
openstack baremetal node show <UUID>
```

The server firmware must also be configured for UEFI boot.

---

## 20. Bare Metal Deployment

The deployment can then be performed through OpenStack.

Example:

```bash
openstack server create \
  --flavor <flavor-baremetal> \
  --image Proxmox-VE-9-Baremetal \
  --network <network-id> \
  pve01
```

The workflow is then:

```text
OpenStack
    |
    v
Ironic
    |
    v
Ironic Python Agent
    |
    v
Download QCOW2 image
    |
    v
Write image to physical disk
    |
    v
Reboot
    |
    v
UEFI
    |
    v
Proxmox VE
```

---

## 21. Post-Deployment Configuration

Once the server has booted, perform the node-specific configuration.

Example:

```text
pve01
 |
 +-- hostname
 +-- management IP address
 +-- DNS
 +-- NTP
 +-- vmbr0
 +-- bonds
 +-- VLANs
 +-- storage
 +-- Proxmox cluster
```

The same image can therefore be used for multiple physical servers.

---

## 22. Recommendations

The Proxmox Golden Image should remain as generic as possible.

### Include in the image

- Proxmox VE;
- Debian;
- EFI partition;
- bootloader;
- standard packages;
- common administration tools.

### Do not include in the image

- final IP address;
- final hostname;
- hardware-dependent NIC configuration;
- bonds;
- final bridges;
- Proxmox cluster;
- Corosync;
- Ceph;
- data ZFS pool;
- server-specific configuration.

---

## 23. Recommended Evolution

To further automate deployment, a first-boot configuration mechanism can be added.

The principle is then:

```text
QCOW2 Golden Image
       |
       v
OPCP Deployment
       |
       v
First Boot
       |
       +-- hostname
       +-- network
       +-- DNS
       +-- NTP
       +-- bridges
       +-- bonds
       +-- storage
       |
       v
Proxmox Server Ready
```

This automation can be implemented using:

- cloud-init;
- a first-boot systemd script;
- Ansible;
- Terraform;
- or an OPCP orchestration mechanism.
