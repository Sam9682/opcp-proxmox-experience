"""
Build-host prerequisite checking for the local KVM/libvirt build path (Req 2).

`PrerequisiteChecker` verifies that the Local_Build_Host runs a Debian/Ubuntu
lineage OS, has the required virtualization packages installed, exposes KVM
hardware acceleration, and provides UEFI/OVMF firmware. It returns an aggregate
``PrerequisiteReport``; the orchestrator raises ``PrerequisiteError`` when
``report.ok`` is False.

Two helpers are deliberately pure (no I/O) so they can be exercised directly by
property-based tests:
  - ``detect_os_family(os_release)``        -> bool
  - ``compute_missing_packages(installed)`` -> list[str]

All subprocess execution flows through the injected ``LocalCommandRunner`` so
``check()`` is unit-testable by mocking a single dependency.
"""

import os
from typing import Dict, List, Set

from ..logging_config import get_logger
from .command_runner import LocalCommandRunner
from .exceptions import LocalCommandError
from .models import PrerequisiteReport

logger = get_logger("local_build.prerequisites")

# Packages required on the Local_Build_Host (Req 2.2).
REQUIRED_PACKAGES = (
    "qemu-utils",
    "qemu-system-x86",
    "libvirt-daemon-system",
    "libvirt-clients",
    "virtinst",
    "ovmf",
)

# OS identifiers that indicate a Debian/Ubuntu lineage (Req 2.1).
_DEBIAN_LINEAGE = frozenset({"debian", "ubuntu"})

# Filesystem probe locations.
_KVM_DEVICE = "/dev/kvm"
_OVMF_FIRMWARE_DESCRIPTOR = "/usr/share/OVMF/OVMF_CODE.fd"
_OS_RELEASE_PATH = "/etc/os-release"


def detect_os_family(os_release: Dict[str, str]) -> bool:
    """
    Pure: return True iff the parsed os-release indicates Debian/Ubuntu lineage.

    Inspects the ``ID`` field and the space-separated ``ID_LIKE`` field. The
    host is considered supported when any of those identifiers is ``debian`` or
    ``ubuntu`` (case-insensitive). Performs no I/O. (Req 2.1)

    Args:
        os_release: Parsed key/value pairs from ``/etc/os-release``.

    Returns:
        True if the OS is part of the Debian/Ubuntu family, else False.
    """
    identifiers: Set[str] = set()

    primary = os_release.get("ID")
    if primary:
        identifiers.add(primary.strip().lower())

    id_like = os_release.get("ID_LIKE")
    if id_like:
        identifiers.update(token.lower() for token in id_like.split() if token)

    return bool(identifiers & _DEBIAN_LINEAGE)


def compute_missing_packages(installed: Set[str]) -> List[str]:
    """
    Pure: return the required packages absent from ``installed``.

    Preserves the canonical ``REQUIRED_PACKAGES`` order and performs no I/O so
    it can be property-tested directly. (Req 2.2)

    Args:
        installed: The set of package names present on the host.

    Returns:
        The ordered list of required packages not found in ``installed``.
    """
    return [pkg for pkg in REQUIRED_PACKAGES if pkg not in installed]


def parse_os_release(content: str) -> Dict[str, str]:
    """
    Pure: parse ``/etc/os-release`` text into a key/value dict.

    Ignores blank lines and comments, splits on the first ``=``, and strips a
    single layer of surrounding single or double quotes from values. Performs
    no I/O. (Req 2.1)

    Args:
        content: The raw text contents of an os-release file.

    Returns:
        A dict of the parsed key/value pairs.
    """
    parsed: Dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            parsed[key] = value
    return parsed


class PrerequisiteChecker:
    """Verify OS family, required packages, KVM accel, and OVMF firmware (Req 2)."""

    def __init__(self, runner: LocalCommandRunner):
        """
        Args:
            runner: The injected, mockable local command runner used to probe
                installed packages.
        """
        self._runner = runner

    def detect_os_family(self, os_release: Dict[str, str]) -> bool:
        """Pure: True iff ID or ID_LIKE indicates debian/ubuntu lineage. (Req 2.1)"""
        return detect_os_family(os_release)

    def compute_missing_packages(self, installed: Set[str]) -> List[str]:
        """Pure: REQUIRED_PACKAGES not present in ``installed``. (Req 2.2)"""
        return compute_missing_packages(installed)

    def check(self) -> PrerequisiteReport:
        """
        Verify OS family, required packages, KVM accel, and OVMF firmware.

        Reads ``/etc/os-release`` (Req 2.1), probes package presence via
        ``dpkg-query`` (Req 2.2), checks ``/dev/kvm`` presence (Req 2.3), and
        checks the OVMF firmware descriptor (Req 2.4). Returns an aggregate
        report; the orchestrator raises ``PrerequisiteError`` when
        ``report.ok`` is False (Req 2.5).

        Returns:
            A ``PrerequisiteReport`` describing each prerequisite's status.
        """
        os_supported = self._check_os_supported()
        installed = self._probe_installed_packages()
        missing_packages = self.compute_missing_packages(installed)
        kvm_available = self._check_kvm()
        uefi_available = self._check_ovmf()

        report = PrerequisiteReport(
            os_supported=os_supported,
            missing_packages=missing_packages,
            kvm_available=kvm_available,
            uefi_available=uefi_available,
        )

        logger.info(
            "Prerequisite check: os_supported=%s missing_packages=%s "
            "kvm_available=%s uefi_available=%s ok=%s",
            os_supported,
            missing_packages,
            kvm_available,
            uefi_available,
            report.ok,
        )
        return report

    def _check_os_supported(self) -> bool:
        """Parse /etc/os-release and classify via the pure detector. (Req 2.1)"""
        try:
            with open(_OS_RELEASE_PATH, "r", encoding="utf-8") as handle:
                content = handle.read()
        except OSError as exc:
            logger.warning("Could not read %s: %s", _OS_RELEASE_PATH, exc)
            return False
        return detect_os_family(parse_os_release(content))

    def _probe_installed_packages(self) -> Set[str]:
        """
        Probe installed packages via ``dpkg-query``. (Req 2.2)

        Queries each required package individually so a single absent package
        does not mask the status of the others. A package is considered
        installed only when ``dpkg-query`` reports the ``install ok installed``
        status.
        """
        installed: Set[str] = set()
        for pkg in REQUIRED_PACKAGES:
            try:
                result = self._runner.run(
                    ["dpkg-query", "-W", "-f=${Status}", pkg],
                    check=False,
                )
            except LocalCommandError as exc:
                logger.warning("dpkg-query probe failed for %s: %s", pkg, exc)
                continue
            if result.exit_code == 0 and "install ok installed" in result.stdout:
                installed.add(pkg)
        return installed

    def _check_kvm(self) -> bool:
        """Check KVM availability via /dev/kvm presence. (Req 2.3)"""
        return os.path.exists(_KVM_DEVICE)

    def _check_ovmf(self) -> bool:
        """Check UEFI/OVMF firmware via the firmware descriptor. (Req 2.4)"""
        return os.path.exists(_OVMF_FIRMWARE_DESCRIPTOR)


__all__ = [
    "REQUIRED_PACKAGES",
    "PrerequisiteChecker",
    "detect_os_family",
    "compute_missing_packages",
    "parse_os_release",
]
