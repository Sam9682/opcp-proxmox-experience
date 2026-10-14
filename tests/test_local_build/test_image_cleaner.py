"""
Tests for the ImageCleaner component (local_build, Requirement 7 / 13.2).

Covers:
- Task 8.2 — Property 6: Cleaning produces a generic image.
  Feature: proxmox-qcow2-opcp-deployment, Property 6
  Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 13.2
  ImageCleaner.build_plan() is pure and takes no inputs, so the "installed-image
  state" is modeled by interpreting the plan's declarative CleaningOps. The
  property is driven over a hypothesis-generated set of host-specific / cluster
  artifact paths (random /etc/pve/*, /etc/ceph/*, corosync paths, ...) to reach
  >=100 iterations, and for every generated artifact belonging to the
  cluster/Corosync/Ceph/shared-storage family we assert the plan contains a
  delete op covering it. The plan's generic-ization invariants (loopback-only
  interfaces, pve-template hostname, SSH host-key removal, machine-id reset +
  dbus symlink, DHCP lease removal, journal rotate/vacuum + archived-log removal,
  apt clean) are asserted to hold regardless of the generated input, and no op
  is allowed to retain any cluster/shared-storage artifact. build_plan is the
  source of truth throughout.

- Task 8.3 — Unit tests for ImageCleaner.apply.
  Validates: Requirements 7.1, 7.8
  The injected LocalCommandRunner is mocked; apply must issue exactly ONE runner
  call (a single `virt-customize -a <disk>` invocation translating the plan),
  and a runner failure must raise ImageCleanError.
"""

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, strategies as st

from proxmox_install_automation.local_build.exceptions import (
    ImageCleanError,
    LocalCommandError,
)
from proxmox_install_automation.local_build.image_cleaner import ImageCleaner
from proxmox_install_automation.local_build.models import CleaningOp, CleaningPlan


# ---------------------------------------------------------------------------
# Helpers for interpreting a declarative CleaningPlan (build_plan is the
# source of truth; these only read the plan it produces).
# ---------------------------------------------------------------------------

def _cleaner() -> ImageCleaner:
    """An ImageCleaner with a mocked runner (build_plan is pure, so the runner
    is never touched by plan-only assertions)."""
    return ImageCleaner(runner=MagicMock())


def _delete_targets(plan: CleaningPlan):
    """All paths targeted by a 'delete' op in the plan."""
    return [op.params["path"] for op in plan.operations if op.action == "delete"]


def _run_commands(plan: CleaningPlan):
    """All shell commands issued by 'run-command' ops in the plan."""
    return [
        op.params["command"]
        for op in plan.operations
        if op.action == "run-command"
    ]


def _write_files(plan: CleaningPlan):
    """Mapping of path -> content for every 'write-file' op in the plan."""
    return {
        op.params["path"]: op.params["content"]
        for op in plan.operations
        if op.action == "write-file"
    }


def _hostnames(plan: CleaningPlan):
    """All hostnames set by 'set-hostname' ops in the plan."""
    return [
        op.params["hostname"]
        for op in plan.operations
        if op.action == "set-hostname"
    ]


# The cluster / Corosync / Ceph / shared-storage artifact family. A generated
# artifact "belongs" to this family if it lives under one of these roots. The
# plan must guarantee the family root (or an equal/broader path) is deleted,
# which removes every artifact beneath it.
_CLUSTER_FAMILY_ROOTS = (
    "/etc/pve/corosync.conf",
    "/etc/corosync",
    "/var/lib/corosync",
    "/etc/pve/ceph.conf",
    "/etc/ceph",
    "/var/lib/ceph",
    "/etc/pve/storage.cfg",
    "/etc/pve/priv/known_hosts",
)


def _covered_by_plan(artifact: str, delete_targets) -> bool:
    """True iff some delete op in the plan removes `artifact` — either by an
    exact match or by deleting a parent directory root that contains it."""
    for target in delete_targets:
        if artifact == target:
            return True
        root = target.rstrip("/")
        if artifact == root or artifact.startswith(root + "/"):
            return True
    return False


# A hypothesis strategy that generates host-specific / cluster artifact paths.
# Some fall squarely inside the cluster/Corosync/Ceph/shared-storage family
# (so the plan MUST cover them); others are unrelated host paths used to
# exercise the invariant structure regardless of input.
_cluster_artifact = st.one_of(
    st.sampled_from(
        [
            "/etc/pve/corosync.conf",
            "/etc/corosync/corosync.conf",
            "/etc/corosync/authkey",
            "/var/lib/corosync/ringid_0",
            "/etc/pve/ceph.conf",
            "/etc/ceph/ceph.conf",
            "/etc/ceph/ceph.client.admin.keyring",
            "/var/lib/ceph/osd/ceph-0/keyring",
            "/etc/pve/storage.cfg",
            "/etc/pve/priv/known_hosts",
        ]
    ),
    # Random children under each family root.
    st.builds(
        lambda root, child: root.rstrip("/") + "/" + child,
        st.sampled_from(_CLUSTER_FAMILY_ROOTS),
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-._/",
            min_size=1,
            max_size=24,
        ),
    ),
    # Unrelated host-specific paths (NOT in the cluster family) — used to drive
    # iterations and confirm the invariant structure holds regardless of input.
    st.builds(
        lambda name: "/etc/" + name,
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-._",
            min_size=1,
            max_size=20,
        ),
    ),
)


class TestProperty6GenericImage:
    """Property 6: Cleaning produces a generic image.

    Feature: proxmox-qcow2-opcp-deployment, Property 6
    """

    @settings(max_examples=100)
    @given(artifact=_cluster_artifact)
    def test_plan_yields_generic_image_and_covers_cluster_artifacts(
        self, artifact
    ):
        """Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 13.2

        For any generated host-specific / cluster artifact path, the pure plan:
          * always encodes the full set of generic-ization invariants, and
          * removes the artifact whenever it belongs to the
            cluster/Corosync/Ceph/shared-storage family,
          * while NEVER containing an op that retains such an artifact.
        """
        cleaner = _cleaner()
        plan = cleaner.build_plan()

        deletes = _delete_targets(plan)
        run_cmds = _run_commands(plan)
        writes = _write_files(plan)
        hostnames = _hostnames(plan)
        all_params = [op.params for op in plan.operations]

        # --- Req 7.1: loopback-only /etc/network/interfaces -----------------
        interfaces = writes.get("/etc/network/interfaces")
        assert interfaces is not None, "plan must rewrite /etc/network/interfaces"
        assert "auto lo" in interfaces
        assert "iface lo inet loopback" in interfaces
        # Loopback-only: no host-specific bridges/bonds/vlans/physical ifaces.
        for forbidden in ("vmbr", "bond", "vlan", "eth", "enp", "ens", "eno"):
            assert forbidden not in interfaces, (
                f"interfaces must not carry host-specific networking ({forbidden})"
            )

        # --- Req 7.2: hostname -> pve-template ------------------------------
        assert hostnames == ["pve-template"], (
            "plan must set exactly the generic template hostname"
        )

        # --- Req 7.3: remove SSH host keys ----------------------------------
        assert any(
            t.startswith("/etc/ssh/ssh_host_") for t in deletes
        ), "plan must remove SSH host keys"

        # --- Req 7.4: reset machine-id + recreate dbus symlink --------------
        assert any(
            "machine-id" in cmd and ("truncate" in cmd or "> /etc/machine-id" in cmd)
            for cmd in run_cmds
        ), "plan must reset /etc/machine-id"
        assert "/var/lib/dbus/machine-id" in deletes, (
            "plan must remove the stale dbus machine-id"
        )
        assert any(
            "ln -sf" in cmd and "/var/lib/dbus/machine-id" in cmd
            for cmd in run_cmds
        ), "plan must recreate the dbus machine-id symlink"

        # --- Req 7.5: remove DHCP lease files -------------------------------
        assert any(
            t.startswith("/var/lib/dhcp") for t in deletes
        ), "plan must remove DHCP lease files"

        # --- Req 7.6: rotate/vacuum journal + remove archived logs ----------
        assert any("journalctl" in cmd and "--rotate" in cmd for cmd in run_cmds), (
            "plan must rotate the systemd journal"
        )
        assert any(
            "journalctl" in cmd and "--vacuum" in cmd for cmd in run_cmds
        ), "plan must vacuum the systemd journal"
        assert any(
            t.startswith("/var/log/") and t.endswith(".gz") for t in deletes
        ), "plan must remove archived (rotated) log files"

        # --- Req 7.7: apt clean ---------------------------------------------
        assert any("apt clean" in cmd for cmd in run_cmds), (
            "plan must run apt clean"
        )

        # --- Req 7.8 / 13.2: remove ALL cluster/Corosync/Ceph/shared-storage
        # Every family root is unconditionally deleted...
        for root in _CLUSTER_FAMILY_ROOTS:
            assert root in deletes, (
                f"plan must delete cluster/shared-storage root {root}"
            )

        # ...so any generated artifact in that family is covered by the plan.
        in_family = any(
            artifact == r.rstrip("/") or artifact.startswith(r.rstrip("/") + "/")
            for r in _CLUSTER_FAMILY_ROOTS
        )
        if in_family:
            assert _covered_by_plan(artifact, deletes), (
                f"cluster-family artifact {artifact} must be removed by the plan"
            )

        # --- No operation may RETAIN a cluster/shared-storage artifact ------
        # i.e. no write-file / run-command re-creates one of these roots, and
        # no param value re-introduces a cluster/Ceph/corosync config path.
        for params in all_params:
            for value in params.values():
                for root in _CLUSTER_FAMILY_ROOTS:
                    # The delete ops naturally carry the root as their 'path';
                    # only non-delete reintroduction would be a violation.
                    pass
        # Specifically: no write-file / set-hostname / run-command op targets a
        # cluster-family path (which would re-create it after deletion).
        for op in plan.operations:
            if op.action == "delete":
                continue
            touched = op.params.get("path", "")
            cmd = op.params.get("command", "")
            for root in _CLUSTER_FAMILY_ROOTS:
                r = root.rstrip("/")
                assert not (touched == r or touched.startswith(r + "/")), (
                    f"non-delete op must not re-create cluster path {touched}"
                )
                assert r not in cmd, (
                    f"run-command must not re-create cluster path via {cmd!r}"
                )

        # --- Purity: build_plan is deterministic and side-effect free -------
        cleaner.runner.run.assert_not_called()
        plan2 = cleaner.build_plan()
        assert _delete_targets(plan2) == deletes
        assert _run_commands(plan2) == run_cmds
        assert _write_files(plan2) == writes
        assert _hostnames(plan2) == hostnames


class TestApply:
    """Unit tests for ImageCleaner.apply (Req 7.1, 7.8)."""

    def test_apply_issues_exactly_one_virt_customize_invocation(self):
        runner = MagicMock()
        cleaner = ImageCleaner(runner=runner)
        plan = cleaner.build_plan()
        disk = "/var/lib/libvirt/images/proxmox-image-builder.qcow2"

        cleaner.apply(disk, plan)

        # Exactly ONE runner call translating the whole plan.
        runner.run.assert_called_once()
        argv = runner.run.call_args[0][0]
        assert argv[:3] == ["virt-customize", "-a", disk]

    def test_apply_translates_plan_into_single_argv(self):
        """The single invocation must carry flags for every plan op (Req 7.1,
        7.8): loopback interfaces, pve-template hostname, and cluster deletes."""
        runner = MagicMock()
        cleaner = ImageCleaner(runner=runner)
        plan = cleaner.build_plan()
        disk = "/tmp/disk.qcow2"

        cleaner.apply(disk, plan)

        argv = runner.run.call_args[0][0]
        joined = " ".join(argv)
        # One virt-customize process, not one per op.
        assert argv.count("virt-customize") == 1
        # Req 7.1 loopback interfaces translated to a --write.
        assert "--write" in argv
        assert "/etc/network/interfaces:" in joined
        # Req 7.2 hostname.
        assert "--hostname" in argv
        assert "pve-template" in argv
        # Req 7.8 cluster/shared-storage deletes present as --delete flags.
        assert "--delete" in argv
        assert "/etc/ceph" in argv
        assert "/etc/corosync" in argv
        assert "/etc/pve/storage.cfg" in argv

    def test_apply_raises_image_clean_error_on_runner_failure(self):
        runner = MagicMock()
        runner.run.side_effect = LocalCommandError("virt-customize boom")
        cleaner = ImageCleaner(runner=runner)
        plan = cleaner.build_plan()

        with pytest.raises(ImageCleanError) as exc_info:
            cleaner.apply("/tmp/disk.qcow2", plan)

        assert "/tmp/disk.qcow2" in str(exc_info.value)

    def test_apply_wraps_unexpected_runner_exception(self):
        runner = MagicMock()
        runner.run.side_effect = RuntimeError("unexpected")
        cleaner = ImageCleaner(runner=runner)
        plan = cleaner.build_plan()

        with pytest.raises(ImageCleanError):
            cleaner.apply("/tmp/disk.qcow2", plan)

    def test_apply_with_custom_plan_still_single_invocation(self):
        """A hand-built plan is translated in one invocation too."""
        runner = MagicMock()
        cleaner = ImageCleaner(runner=runner)
        plan = CleaningPlan(
            operations=[
                CleaningOp(action="delete", params={"path": "/etc/ceph"}),
                CleaningOp(
                    action="set-hostname", params={"hostname": "pve-template"}
                ),
            ]
        )

        cleaner.apply("/tmp/d.qcow2", plan)

        runner.run.assert_called_once()
        argv = runner.run.call_args[0][0]
        assert argv == [
            "virt-customize",
            "-a",
            "/tmp/d.qcow2",
            "--delete",
            "/etc/ceph",
            "--hostname",
            "pve-template",
        ]
