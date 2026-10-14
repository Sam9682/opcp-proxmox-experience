"""
Post-deployment first-boot scaffolding generator for the local build path.

After the generic image is deployed to a bare-metal node, node-specific
configuration must be applied on first boot rather than baked into the generic
image (Req 12). :class:`FirstBootScaffolder` generates first-boot automation
artifacts in one of three formats — cloud-init, systemd first-boot, or
Ansible — selected via ``DeployConfig.firstboot_format``.

Every generated artifact contains a clearly labeled scaffolding section for
each entry in :data:`REQUIRED_TOPICS`, covering hostname, IP address, DNS, NTP,
network interfaces, the vmbr0 bridge, bonds, VLANs, the storage network,
cluster/Corosync, and ZFS/Ceph (Req 12.1, 12.2, 12.3). Sections are TODO
scaffolding the operator fills in per node; nothing host-specific is assumed.

Requirements covered:
  12.1  generate artifacts via cloud-init, systemd first-boot, or Ansible
  12.2  scaffolding for hostname, IP, DNS, NTP, network interfaces, vmbr0
        bridge, bonds, VLANs, and the storage network
  12.3  scaffolding for cluster/Corosync and ZFS/Ceph configuration
"""

import os
from typing import Dict, List, Tuple

from ..logging_config import get_logger
from .exceptions import FirstBootScaffoldError
from .models import DeployConfig

logger = get_logger("local_build.firstboot_scaffolder")

# The configuration topics every generated artifact must scaffold (Req 12.2,
# 12.3). Ordered so output is deterministic and property-testable.
REQUIRED_TOPICS: Tuple[str, ...] = (
    "hostname",
    "ip_address",
    "dns",
    "ntp",
    "network_interfaces",
    "vmbr0_bridge",
    "bonds",
    "vlans",
    "storage_network",
    "cluster_corosync",
    "zfs_ceph",
)

# Human-readable labels for each required topic, used in the scaffolding
# section headings so operators know what to fill in.
_TOPIC_LABELS: Dict[str, str] = {
    "hostname": "Hostname",
    "ip_address": "IP address",
    "dns": "DNS resolvers",
    "ntp": "NTP servers",
    "network_interfaces": "Network interfaces",
    "vmbr0_bridge": "vmbr0 bridge",
    "bonds": "Bonds",
    "vlans": "VLANs",
    "storage_network": "Storage network",
    "cluster_corosync": "Cluster / Corosync",
    "zfs_ceph": "ZFS / Ceph",
}

# Supported first-boot artifact formats (Req 12.1), mapped to output filenames.
_FORMAT_FILENAMES: Dict[str, str] = {
    "cloud-init": "firstboot-cloud-init.yaml",
    "systemd": "firstboot.sh",
    "ansible": "firstboot-playbook.yaml",
}


class FirstBootScaffolder:
    """Generates post-deployment first-boot configuration scaffolding."""

    def generate(self, config: DeployConfig) -> List[str]:
        """
        Generate first-boot scaffolding artifacts (Req 12).

        Renders a single artifact in the format named by
        ``config.firstboot_format`` (cloud-init, systemd first-boot, or
        Ansible — Req 12.1) into ``config.firstboot_output_dir``. The artifact
        contains a labeled scaffolding section for every entry in
        :data:`REQUIRED_TOPICS` (Req 12.2, 12.3).

        Args:
            config: Deploy configuration selecting the format and output dir.

        Returns:
            The list of written artifact paths.

        Raises:
            FirstBootScaffoldError: If the format is unsupported or writing the
                artifact fails for any reason.
        """
        fmt = config.firstboot_format
        if fmt not in _FORMAT_FILENAMES:
            raise FirstBootScaffoldError(
                f"Unsupported first-boot format {fmt!r}; expected one of "
                f"{', '.join(sorted(_FORMAT_FILENAMES))}"
            )

        content = self._render(fmt)
        filename = _FORMAT_FILENAMES[fmt]
        output_dir = config.firstboot_output_dir
        artifact_path = os.path.join(output_dir, filename)

        logger.info(
            "Generating %s first-boot scaffolding at %s", fmt, artifact_path
        )

        try:
            os.makedirs(output_dir, exist_ok=True)
            with open(artifact_path, "w", encoding="utf-8") as handle:
                handle.write(content)
        except OSError as exc:
            logger.error(
                "Failed to write first-boot scaffolding to %s: %s",
                artifact_path,
                exc,
            )
            raise FirstBootScaffoldError(
                f"Failed to write first-boot scaffolding to {artifact_path}: {exc}"
            ) from exc

        return [artifact_path]

    def _render(self, fmt: str) -> str:
        """Render the artifact body for the given format (pure helper)."""
        if fmt == "cloud-init":
            return self._render_cloud_init()
        if fmt == "systemd":
            return self._render_systemd()
        if fmt == "ansible":
            return self._render_ansible()
        # Unreachable: generate() validates fmt before calling _render.
        raise FirstBootScaffoldError(  # pragma: no cover
            f"Unsupported first-boot format {fmt!r}"
        )

    def _render_cloud_init(self) -> str:
        """Render a cloud-init first-boot artifact (Req 12.1)."""
        lines: List[str] = [
            "#cloud-config",
            "# Proxmox VE post-deployment first-boot scaffolding.",
            "# Fill in each node-specific section below before first boot.",
            "runcmd:",
        ]
        for topic in REQUIRED_TOPICS:
            label = _TOPIC_LABELS[topic]
            lines.append(f"  # --- {label} ({topic}) ---")
            lines.append(f"  # TODO: configure {label} for this node")
        return "\n".join(lines) + "\n"

    def _render_systemd(self) -> str:
        """Render a systemd first-boot shell artifact (Req 12.1)."""
        lines: List[str] = [
            "#!/bin/sh",
            "# Proxmox VE post-deployment first-boot scaffolding.",
            "# Invoked once on first boot (e.g. via a systemd oneshot unit).",
            "set -eu",
        ]
        for topic in REQUIRED_TOPICS:
            label = _TOPIC_LABELS[topic]
            lines.append("")
            lines.append(f"# --- {label} ({topic}) ---")
            lines.append(f"# TODO: configure {label} for this node")
        return "\n".join(lines) + "\n"

    def _render_ansible(self) -> str:
        """Render an Ansible first-boot playbook artifact (Req 12.1)."""
        lines: List[str] = [
            "---",
            "# Proxmox VE post-deployment first-boot scaffolding.",
            "- name: Proxmox VE first-boot configuration",
            "  hosts: all",
            "  become: true",
            "  tasks:",
        ]
        for topic in REQUIRED_TOPICS:
            label = _TOPIC_LABELS[topic]
            lines.append(f"    # --- {label} ({topic}) ---")
            lines.append(f"    # TODO: configure {label} for this node")
        return "\n".join(lines) + "\n"


__all__ = ["FirstBootScaffolder", "REQUIRED_TOPICS"]
