"""
GPU device detection on the host system.
"""

import re
from typing import List

from ..exceptions import GPUDetectionError
from ..logging_config import get_logger
from ..models import GPUDevice
from ..provisioner.ssh import SSHConnection

logger = get_logger("gpu.detector")

# Known GPU vendor IDs
NVIDIA_VENDOR_ID = "10de"
AMD_VENDOR_ID = "1002"


class GPUDetector:
    """Detects GPU PCI devices on the system."""

    def detect(self, ssh: SSHConnection) -> List[GPUDevice]:
        """
        Detect all GPU devices (NVIDIA and AMD).

        Args:
            ssh: Active SSH connection.

        Returns:
            List of detected GPUDevice objects.

        Raises:
            GPUDetectionError: If detection fails.
        """
        logger.info("Detecting GPU devices...")

        try:
            # Use lspci to find VGA/3D controllers
            result = ssh.execute_sudo(
                "lspci -nn | grep -iE '(vga|3d|display)'"
            )

            if result.exit_code != 0 and not result.stdout.strip():
                logger.warning("No GPU devices found via lspci")
                return []

            devices = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                device = self._parse_lspci_line(line)
                if device:
                    devices.append(device)

            # Also detect associated audio devices (NVIDIA HDMI audio)
            audio_devices = self._detect_gpu_audio(ssh, devices)
            devices.extend(audio_devices)

            # Get IOMMU group information
            self._populate_iommu_groups(ssh, devices)

            logger.info("Found %d GPU-related devices", len(devices))
            for dev in devices:
                logger.info(
                    "  %s: %s [%s:%s] (IOMMU group: %s)",
                    dev.pci_id,
                    dev.description,
                    dev.vendor_id,
                    dev.device_id,
                    dev.iommu_group,
                )

            return devices

        except GPUDetectionError:
            raise
        except Exception as e:
            raise GPUDetectionError(f"GPU detection failed: {e}") from e

    def _parse_lspci_line(self, line: str) -> GPUDevice | None:
        """Parse a single lspci output line into a GPUDevice."""
        # Example: "41:00.0 3D controller [0302]: NVIDIA Corporation Tesla T4 [10de:1eb8] (rev a1)"
        match = re.match(
            r"(\S+)\s+.+?\[([0-9a-f]{4}):([0-9a-f]{4})\]",
            line,
        )
        if not match:
            return None

        pci_slot = match.group(1)
        vendor_id = match.group(2)
        device_id = match.group(3)

        # Only track NVIDIA and AMD GPUs
        if vendor_id not in (NVIDIA_VENDOR_ID, AMD_VENDOR_ID):
            return None

        # Extract description - try to get the part after the colon (device name)
        # Pattern: "41:00.0 3D controller [0302]: NVIDIA Corporation Tesla T4 [10de:1eb8]"
        desc_match = re.search(r"\]:\s*(.+?)\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]", line)
        if desc_match:
            description = desc_match.group(1).strip()
        else:
            # Fallback: get the class description
            desc_match = re.match(r"\S+\s+(.+?)\s*\[", line)
            description = desc_match.group(1) if desc_match else "Unknown GPU"

        # Normalize PCI ID to full format
        pci_id = f"0000:{pci_slot}" if ":" in pci_slot and len(pci_slot) < 12 else pci_slot

        return GPUDevice(
            pci_id=pci_id,
            vendor_id=vendor_id,
            device_id=device_id,
            description=description,
        )

    def _detect_gpu_audio(
        self, ssh: SSHConnection, gpu_devices: List[GPUDevice]
    ) -> List[GPUDevice]:
        """Detect associated audio controllers for GPU devices."""
        audio_devices = []

        for gpu in gpu_devices:
            # Check for audio device at same slot but function 1
            base_slot = gpu.pci_id.rsplit(".", 1)[0]
            audio_slot = f"{base_slot}.1"

            result = ssh.execute_sudo(f"lspci -nn -s {audio_slot}")
            if result.exit_code == 0 and result.stdout.strip():
                line = result.stdout.strip()
                if "audio" in line.lower() or "Audio" in line:
                    device = self._parse_lspci_line(line)
                    if device:
                        device.description = f"{gpu.description} Audio"
                        audio_devices.append(device)

        return audio_devices

    def _populate_iommu_groups(
        self, ssh: SSHConnection, devices: List[GPUDevice]
    ) -> None:
        """Populate IOMMU group information for devices."""
        result = ssh.execute_sudo(
            "find /sys/kernel/iommu_groups/ -type l 2>/dev/null | sort -V"
        )
        if result.exit_code != 0:
            logger.warning("Could not read IOMMU groups")
            return

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            # Line format: /sys/kernel/iommu_groups/X/devices/0000:XX:XX.X
            parts = line.split("/")
            if len(parts) >= 6:
                try:
                    group_id = int(parts[4])
                    pci_addr = parts[-1]
                    for device in devices:
                        if device.pci_id == pci_addr or device.pci_id.endswith(pci_addr):
                            device.iommu_group = group_id
                except (ValueError, IndexError):
                    continue

    def get_current_driver(self, ssh: SSHConnection, device: GPUDevice) -> str | None:
        """Get the current kernel driver for a device."""
        result = ssh.execute_sudo(
            f"lspci -ks {device.pci_id} | grep 'Kernel driver in use:'"
        )
        if result.exit_code == 0 and result.stdout.strip():
            match = re.search(r"Kernel driver in use:\s*(\S+)", result.stdout)
            if match:
                return match.group(1)
        return None
