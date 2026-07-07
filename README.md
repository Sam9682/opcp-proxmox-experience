# Proxmox VE Installation on OVH Baremetal OpenStack

Automated Proxmox VE installation on OVH Baremetal OpenStack instances with GPU PCI passthrough support.

## Overview

This system automates the deployment of Proxmox VE on OVH OpenStack Private Cloud (OPCP) baremetal instances, with the specific goal of enabling GPU PCI passthrough for virtual machines. This allows you to run GPU-accelerated workloads (AI/ML inference, rendering, video transcoding, etc.) inside VMs on Proxmox.

### How It Works

1. **Provision a baremetal instance** on OVH OpenStack with a GPU-equipped flavor
2. **Install Proxmox VE** on top of the Debian base system
3. **Configure IOMMU and PCI passthrough** for GPU devices
4. **Create a test VM** with the GPU attached via PCI passthrough
5. **Validate GPU availability** inside the VM

### Key Features

- Automated Proxmox VE 8.x installation on OVH baremetal
- IOMMU/VT-d configuration for PCI passthrough
- GPU device detection and passthrough configuration
- VFIO driver binding for GPU isolation
- Test VM creation with GPU attached
- Network bridge configuration for VM connectivity
- Full cleanup and resource management

## Requirements

### System Requirements

- **Operating Systems** (control node): Ubuntu 22.04, RHEL 8/9, macOS
- **CPU**: Minimum 2 cores (control node)
- **RAM**: Minimum 4 GB (control node)
- **Disk**: Minimum 10 GB free space (control node)
- **Network**: 100 Mbps minimum

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

## Quick Start

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
proxmox-install --config config.yaml
```

3. **Access Proxmox Web UI**:

```
https://<instance-ip>:8006
```

## Architecture

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

## Project Structure

```
proxmox_install_automation/
├── __init__.py              # Package initialization
├── cli.py                   # CLI entry point
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
├── orchestrator/            # Build orchestration
│   └── builder.py           # Main workflow orchestrator
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

## Security Considerations

- Never commit credentials to version control
- Use environment variables or OpenStack clouds.yaml for authentication
- Restrict SSH key permissions to 600
- Limit Proxmox Web UI access via firewall rules
- Use strong passwords for Proxmox root account

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please read CONTRIBUTING.md for guidelines.
