"""
Tests for the CLI wiring of the local-build subcommand group
(proxmox_install_automation.cli).

Covers three tasks from the proxmox-qcow2-opcp-deployment spec:

- Task 18.2 — Unit tests for the CLI subcommands (Requirements 1.1, 1.2, 14.1):
  the existing ``build-image`` and ``install`` commands remain registered on
  the top-level ``main`` group (preserved, unchanged), the additive
  ``local-build`` group exists, and it exposes the ``check``, ``run`` and
  ``deploy`` subcommands. A smoke invocation of ``local-build run --dry-run``
  against a valid temp YAML config exits 0 with ``LocalImageBuilder`` mocked.

- Task 18.3 — Property 10: CLI exit-code contract (Requirements 2.5, 3.5,
  4.3, 5.3, 8.5, 9.3, 10.4, 11.4, 14.2). For any command outcome the CLI
  returns exit code 0 iff the outcome is success; any failure (a raised
  ProxmoxAutomationError subclass) maps to a non-zero exit code.

- Task 18.4 — Property 1: Existing image_builder public API is preserved
  (Requirements 1.3). Every name exported by image_builder.__all__ remains
  importable from image_builder with a compatible kind (class/function).

All subprocess/orchestrator interaction is mocked; no real build, prerequisite
probe, or OpenStack call is performed.
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from proxmox_install_automation.cli import main
from proxmox_install_automation.exceptions import ProxmoxAutomationError
from proxmox_install_automation.local_build.exceptions import (
    BootTestError,
    BuildVMError,
    GlanceImportError,
    ImageCleanError,
    ImageFinalizeError,
    IronicDeployError,
    ISOStagingError,
    LocalBuildError,
    LocalCommandError,
    PrerequisiteError,
    SystemDiskError,
)
from proxmox_install_automation.local_build.models import PrerequisiteReport


# A minimal but *valid* local-build YAML config. The only field the validator
# requires beyond the dataclass defaults is a non-empty ``iso_source_path``;
# the default architecture (x86_64), sizes, names, and timeouts all pass
# LocalBuildConfigValidator.
_VALID_CONFIG_YAML = """\
local_build:
  iso_source_path: /isos/proxmox-ve.iso
  architecture: x86_64
"""


def _write_config(tmp_path) -> str:
    """Write a valid local-build config to a temp file and return its path."""
    config_file = tmp_path / "local_build.yaml"
    config_file.write_text(_VALID_CONFIG_YAML, encoding="utf-8")
    return str(config_file)


# ---------------------------------------------------------------------------
# Task 18.2 — Unit tests for the CLI subcommands
# Validates: Requirements 1.1, 1.2, 14.1
# ---------------------------------------------------------------------------


class TestCliCommandRegistration:
    def test_existing_commands_preserved(self):
        """``build-image`` and ``install`` remain registered on main (Req 1.2)."""
        assert "build-image" in main.commands
        assert "install" in main.commands

    def test_local_build_group_registered(self):
        """The additive ``local-build`` group exists on main (Req 1.1)."""
        assert "local-build" in main.commands

    def test_local_build_subcommands_present(self):
        """``local-build`` exposes check, run and deploy (Req 1.1, 14.1)."""
        local_build = main.commands["local-build"]
        # It is a group with its own subcommands.
        assert hasattr(local_build, "commands")
        for sub in ("check", "run", "deploy"):
            assert sub in local_build.commands

    def test_local_build_run_has_dry_run_option(self):
        """``local-build run`` exposes a --dry-run flag (Req 14.1)."""
        run_cmd = main.commands["local-build"].commands["run"]
        option_names = {
            opt
            for param in run_cmd.params
            for opt in getattr(param, "opts", [])
        }
        assert "--dry-run" in option_names
        assert "--config" in option_names


class TestLocalBuildRunDryRun:
    def test_run_dry_run_exits_zero_with_valid_config(self, tmp_path):
        """
        ``local-build run --dry-run`` with a valid config validates and exits 0
        without invoking a real build (LocalImageBuilder is mocked). (Req 14.1)
        """
        config_path = _write_config(tmp_path)
        runner = CliRunner()

        # Mock the builder so that even if --dry-run short-circuiting changed,
        # no real build.build(...) would run.
        with patch(
            "proxmox_install_automation.local_build.LocalImageBuilder"
        ) as mock_builder:
            result = runner.invoke(
                main,
                ["local-build", "run", "--config", config_path, "--dry-run"],
            )

        assert result.exit_code == 0, result.output
        # --dry-run validates only and must not build.
        mock_builder.return_value.build.assert_not_called()


# ---------------------------------------------------------------------------
# Task 18.3 — Property 10: CLI exit-code contract
# Feature: proxmox-qcow2-opcp-deployment, Property 10
# Validates: Requirements 2.5, 3.5, 4.3, 5.3, 8.5, 9.3, 10.4, 11.4, 14.2
# ---------------------------------------------------------------------------


# Every ProxmoxAutomationError subclass a local-build subcommand may surface.
_LOCAL_BUILD_ERRORS = [
    LocalBuildError,
    LocalCommandError,
    PrerequisiteError,
    ISOStagingError,
    SystemDiskError,
    BuildVMError,
    ImageCleanError,
    ImageFinalizeError,
    BootTestError,
    GlanceImportError,
    IronicDeployError,
    # The generic base, too — the handler catches ProxmoxAutomationError.
    ProxmoxAutomationError,
]

# An all-prerequisites-satisfied report → the ``check`` subcommand succeeds.
_OK_REPORT = PrerequisiteReport(
    os_supported=True,
    missing_packages=[],
    kvm_available=True,
    uefi_available=True,
)


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    success=st.booleans(),
    error_cls=st.sampled_from(_LOCAL_BUILD_ERRORS),
)
def test_property_cli_exit_code_contract(tmp_path, success, error_cls):
    """
    Feature: proxmox-qcow2-opcp-deployment, Property 10

    For any command outcome, the CLI exit code is 0 iff the outcome is a
    success. Any failure — modelled as a raised ProxmoxAutomationError
    subclass from the component the subcommand drives — maps to a non-zero
    exit code.

    Driven through ``local-build check``: its PrerequisiteChecker is patched to
    either return an all-satisfied report (success) or raise a
    hypothesis-chosen ProxmoxAutomationError subclass (failure). A valid temp
    config file ensures argument parsing and config loading succeed, so the
    only variable is the component outcome.

    Validates: Requirements 2.5, 3.5, 4.3, 5.3, 8.5, 9.3, 10.4, 11.4, 14.2
    """
    config_path = _write_config(tmp_path)
    runner = CliRunner()

    checker_instance = MagicMock()
    if success:
        checker_instance.check.return_value = _OK_REPORT
    else:
        checker_instance.check.side_effect = error_cls("boom")

    # Patch the names the ``check`` handler resolves from the local_build
    # package at call time. LocalCommandRunner is patched so no real subprocess
    # probe is attempted when constructing the checker's dependency.
    with patch(
        "proxmox_install_automation.local_build.PrerequisiteChecker",
        return_value=checker_instance,
    ), patch(
        "proxmox_install_automation.local_build.LocalCommandRunner",
        return_value=MagicMock(),
    ):
        result = runner.invoke(
            main,
            ["local-build", "check", "--config", config_path],
        )

    # Exit code is 0 iff the outcome was a success.
    assert (result.exit_code == 0) == success, (
        f"success={success} error_cls={error_cls.__name__} "
        f"exit_code={result.exit_code} output={result.output!r}"
    )
    if not success:
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Task 18.4 — Property 1: Existing image_builder public API is preserved
# Feature: proxmox-qcow2-opcp-deployment, Property 1
# Validates: Requirements 1.3
# ---------------------------------------------------------------------------


# Baseline snapshot of the image_builder public surface, captured once from
# the package's declared __all__. The property re-imports each name and
# confirms it is still present with a compatible kind.
import proxmox_install_automation.image_builder as _image_builder  # noqa: E402

_IMAGE_BUILDER_BASELINE = tuple(_image_builder.__all__)


def test_image_builder_baseline_is_non_empty():
    """Guard: the captured baseline actually contains exported names (Req 1.3)."""
    assert len(_IMAGE_BUILDER_BASELINE) > 0


@settings(max_examples=100)
@given(name=st.sampled_from(_IMAGE_BUILDER_BASELINE))
def test_property_image_builder_public_api_preserved(name):
    """
    Feature: proxmox-qcow2-opcp-deployment, Property 1

    Every name in the image_builder public API baseline remains importable
    from the image_builder package and retains a compatible kind: the symbol
    exists as an attribute, is listed in __all__, and is either a class or a
    callable (function/factory) — never silently dropped or turned into an
    incompatible value.

    Validates: Requirements 1.3
    """
    # Re-import fresh to prove the attribute resolves from the package today.
    import proxmox_install_automation.image_builder as image_builder

    # Still advertised in __all__.
    assert name in image_builder.__all__

    # Still importable as an attribute.
    assert hasattr(image_builder, name), f"{name} is no longer exported"
    obj = getattr(image_builder, name)
    assert obj is not None

    # Compatible kind: a class or a callable (function/factory). The two
    # function exports (load_image_build_config, generate_snapshot_name) are
    # callables; everything else in the baseline is a class.
    assert inspect.isclass(obj) or callable(obj), (
        f"{name} resolved to an incompatible kind: {type(obj)!r}"
    )

    # Functions in the baseline stay functions (not accidentally classes).
    if name in ("load_image_build_config", "generate_snapshot_name"):
        assert inspect.isfunction(obj), (
            f"{name} is expected to remain a function, got {type(obj)!r}"
        )
    else:
        assert inspect.isclass(obj), (
            f"{name} is expected to remain a class, got {type(obj)!r}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
