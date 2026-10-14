# Proxmox VE on OVH Baremetal OpenStack (OPCP)

Automated Proxmox VE provisioning, image building, and GPU PCI passthrough for OVH OpenStack Private Cloud (OPCP).

## Overview

This project automates three complementary workflows for running Proxmox VE on OVH OpenStack:

1. **Install** — Provision an OVH baremetal instance, install Proxmox VE on the Debian base system, and configure GPU PCI passthrough so VMs can run GPU-accelerated workloads (AI/ML inference, rendering, video transcoding, etc.).
2. **Build image (remote)** — Build a Proxmox VE qcow2 image using a temporary OpenStack instance: authenticate, create a build instance, download the Proxmox ISO over SSH, convert it to qcow2, snapshot, upload to Glance, and clean up.
3. **Build image (local) and deploy to bare metal** — Build a generic, reusable Proxmox VE qcow2 image locally with KVM/libvirt (`virt-install`), import it into OpenStack Glance, and deploy it to a physical server through OPCP / Ironic. See [shared/LOCAL_BUILD_context.md](shared/LOCAL_BUILD_context.md) for the full documented procedure.

The local build path is **additive**: it lives in the `local_build` package alongside the existing remote `image_builder` flow, which is preserved unchanged.

### Key Features

**Install (GPU passthrough)**
- Automated Proxmox VE 8.x installation on OVH baremetal
- IOMMU/VT-d configuration for PCI passthrough
- GPU device detection, VFIO driver binding, and passthrough configuration
- Test VM creation with the GPU attached and in-VM GPU validation
- Network bridge configuration and full cleanup / resource management

**Remote image build**
- Builds a Proxmox qcow2 image on a temporary OpenStack instance
- ISO download, qcow2 conversion, snapshot, and Glance upload
- Automatic cleanup of transient build resources

**Local image build + OPCP/Ironic deploy**
- Local Debian/Ubuntu build host using QEMU/KVM, libvirt, and `virt-install`
- Build-host prerequisite checks (packages, KVM acceleration, UEFI/OVMF)
- 64 GB qcow2 system disk, UEFI build VM (8 vCPU / 16 GB / VirtIO)
- Documented interactive Proxmox install (GPT, ext4/LVM, no ZFS for the template)
- Image generic-ization (SSH host keys, machine-id, DHCP leases, logs, hostname, loopback-only network, no cluster/Corosync/Ceph)
- Finalization (`virsh undefine --nvram`, `qemu-img check/info`, compression) and an ISO-less boot test
- Whole-disk Glance import and Ironic bare-metal deploy (`boot_mode: uefi`)
- First-boot scaffolding (cloud-init / systemd / Ansible) for per-node configuration

## Requirements

### System Requirements

- **Operating Systems** (control node): Ubuntu 22.04, RHEL 8/9, macOS
- **CPU**: Minimum 2 cores (control node)
- **RAM**: Minimum 4 GB (control node)
- **Disk**: Minimum 10 GB free space (control node)
- **Network**: 100 Mbps minimum

> **Local image build host**: the `local-build` workflow additionally requires a Debian/Ubuntu host with QEMU, libvirt, `virt-install`, `qemu-img`, UEFI/OVMF firmware, and (preferably) KVM hardware acceleration. Install with:
> ```bash
> apt install -y qemu-utils qemu-system-x86 libvirt-daemon-system libvirt-clients virtinst ovmf
> ```

### OVH OpenStack Requirements

- OVH Public Cloud or Private Cloud account with baremetal instances
- Baremetal flavor with GPU (e.g., `gpu-b3-*`, `t2-*` with NVIDIA GPUs)
- Debian 12 base image available
- OpenStack application credentials
- Security group allowing SSH (port 22) and Proxmox Web UI (port 8006)

### Software Requirements

- **Python**: 3.8 or higher
- **OpenStack SDK**: 1.0.0 or higher
- **SSH**: OpenSSH client
- **Optional**: Ansible 2.14+ (for playbook-based deployment)

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd opcp-proxmox-install

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

This installs the `proxmox-install` command-line entry point.

## CLI Commands

The `proxmox-install` CLI exposes three capabilities:

| Command | Purpose |
|---------|---------|
| `proxmox-install install -c config.yaml` | Provision a baremetal instance and install Proxmox VE with GPU passthrough |
| `proxmox-install build-image -c config.yaml` | Build a Proxmox qcow2 image on a temporary OpenStack instance and upload to Glance (remote flow) |
| `proxmox-install local-build check -c config.yaml` | Verify local build-host prerequisites |
| `proxmox-install local-build run -c config.yaml` | Build the Proxmox qcow2 image locally with KVM/libvirt (through boot test) |
| `proxmox-install local-build deploy -c config.yaml` | Import the image into Glance, deploy to an Ironic bare-metal node, and scaffold first-boot config |

Add `--dry-run` to `build-image` or `local-build run` to validate configuration without executing.

## Quick Start (install + GPU passthrough)

1. **Configure OpenStack credentials and Proxmox settings**:

```yaml
# config.yaml
openstack:
  auth_url: "https://auth.cloud.ovh.net/v3"
  region: "GRA7"
  auth_type: "v3applicationcredential"
  application_credential_id: "your_credential_id"
  application_credential_secret: "your_credential_secret"
  project_name: "your-project"

instance:
  base_image_name: "Debian 12"
  flavor_name: "b3-8"   # Use a baremetal GPU flavor for passthrough
  ssh_username: "debian"
  ssh_key_name: "your-keypair"
  ssh_key_path: "~/.ssh/id_rsa"

proxmox:
  version: "8.2"
  storage_type: "local-lvm"
  network_bridge: "vmbr0"

gpu_passthrough:
  enabled: true
  auto_detect: true
  # Optionally specify PCI device IDs manually:
  # devices:
  #   - "0000:41:00.0"  # GPU
  #   - "0000:41:00.1"  # GPU Audio

test_vm:
  enabled: true
  name: "gpu-test-vm"
  memory_mb: 8192
  cores: 4
  disk_gb: 32
  os_iso: "local:iso/ubuntu-22.04-live-server-amd64.iso"
```

2. **Run the installation**:

```bash
proxmox-install install --config config.yaml
```

3. **Access Proxmox Web UI**:

```
https://<instance-ip>:8006
```

## Quick Start (local image build + OPCP deploy)

```bash
# 1. Verify the local build host has the required tooling
proxmox-install local-build check --config local-build.yaml

# 2. Build the generic Proxmox qcow2 image locally (pauses for the
#    documented interactive install, then cleans, finalizes, and boot-tests)
proxmox-install local-build run --config local-build.yaml

# 3. Import into Glance, deploy to an Ironic bare-metal node, and
#    generate first-boot scaffolding
proxmox-install local-build deploy --config local-build.yaml
```

The full step-by-step procedure (prerequisites, ISO staging, disk/VM creation, interactive install, cleaning, finalization, boot test, Glance import, Ironic deploy, and first-boot scaffolding) is documented in [shared/LOCAL_BUILD_context.md](shared/LOCAL_BUILD_context.md).

## Architecture

### Install + GPU passthrough

```
┌─────────────────────────────────────────────────┐
│                 OVH OpenStack                    │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │         Baremetal Instance (GPU)          │  │
│  │                                           │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │          Proxmox VE 8.x             │  │  │
│  │  │                                     │  │  │
│  │  │  ┌──────────┐    ┌──────────────┐  │  │  │
│  │  │  │  VM #1   │    │   VM #2      │  │  │  │
│  │  │  │ (no GPU) │    │ (GPU pass-   │  │  │  │
│  │  │  │          │    │  through)    │  │  │  │
│  │  │  └──────────┘    └──────┬───────┘  │  │  │
│  │  │                         │           │  │  │
│  │  │  ┌──────────────────────┴────────┐  │  │  │
│  │  │  │     NVIDIA GPU (VFIO)         │  │  │  │
│  │  │  └──────────────────────────────-┘  │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### Local image build → OPCP / Ironic

```
Proxmox VE ISO
      │
      ▼
Temporary KVM/QEMU build VM (UEFI, 8 vCPU, 16 GB, 64 GB qcow2)
      │  interactive install + generic-ization
      ▼
proxmox-opcp-final.qcow2  (GPT, EFI, Debian, Proxmox VE)
      │  Glance import (whole-disk image)
      ▼
OPCP / OpenStack / Ironic  (boot_mode: uefi)
      │
      ▼
Bare-metal server  →  first-boot config (hostname, network, cluster, storage)
```

## Project Structure

```
proxmox_install_automation/
├── __init__.py              # Package initialization
├── cli.py                   # CLI entry point (install, build-image, local-build)
├── models.py                # Core data models
├── interfaces.py            # Abstract interfaces
├── exceptions.py            # Custom exceptions
├── config_loader.py         # Configuration loading
├── logging_config.py        # Logging configuration
├── auth/                    # OpenStack authentication
│   └── manager.py
├── provisioner/             # Baremetal instance provisioning
│   ├── instance.py          # Instance lifecycle
│   └── ssh.py               # SSH connection management
├── proxmox/                 # Proxmox VE installation
│   ├── installer.py         # Proxmox package installation
│   ├── network.py           # Network bridge configuration
│   └── storage.py           # Storage configuration
├── gpu/                     # GPU passthrough configuration
│   ├── detector.py          # GPU device detection
│   ├── iommu.py             # IOMMU/VT-d configuration
│   └── vfio.py              # VFIO driver binding
├── vm/                      # Test VM management
│   ├── creator.py           # VM creation with GPU
│   └── validator.py         # GPU validation in VM
├── image_builder/           # Remote qcow2 image build (OpenStack instance)
│   ├── builder.py           # Remote build orchestrator
│   ├── instance.py          # Build instance lifecycle
│   ├── iso_downloader.py    # ISO download over SSH
│   ├── iso_converter.py     # ISO → qcow2 conversion
│   ├── snapshot.py          # Server snapshot
│   ├── glance_uploader.py   # Glance upload
│   └── cleanup.py           # Build resource cleanup
├── local_build/             # Local KVM/libvirt build + OPCP/Ironic deploy
│   ├── builder.py           # LocalImageBuilder orchestrator (build + deploy)
│   ├── command_runner.py    # Mockable local subprocess wrapper
│   ├── prerequisites.py     # Build-host prerequisite checks
│   ├── iso_stager.py        # ISO staging into libvirt images dir
│   ├── system_disk.py       # 64 GB qcow2 system disk creation
│   ├── build_vm.py          # virt-install build VM creation
│   ├── image_cleaner.py     # Image generic-ization (libguestfs)
│   ├── image_finalizer.py   # Undefine, validate, compress final image
│   ├── boot_tester.py       # ISO-less import boot test
│   ├── glance_importer.py   # Whole-disk Glance import
│   ├── ironic_deployer.py   # Ironic bare-metal deploy (boot_mode: uefi)
│   ├── firstboot_scaffolder.py # cloud-init/systemd/Ansible scaffolding
│   ├── config_loader.py     # YAML config loading
│   └── config_validator.py  # Config validation
├── orchestrator/            # Install workflow orchestration
│   └── builder.py           # Main install orchestrator
└── cleanup/                 # Resource cleanup
    └── manager.py
```

## GPU PCI Passthrough Details

### How GPU Passthrough Works

1. **IOMMU Enablement**: The BIOS/UEFI must have VT-d (Intel) or AMD-Vi enabled. We configure the kernel boot parameters (`intel_iommu=on` or `amd_iommu=on`).

2. **VFIO Driver Binding**: The GPU is unbound from its native driver (e.g., `nouveau`, `nvidia`) and bound to the `vfio-pci` driver, which provides safe userspace access.

3. **IOMMU Groups**: PCI devices are grouped by the hardware topology. All devices in the same IOMMU group must be passed through together.

4. **VM Configuration**: The GPU PCI device is added to the VM configuration, making it appear as a native device inside the VM.

### Supported GPU Types

| GPU | OVH Flavor | PCI IDs | Notes |
|-----|-----------|---------|-------|
| NVIDIA T4 | t2-45 | 10de:1eb8 | Inference, AI workloads |
| NVIDIA V100 | gpu-b3-* | 10de:1db4 | Training, HPC |
| NVIDIA A100 | * | 10de:20b0 | Large model training |
| NVIDIA L4 | * | 10de:27b8 | Inference, video |

### Verifying Passthrough

After installation, verify GPU passthrough is working:

```bash
# On the Proxmox host - check IOMMU groups
find /sys/kernel/iommu_groups/ -type l | sort -V

# Check VFIO binding
lspci -nnk | grep -A3 "NVIDIA"

# Inside the VM - verify GPU is visible
lspci | grep -i nvidia
nvidia-smi  # If NVIDIA drivers are installed
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=proxmox_install_automation

# Run specific test module
pytest tests/test_gpu_passthrough.py

# Run the local-build suite
pytest tests/test_local_build
```

### Code Quality

```bash
# Format code
black proxmox_install_automation/
isort proxmox_install_automation/

# Lint code
pylint proxmox_install_automation/
flake8 proxmox_install_automation/

# Type checking
mypy proxmox_install_automation/
```

## Troubleshooting

### IOMMU Not Available

**Problem**: `DMAR: IOMMU not detected` in kernel logs

**Solutions**:
1. Verify the baremetal instance has VT-d/AMD-Vi support
2. Check that the correct kernel parameters are set in GRUB
3. Reboot after applying kernel parameters
4. Ensure the OVH flavor supports hardware virtualization extensions

### GPU Not Detected

**Problem**: No NVIDIA GPU found via `lspci`

**Solutions**:
1. Verify you're using a GPU-enabled OVH flavor
2. Check `lspci -nn | grep -i "3d\|vga\|display"` for any GPU
3. Contact OVH support if GPU is not visible on baremetal

### VFIO Binding Failure

**Problem**: Cannot bind GPU to vfio-pci driver

**Solutions**:
1. Ensure the GPU is not in use by another driver
2. Blacklist the native GPU driver (nouveau, nvidia)
3. Check that vfio-pci module is loaded: `lsmod | grep vfio`
4. Verify IOMMU groups: all devices in the group must be passed through

### VM Cannot Access GPU

**Problem**: GPU not visible inside the VM

**Solutions**:
1. Verify the VM configuration includes the correct PCI device
2. Check that the host has properly isolated the GPU
3. Ensure the VM machine type supports PCI passthrough (q35)
4. Install GPU drivers inside the VM

### Local build prerequisites missing

**Problem**: `local-build check` reports missing packages, KVM, or OVMF

**Solutions**:
1. Install the required packages: `apt install -y qemu-utils qemu-system-x86 libvirt-daemon-system libvirt-clients virtinst ovmf`
2. Confirm KVM acceleration is available (`/dev/kvm` exists)
3. Confirm the OVMF firmware descriptor is present (e.g. `/usr/share/OVMF/OVMF_CODE.fd`)
4. Run the build host on Debian or Ubuntu

## Security Considerations

- Never commit credentials to version control
- Use environment variables or OpenStack clouds.yaml for authentication
- Restrict SSH key permissions to 600
- Limit Proxmox Web UI access via firewall rules
- Use strong passwords for Proxmox root account
- Keep server-specific data (final IP, hostname, cluster/Corosync, Ceph, data ZFS pools) out of the generic image — apply it at first boot

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please read CONTRIBUTING.md for guidelines.