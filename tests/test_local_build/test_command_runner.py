"""
Tests for the LocalCommandRunner component (local_build, Requirements 2.5, 4.3, 5.3).

Covers:
- success path: subprocess.run invoked with argv as a list and shell=False, and
  the returned CommandResult has argv/exit_code/stdout/stderr populated.
- non-zero exit with check=True raises LocalCommandError.
- non-zero exit with check=False returns the CommandResult without raising.
- subprocess.TimeoutExpired raises LocalCommandError.
- empty argv raises LocalCommandError before touching subprocess.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from proxmox_install_automation.local_build.command_runner import LocalCommandRunner
from proxmox_install_automation.local_build.exceptions import LocalCommandError
from proxmox_install_automation.local_build.models import CommandResult

MODULE = "proxmox_install_automation.local_build.command_runner"


def _completed(returncode=0, stdout="out", stderr="err"):
    """Build a fake subprocess.CompletedProcess-like object."""
    completed = MagicMock()
    completed.returncode = returncode
    completed.stdout = stdout
    completed.stderr = stderr
    return completed


class TestSuccess:
    def test_success_returns_populated_command_result(self):
        argv = ["qemu-img", "info", "/tmp/disk.qcow2"]
        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = _completed(
                returncode=0, stdout="virtual size: 64G", stderr=""
            )
            result = LocalCommandRunner().run(argv)

        assert isinstance(result, CommandResult)
        assert result.argv == argv
        assert result.exit_code == 0
        assert result.stdout == "virtual size: 64G"
        assert result.stderr == ""
        assert result.success is True
        assert result.duration_seconds >= 0.0

    def test_argv_passed_as_list_with_shell_false(self):
        argv = ["virsh", "list", "--all"]
        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = _completed(returncode=0)
            LocalCommandRunner().run(argv, timeout=120)

        mock_run.assert_called_once()
        call_args, call_kwargs = mock_run.call_args
        passed_argv = call_args[0] if call_args else call_kwargs["args"]
        assert isinstance(passed_argv, list)
        assert passed_argv == argv
        assert call_kwargs["shell"] is False
        assert call_kwargs["timeout"] == 120

    def test_result_argv_is_a_copy_not_the_input_object(self):
        argv = ["echo", "hi"]
        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = _completed(returncode=0)
            result = LocalCommandRunner().run(argv)

        assert result.argv == argv
        assert result.argv is not argv


class TestNonZeroExit:
    def test_nonzero_exit_with_check_true_raises(self):
        argv = ["false"]
        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = _completed(
                returncode=1, stdout="", stderr="boom"
            )
            with pytest.raises(LocalCommandError) as exc_info:
                LocalCommandRunner().run(argv, check=True)

        assert "1" in str(exc_info.value)
        assert "boom" in str(exc_info.value)

    def test_nonzero_exit_with_check_false_returns_result(self):
        argv = ["grep", "missing", "/tmp/file"]
        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = _completed(
                returncode=2, stdout="", stderr="no match"
            )
            result = LocalCommandRunner().run(argv, check=False)

        assert isinstance(result, CommandResult)
        assert result.exit_code == 2
        assert result.stderr == "no match"
        assert result.success is False


class TestTimeout:
    def test_timeout_raises_local_command_error(self):
        argv = ["sleep", "99"]
        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=argv, timeout=5)
            with pytest.raises(LocalCommandError) as exc_info:
                LocalCommandRunner().run(argv, timeout=5)

        assert "timed out" in str(exc_info.value).lower()


class TestEmptyArgv:
    def test_empty_argv_raises_without_calling_subprocess(self):
        with patch(f"{MODULE}.subprocess.run") as mock_run:
            with pytest.raises(LocalCommandError):
                LocalCommandRunner().run([])
        mock_run.assert_not_called()


class TestExecutionError:
    def test_oserror_raises_local_command_error(self):
        argv = ["does-not-exist"]
        with patch(f"{MODULE}.subprocess.run") as mock_run:
            mock_run.side_effect = OSError("No such file")
            with pytest.raises(LocalCommandError) as exc_info:
                LocalCommandRunner().run(argv)

        assert "does-not-exist" in str(exc_info.value)
