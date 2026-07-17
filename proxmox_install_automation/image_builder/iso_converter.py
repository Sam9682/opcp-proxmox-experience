"""
ISO to qcow2 converter using qemu-img.

Executes `qemu-img convert` on a remote instance via SSH to produce
a qcow2 disk image from a raw ISO file.
"""

from ..exceptions import SSHCommandError
from ..logging_config import get_logger
from ..provisioner.ssh import SSHConnection
from .exceptions import ISOConversionError

logger = get_logger("image_builder.iso_converter")


class ISOConverter:
    """Converts ISO to qcow2 format via qemu-img on a remote instance."""

    def convert(
        self,
        ssh: SSHConnection,
        iso_path: str,
        qcow2_path: str,
        timeout: int = 600,
    ) -> str:
        """
        Convert an ISO file to qcow2 format using qemu-img.

        Args:
            ssh: Active SSH connection to the build instance.
            iso_path: Path to the source ISO file on the remote instance.
            qcow2_path: Desired path for the output qcow2 file.
            timeout: Maximum seconds to allow for conversion (default 600).

        Returns:
            Path to the created qcow2 file.

        Raises:
            ISOConversionError: If conversion fails, times out, or output
                verification fails.
        """
        command = f"qemu-img convert -f raw -O qcow2 {iso_path} {qcow2_path}"
        logger.info(
            "Starting ISO conversion: %s -> %s (timeout: %ds)",
            iso_path,
            qcow2_path,
            timeout,
        )

        try:
            result = ssh.execute(command, timeout=timeout)
        except SSHCommandError as e:
            # Timeout or other SSH execution failure — kill the process
            error_msg = str(e)
            if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
                logger.warning(
                    "qemu-img conversion timed out after %ds, killing process",
                    timeout,
                )
                self._kill_qemu_img(ssh)
                raise ISOConversionError(
                    f"qemu-img conversion timed out after {timeout} seconds"
                ) from e
            # Re-raise as ISOConversionError for other SSH failures
            raise ISOConversionError(
                f"qemu-img execution failed: {error_msg}"
            ) from e

        if result.exit_code != 0:
            logger.error(
                "qemu-img conversion failed with exit code %d: %s",
                result.exit_code,
                result.stderr,
            )
            raise ISOConversionError(result.stderr)

        logger.info("ISO conversion completed in %.1fs", result.duration_seconds)
        return qcow2_path

    def verify_output(self, ssh: SSHConnection, qcow2_path: str) -> bool:
        """
        Verify the output qcow2 file exists and has size > 0.

        Args:
            ssh: Active SSH connection to the build instance.
            qcow2_path: Path to the qcow2 file to verify.

        Returns:
            True if the file exists and has size > 0.

        Raises:
            ISOConversionError: If the file does not exist or has zero size.
        """
        logger.debug("Verifying output file: %s", qcow2_path)

        # Check file exists and get its size
        result = ssh.execute(f"stat --format='%s' {qcow2_path}")

        if result.exit_code != 0:
            raise ISOConversionError(
                f"Output file does not exist: {qcow2_path}"
            )

        try:
            file_size = int(result.stdout.strip())
        except (ValueError, TypeError):
            raise ISOConversionError(
                f"Could not determine file size for: {qcow2_path}"
            )

        if file_size <= 0:
            raise ISOConversionError(
                f"Output file has zero size: {qcow2_path}"
            )

        logger.info("Output file verified: %s (%d bytes)", qcow2_path, file_size)
        return True

    def _kill_qemu_img(self, ssh: SSHConnection) -> None:
        """Attempt to kill any running qemu-img process on the remote host."""
        try:
            ssh.execute("pkill -f qemu-img", timeout=30)
            logger.info("Killed qemu-img process")
        except (SSHCommandError, Exception) as e:
            logger.warning("Failed to kill qemu-img process: %s", e)
