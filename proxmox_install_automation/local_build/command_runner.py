"""
Mockable local subprocess wrapper for the local KVM/libvirt build path.

`LocalCommandRunner` isolates all local shell execution behind a single,
injectable object so that every tool-invoking component (qemu-img,
virt-install, virsh, openstack, libguestfs) is unit-testable by mocking one
dependency. This mirrors how `image_builder.ISOConverter` depends on an
injected transport.

Commands are always executed from an argv list with ``shell=False`` — never a
shell string — to avoid command injection.
"""

import subprocess
import time
from typing import List, Optional

from ..logging_config import get_logger
from .exceptions import LocalCommandError
from .models import CommandResult

logger = get_logger("local_build.command_runner")


class LocalCommandRunner:
    """Thin, mockable wrapper over subprocess for local tool execution."""

    def run(
        self,
        argv: List[str],
        timeout: Optional[int] = None,
        check: bool = True,
    ) -> CommandResult:
        """
        Run ``argv`` as a list (no shell), capturing stdout and stderr.

        Uses argv lists (never shell string interpolation) to avoid command
        injection.

        Args:
            argv: The command and its arguments as a list of strings.
            timeout: Optional maximum seconds to allow the command to run.
            check: When True, raise ``LocalCommandError`` if the command exits
                with a non-zero status.

        Returns:
            A ``CommandResult`` capturing argv, exit code, stdout, stderr, and
            the measured wall-clock duration.

        Raises:
            LocalCommandError: If the command cannot be started, times out, or
                (when ``check`` is True) exits with a non-zero status.
        """
        if not argv:
            raise LocalCommandError("Cannot run an empty command (argv is empty)")

        logger.info(
            "Running local command: %s (timeout: %s, check: %s)",
            " ".join(argv),
            timeout,
            check,
        )

        start = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - start
            logger.warning(
                "Local command timed out after %ss: %s",
                timeout,
                " ".join(argv),
            )
            raise LocalCommandError(
                f"Command timed out after {timeout} seconds: {' '.join(argv)}"
            ) from exc
        except (OSError, ValueError) as exc:
            raise LocalCommandError(
                f"Failed to execute command {' '.join(argv)}: {exc}"
            ) from exc

        duration = time.monotonic() - start
        result = CommandResult(
            argv=list(argv),
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_seconds=duration,
        )

        if check and result.exit_code != 0:
            logger.error(
                "Local command failed with exit code %d: %s\n%s",
                result.exit_code,
                " ".join(argv),
                result.stderr,
            )
            raise LocalCommandError(
                f"Command exited with code {result.exit_code}: "
                f"{' '.join(argv)}\n{result.stderr}"
            )

        logger.debug(
            "Local command completed in %.3fs (exit code %d)",
            duration,
            result.exit_code,
        )
        return result


__all__ = ["LocalCommandRunner"]
