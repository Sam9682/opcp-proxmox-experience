"""
SSH connection management.
"""

import time
from pathlib import Path
from typing import Optional

import paramiko

from ..exceptions import SSHCommandError, SSHConnectionError
from ..logging_config import get_logger
from ..models import ExecutionResult

logger = get_logger("provisioner.ssh")


class SSHConnection:
    """Manages SSH connections to remote instances."""

    def __init__(self) -> None:
        self._client: Optional[paramiko.SSHClient] = None
        self._host: Optional[str] = None

    def connect(
        self,
        host: str,
        username: str,
        key_path: str,
        timeout: int = 300,
        retry_interval: int = 15,
    ) -> None:
        """
        Establish SSH connection with retry logic.

        Args:
            host: Remote host IP or hostname.
            username: SSH username.
            key_path: Path to SSH private key.
            timeout: Total timeout in seconds.
            retry_interval: Seconds between retry attempts.

        Raises:
            SSHConnectionError: If connection cannot be established.
        """
        self._host = host
        key_file = Path(key_path).expanduser()

        if not key_file.exists():
            raise SSHConnectionError(f"SSH key not found: {key_file}")

        logger.info("Connecting to %s@%s (timeout: %ds)", username, host, timeout)
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(
                    hostname=host,
                    username=username,
                    key_filename=str(key_file),
                    timeout=30,
                    look_for_keys=False,
                    allow_agent=False,
                )
                self._client = client
                logger.info("SSH connection established to %s", host)
                return

            except (
                paramiko.ssh_exception.NoValidConnectionsError,
                paramiko.ssh_exception.SSHException,
                OSError,
                TimeoutError,
            ) as e:
                elapsed = int(time.time() - start_time)
                logger.debug(
                    "SSH connection attempt failed (%ds elapsed): %s",
                    elapsed,
                    str(e),
                )
                time.sleep(retry_interval)

        raise SSHConnectionError(
            f"Could not establish SSH connection to {host} within {timeout}s"
        )

    def execute(self, command: str, timeout: int = 600) -> ExecutionResult:
        """
        Execute a command over SSH.

        Args:
            command: Command to execute.
            timeout: Command timeout in seconds.

        Returns:
            ExecutionResult with exit code, stdout, stderr.

        Raises:
            SSHConnectionError: If not connected.
            SSHCommandError: If execution fails unexpectedly.
        """
        if self._client is None:
            raise SSHConnectionError("Not connected. Call connect() first.")

        logger.debug("Executing: %s", command[:100])
        start_time = time.time()

        try:
            stdin, stdout, stderr = self._client.exec_command(
                command, timeout=timeout
            )
            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode("utf-8", errors="replace")
            stderr_text = stderr.read().decode("utf-8", errors="replace")
            duration = time.time() - start_time

            result = ExecutionResult(
                exit_code=exit_code,
                stdout=stdout_text,
                stderr=stderr_text,
                command=command,
                duration_seconds=duration,
            )

            if exit_code != 0:
                logger.warning(
                    "Command exited with code %d: %s", exit_code, command[:100]
                )
                logger.debug("stderr: %s", stderr_text[:500])

            return result

        except Exception as e:
            raise SSHCommandError(
                f"Failed to execute command on {self._host}: {e}"
            ) from e

    def execute_sudo(self, command: str, timeout: int = 600) -> ExecutionResult:
        """
        Execute a command with sudo.

        Args:
            command: Command to execute (without sudo prefix).
            timeout: Command timeout in seconds.

        Returns:
            ExecutionResult.
        """
        return self.execute(f"sudo {command}", timeout=timeout)

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """
        Upload a file via SFTP.

        Args:
            local_path: Local file path.
            remote_path: Remote destination path.

        Returns:
            True if upload succeeds.
        """
        if self._client is None:
            raise SSHConnectionError("Not connected. Call connect() first.")

        try:
            sftp = self._client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            logger.info("Uploaded %s to %s:%s", local_path, self._host, remote_path)
            return True
        except Exception as e:
            logger.error("Failed to upload file: %s", e)
            return False

    def disconnect(self) -> None:
        """Close the SSH connection."""
        if self._client:
            self._client.close()
            self._client = None
            logger.info("SSH connection closed to %s", self._host)

    @property
    def is_connected(self) -> bool:
        """Check if SSH is connected."""
        if self._client is None:
            return False
        transport = self._client.get_transport()
        return transport is not None and transport.is_active()
