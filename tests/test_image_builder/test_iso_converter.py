"""
Tests for the ISO converter component.

Tests cover:
- Successful conversion flow
- Non-zero exit code handling
- Timeout handling and process kill
- Output verification (file exists, size > 0, missing file, zero size)
"""

from unittest.mock import MagicMock, patch

import pytest

from proxmox_install_automation.exceptions import SSHCommandError
from proxmox_install_automation.image_builder.exceptions import ISOConversionError
from proxmox_install_automation.image_builder.iso_converter import ISOConverter
from proxmox_install_automation.models import ExecutionResult


@pytest.fixture
def converter():
    """Create an ISOConverter instance."""
    return ISOConverter()


@pytest.fixture
def mock_ssh():
    """Create a mock SSH connection."""
    return MagicMock()


class TestISOConverterConvert:
    """Tests for ISOConverter.convert()."""

    def test_successful_conversion(self, converter, mock_ssh):
        """Test successful ISO to qcow2 conversion."""
        mock_ssh.execute.return_value = ExecutionResult(
            exit_code=0,
            stdout="",
            stderr="",
            command="qemu-img convert -f raw -O qcow2 /tmp/proxmox.iso /tmp/proxmox.qcow2",
            duration_seconds=120.5,
        )

        result = converter.convert(
            mock_ssh, "/tmp/proxmox.iso", "/tmp/proxmox.qcow2", timeout=600
        )

        assert result == "/tmp/proxmox.qcow2"
        mock_ssh.execute.assert_called_once_with(
            "qemu-img convert -f raw -O qcow2 /tmp/proxmox.iso /tmp/proxmox.qcow2",
            timeout=600,
        )

    def test_command_format(self, converter, mock_ssh):
        """Test that the command is constructed exactly as specified."""
        mock_ssh.execute.return_value = ExecutionResult(
            exit_code=0,
            stdout="",
            stderr="",
            command="",
            duration_seconds=1.0,
        )

        converter.convert(mock_ssh, "/path/to/input.iso", "/path/to/output.qcow2")

        expected_cmd = "qemu-img convert -f raw -O qcow2 /path/to/input.iso /path/to/output.qcow2"
        mock_ssh.execute.assert_called_once_with(expected_cmd, timeout=600)

    def test_non_zero_exit_code_raises_with_stderr(self, converter, mock_ssh):
        """Test that non-zero exit code raises ISOConversionError with stderr."""
        stderr_output = "qemu-img: Could not open '/tmp/bad.iso': No such file or directory"
        mock_ssh.execute.return_value = ExecutionResult(
            exit_code=1,
            stdout="",
            stderr=stderr_output,
            command="qemu-img convert ...",
            duration_seconds=0.5,
        )

        with pytest.raises(ISOConversionError, match=stderr_output):
            converter.convert(mock_ssh, "/tmp/bad.iso", "/tmp/out.qcow2")

    def test_timeout_kills_process_and_raises(self, converter, mock_ssh):
        """Test that timeout kills qemu-img process and raises error."""
        mock_ssh.execute.side_effect = [
            SSHCommandError("Failed to execute command on host: timed out"),
            # Second call is the pkill attempt
            ExecutionResult(
                exit_code=0, stdout="", stderr="", command="pkill -f qemu-img", duration_seconds=0.1
            ),
        ]

        with pytest.raises(ISOConversionError, match="timed out after 600 seconds"):
            converter.convert(mock_ssh, "/tmp/proxmox.iso", "/tmp/out.qcow2", timeout=600)

        # Verify pkill was called
        assert mock_ssh.execute.call_count == 2
        mock_ssh.execute.assert_any_call("pkill -f qemu-img", timeout=30)

    def test_timeout_with_custom_timeout_value(self, converter, mock_ssh):
        """Test timeout error message includes the custom timeout value."""
        mock_ssh.execute.side_effect = [
            SSHCommandError("Command timed out"),
            ExecutionResult(
                exit_code=0, stdout="", stderr="", command="pkill", duration_seconds=0.1
            ),
        ]

        with pytest.raises(ISOConversionError, match="timed out after 300 seconds"):
            converter.convert(mock_ssh, "/tmp/in.iso", "/tmp/out.qcow2", timeout=300)

    def test_ssh_error_non_timeout_raises(self, converter, mock_ssh):
        """Test that non-timeout SSH errors raise ISOConversionError."""
        mock_ssh.execute.side_effect = SSHCommandError(
            "Failed to execute command on host: Connection reset"
        )

        with pytest.raises(ISOConversionError, match="qemu-img execution failed"):
            converter.convert(mock_ssh, "/tmp/in.iso", "/tmp/out.qcow2")

    def test_default_timeout_is_600(self, converter, mock_ssh):
        """Test that default timeout is 600 seconds."""
        mock_ssh.execute.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", command="", duration_seconds=1.0
        )

        converter.convert(mock_ssh, "/tmp/in.iso", "/tmp/out.qcow2")

        mock_ssh.execute.assert_called_once_with(
            "qemu-img convert -f raw -O qcow2 /tmp/in.iso /tmp/out.qcow2",
            timeout=600,
        )


class TestISOConverterVerifyOutput:
    """Tests for ISOConverter.verify_output()."""

    def test_verify_output_success(self, converter, mock_ssh):
        """Test successful verification with existing file > 0 bytes."""
        mock_ssh.execute.return_value = ExecutionResult(
            exit_code=0,
            stdout="1073741824\n",
            stderr="",
            command="stat --format='%s' /tmp/out.qcow2",
            duration_seconds=0.1,
        )

        assert converter.verify_output(mock_ssh, "/tmp/out.qcow2") is True

    def test_verify_output_file_not_found(self, converter, mock_ssh):
        """Test verification fails when file does not exist."""
        mock_ssh.execute.return_value = ExecutionResult(
            exit_code=1,
            stdout="",
            stderr="stat: cannot stat '/tmp/missing.qcow2': No such file or directory",
            command="stat --format='%s' /tmp/missing.qcow2",
            duration_seconds=0.1,
        )

        with pytest.raises(ISOConversionError, match="does not exist"):
            converter.verify_output(mock_ssh, "/tmp/missing.qcow2")

    def test_verify_output_zero_size(self, converter, mock_ssh):
        """Test verification fails when file has zero size."""
        mock_ssh.execute.return_value = ExecutionResult(
            exit_code=0,
            stdout="0\n",
            stderr="",
            command="stat --format='%s' /tmp/empty.qcow2",
            duration_seconds=0.1,
        )

        with pytest.raises(ISOConversionError, match="zero size"):
            converter.verify_output(mock_ssh, "/tmp/empty.qcow2")

    def test_verify_output_invalid_size_output(self, converter, mock_ssh):
        """Test verification handles invalid stat output gracefully."""
        mock_ssh.execute.return_value = ExecutionResult(
            exit_code=0,
            stdout="not-a-number\n",
            stderr="",
            command="stat --format='%s' /tmp/bad.qcow2",
            duration_seconds=0.1,
        )

        with pytest.raises(ISOConversionError, match="Could not determine file size"):
            converter.verify_output(mock_ssh, "/tmp/bad.qcow2")
