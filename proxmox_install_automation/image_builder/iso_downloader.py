"""
ISO downloader component for the image build pipeline.

Downloads the Proxmox ISO to the build instance via SSH,
verifies integrity by file size comparison, and handles
disk space checks and retry logic.
"""

import time
from typing import Optional

from ..logging_config import get_logger
from ..models import ExecutionResult
from ..provisioner.ssh import SSHConnection
from .exceptions import ISODownloadError

logger = get_logger("image_builder.iso_downloader")

# Constants
DEFAULT_DOWNLOAD_TIMEOUT = 1800  # seconds
DEFAULT_DOWNLOAD_DIR = "/tmp"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10


class ISODownloader:
    """Downloads and verifies the Proxmox ISO on the build instance."""

    def check_disk_space(
        self, ssh: SSHConnection, directory: str, required_bytes: int
    ) -> bool:
        """
        Check if sufficient disk space is available on the remote instance.

        Args:
            ssh: Active SSH connection to the build instance.
            directory: Directory where the ISO will be stored.
            required_bytes: Number of bytes needed for the download.

        Returns:
            True if sufficient space is available.

        Raises:
            ISODownloadError: If insufficient disk space, including
                available and required byte values in the message.
        """
        logger.info(
            "Checking disk space in %s (need %d bytes)", directory, required_bytes
        )

        # Use df to get available bytes for the target directory
        result: ExecutionResult = ssh.execute(
            f"df --output=avail -B1 {directory} | tail -1"
        )

        if not result.success:
            raise ISODownloadError(
                f"Failed to check disk space in {directory}: {result.stderr}"
            )

        try:
            available_bytes = int(result.stdout.strip())
        except (ValueError, TypeError) as e:
            raise ISODownloadError(
                f"Could not parse disk space output: {result.stdout.strip()}"
            ) from e

        if available_bytes < required_bytes:
            raise ISODownloadError(
                f"Insufficient disk space in {directory}: "
                f"available {available_bytes} bytes, "
                f"required {required_bytes} bytes"
            )

        logger.info(
            "Disk space check passed: %d bytes available, %d bytes required",
            available_bytes,
            required_bytes,
        )
        return True

    def download(
        self,
        ssh: SSHConnection,
        url: str,
        dest_dir: str = DEFAULT_DOWNLOAD_DIR,
        timeout: int = DEFAULT_DOWNLOAD_TIMEOUT,
    ) -> str:
        """
        Download the ISO file to the build instance via SSH.

        Executes wget on the remote instance. Retries up to 3 times
        with a 10-second delay between attempts on failure.

        Args:
            ssh: Active SSH connection to the build instance.
            url: HTTPS URL of the ISO to download.
            dest_dir: Directory on the build instance to store the ISO.
            timeout: Download timeout in seconds (default 1800s).

        Returns:
            Full path to the downloaded ISO file on the remote instance.

        Raises:
            ISODownloadError: If download fails after all retry attempts,
                including the failure reason and number of attempts made.
        """
        # Extract filename from URL
        filename = url.rstrip("/").split("/")[-1]
        dest_path = f"{dest_dir}/{filename}"

        logger.info("Downloading ISO from %s to %s", url, dest_path)

        last_error: Optional[str] = None

        for attempt in range(1, MAX_RETRIES + 1):
            logger.info("Download attempt %d/%d", attempt, MAX_RETRIES)

            # Use wget with timeout and output to destination path
            # --tries=1 to let our retry logic handle retries
            # --timeout for connect/read timeout per attempt
            result: ExecutionResult = ssh.execute(
                f"wget --tries=1 --timeout={timeout} -O {dest_path} '{url}'",
                timeout=timeout + 60,  # Give extra buffer beyond wget timeout
            )

            if result.success:
                logger.info("ISO downloaded successfully to %s", dest_path)
                return dest_path

            last_error = result.stderr.strip() or result.stdout.strip()
            logger.warning(
                "Download attempt %d failed: %s", attempt, last_error
            )

            # Clean up partial download
            ssh.execute(f"rm -f {dest_path}")

            if attempt < MAX_RETRIES:
                logger.info(
                    "Retrying in %d seconds...", RETRY_DELAY_SECONDS
                )
                time.sleep(RETRY_DELAY_SECONDS)

        raise ISODownloadError(
            f"ISO download failed after {MAX_RETRIES} attempts. "
            f"URL: {url}, reason: {last_error}"
        )

    def verify_integrity(
        self, ssh: SSHConnection, file_path: str, expected_size: int
    ) -> bool:
        """
        Verify the integrity of a downloaded ISO by comparing file size.

        Args:
            ssh: Active SSH connection to the build instance.
            file_path: Path to the downloaded ISO file.
            expected_size: Expected file size in bytes.

        Returns:
            True if the file size matches the expected size exactly.

        Raises:
            ISODownloadError: If the file does not exist or size
                does not match expected.
        """
        logger.info(
            "Verifying integrity of %s (expected %d bytes)",
            file_path,
            expected_size,
        )

        # Get actual file size using stat
        result: ExecutionResult = ssh.execute(
            f"stat -c %s {file_path}"
        )

        if not result.success:
            raise ISODownloadError(
                f"Failed to verify ISO file at {file_path}: {result.stderr}"
            )

        try:
            actual_size = int(result.stdout.strip())
        except (ValueError, TypeError) as e:
            raise ISODownloadError(
                f"Could not parse file size output: {result.stdout.strip()}"
            ) from e

        if actual_size != expected_size:
            raise ISODownloadError(
                f"ISO integrity check failed: "
                f"actual size {actual_size} bytes != "
                f"expected size {expected_size} bytes"
            )

        logger.info("ISO integrity check passed: %d bytes", actual_size)
        return True
