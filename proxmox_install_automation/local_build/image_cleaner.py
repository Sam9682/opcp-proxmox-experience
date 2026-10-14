"""
Post-install guest-image cleaner (generic-ization) for the local build path.

The cleaner builds a declarative :class:`CleaningPlan` — a pure data structure
listing the ordered operations required to turn a freshly installed Proxmox VE
disk into a generic, reusable template image (Req 7). Modeling the plan as data
makes the generic-ization behavior property-testable without a real guest.

``apply`` executes the plan against the installed guest disk via libguestfs
(``virt-customize``/``guestfish``) in a single runner invocation, isolating all
I/O behind the injected :class:`LocalCommandRunner` so the pure plan logic can be
tested independently.

Requirements covered:
  7.1  loopback-only /etc/network/interfaces
  7.2  hostname -> pve-template
  7.3  remove SSH host keys
  7.4  reset machine-id + recreate dbus machine-id symlink
  7.5  remove DHCP lease files
  7.6  rotate/vacuum systemd journal + remove archived logs
  7.7  apt clean
  7.8  remove any cluster/Corosync/Ceph/shared-storage configuration
  13.2 the cleaned image excludes server-specific/cluster/shared-storage state
"""

from typing import List

from ..logging_config import get_logger
from .command_runner import LocalCommandRunner
from .exceptions import ImageCleanError
from .models import CleaningOp, CleaningPlan

logger = get_logger("local_build.image_cleaner")

# Generic loopback-only /etc/network/interfaces (Req 7.1). Interface naming,
# bridges, bonds, VLANs, and the storage network are intentionally omitted so
# the image carries no host-specific networking.
LOOPBACK_INTERFACES = "auto lo\niface lo inet loopback\n"

# The generic template hostname (Req 7.2).
TEMPLATE_HOSTNAME = "pve-template"

# Cluster / Corosync / Ceph / shared-storage paths that must never be retained
# in a generic image (Req 7.8, 13.2). Removed unconditionally; absence is fine.
CLUSTER_CONFIG_PATHS = (
    "/etc/pve/corosync.conf",
    "/etc/corosync",
    "/var/lib/corosync",
    "/etc/pve/ceph.conf",
    "/etc/ceph",
    "/var/lib/ceph",
    "/etc/pve/storage.cfg",
    "/etc/pve/priv/known_hosts",
)


class ImageCleaner:
    """Builds and applies the generic-ization cleaning plan for a guest disk."""

    def __init__(self, runner: LocalCommandRunner) -> None:
        """
        Args:
            runner: Injected local command runner used to invoke libguestfs.
        """
        self.runner = runner

    def build_plan(self) -> CleaningPlan:
        """
        Produce the ordered cleaning plan (Req 7).

        Pure function: returns a :class:`CleaningPlan` data structure and performs
        no I/O, so the generic-ization behavior is deterministic and
        property-testable without a real guest.

        The plan NEVER retains cluster, Corosync, Ceph, or shared-storage
        configuration and removes any present (Req 7.8, 13.2).

        Returns:
            An ordered :class:`CleaningPlan`.
        """
        operations: List[CleaningOp] = [
            # 7.1 — generic loopback-only /etc/network/interfaces
            CleaningOp(
                action="write-file",
                params={
                    "path": "/etc/network/interfaces",
                    "content": LOOPBACK_INTERFACES,
                },
                description="Write loopback-only /etc/network/interfaces (Req 7.1)",
            ),
            # 7.2 — set hostname to pve-template
            CleaningOp(
                action="set-hostname",
                params={"hostname": TEMPLATE_HOSTNAME},
                description="Set hostname to pve-template (Req 7.2)",
            ),
            # 7.3 — remove SSH host keys
            CleaningOp(
                action="delete",
                params={"path": "/etc/ssh/ssh_host_*"},
                description="Remove SSH host keys (Req 7.3)",
            ),
            # 7.4 — reset machine-id, remove dbus machine-id, recreate symlink
            CleaningOp(
                action="run-command",
                params={"command": "truncate -s 0 /etc/machine-id"},
                description="Truncate /etc/machine-id (Req 7.4)",
            ),
            CleaningOp(
                action="delete",
                params={"path": "/var/lib/dbus/machine-id"},
                description="Remove /var/lib/dbus/machine-id (Req 7.4)",
            ),
            CleaningOp(
                action="run-command",
                params={
                    "command": "ln -sf /etc/machine-id /var/lib/dbus/machine-id",
                },
                description="Recreate dbus machine-id symlink (Req 7.4)",
            ),
            # 7.5 — remove DHCP lease files
            CleaningOp(
                action="delete",
                params={"path": "/var/lib/dhcp/*"},
                description="Remove DHCP lease files (Req 7.5)",
            ),
            # 7.6 — rotate/vacuum journal, remove archived logs
            CleaningOp(
                action="run-command",
                params={"command": "journalctl --rotate"},
                description="Rotate systemd journal (Req 7.6)",
            ),
            CleaningOp(
                action="run-command",
                params={"command": "journalctl --vacuum-time=1s"},
                description="Vacuum systemd journal (Req 7.6)",
            ),
            CleaningOp(
                action="delete",
                params={"path": "/var/log/*.gz"},
                description="Remove archived log files (Req 7.6)",
            ),
            # 7.7 — apt clean
            CleaningOp(
                action="run-command",
                params={"command": "apt clean"},
                description="Run apt clean (Req 7.7)",
            ),
        ]

        # 7.8 / 13.2 — remove any cluster/Corosync/Ceph/shared-storage config.
        # Appended last so the plan NEVER retains these artifacts.
        for path in CLUSTER_CONFIG_PATHS:
            operations.append(
                CleaningOp(
                    action="delete",
                    params={"path": path},
                    description=(
                        "Remove cluster/Corosync/Ceph/shared-storage config "
                        f"{path} (Req 7.8, 13.2)"
                    ),
                )
            )

        return CleaningPlan(operations=operations)

    def apply(self, disk_path: str, plan: CleaningPlan) -> None:
        """
        Apply a cleaning plan to the guest disk via libguestfs.

        Translates the declarative plan into a single ``virt-customize`` argv and
        runs it through the injected runner (one invocation). Raises
        :class:`ImageCleanError` on any failure.

        Args:
            disk_path: Path to the installed guest qcow2 disk to clean.
            plan: The :class:`CleaningPlan` produced by :meth:`build_plan`.

        Raises:
            ImageCleanError: If the libguestfs invocation fails.
        """
        argv = self._build_virt_customize_argv(disk_path, plan)

        logger.info(
            "Applying cleaning plan to %s via libguestfs (%d operations)",
            disk_path,
            len(plan.operations),
        )

        try:
            self.runner.run(argv)
        except Exception as exc:  # LocalCommandError and any unexpected failure
            logger.error("Image cleaning failed for %s: %s", disk_path, exc)
            raise ImageCleanError(
                f"Failed to clean guest image {disk_path}: {exc}"
            ) from exc

    def _build_virt_customize_argv(
        self, disk_path: str, plan: CleaningPlan
    ) -> List[str]:
        """
        Translate the plan into a single ``virt-customize`` argv (pure helper).

        Each :class:`CleaningOp` maps to a ``virt-customize`` flag pair:
          write-file   -> --write PATH:CONTENT
          set-hostname -> --hostname NAME
          delete       -> --delete PATH
          run-command  -> --run-command CMD
        """
        argv: List[str] = ["virt-customize", "-a", disk_path]

        for op in plan.operations:
            if op.action == "write-file":
                argv += [
                    "--write",
                    f"{op.params['path']}:{op.params['content']}",
                ]
            elif op.action == "set-hostname":
                argv += ["--hostname", op.params["hostname"]]
            elif op.action == "delete":
                argv += ["--delete", op.params["path"]]
            elif op.action == "run-command":
                argv += ["--run-command", op.params["command"]]
            else:  # pragma: no cover - guarded against future op kinds
                raise ImageCleanError(
                    f"Unknown cleaning operation action: {op.action!r}"
                )

        return argv


__all__ = ["ImageCleaner"]
