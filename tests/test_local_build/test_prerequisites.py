"""
Tests for the PrerequisiteChecker component (local_build, Requirement 2).

Covers three task-list items for the proxmox-qcow2-opcp-deployment spec:

- Task 3.2 / Property 2: OS family detection correctness (Req 2.1).
  detect_os_family returns True iff the parsed ID / ID_LIKE indicate a
  Debian/Ubuntu lineage, checked against an independent oracle.

- Task 3.3 / Property 3: Missing-package computation correctness (Req 2.2, 2.5).
  compute_missing_packages returns exactly the REQUIRED_PACKAGES absent from the
  installed set, and the emptiness of that result corresponds to package-ok.

- Task 3.4: Unit tests for PrerequisiteChecker.check (Req 2.3, 2.4, 2.5).
  The injected LocalCommandRunner (dpkg-query) and the filesystem probes
  (os.path.exists / open on /etc/os-release) are mocked to exercise the
  missing-package, missing-KVM, and missing-OVMF paths and assert the report
  fields plus report.ok.
"""

from unittest import mock

import pytest
from hypothesis import given, settings, strategies as st

from proxmox_install_automation.local_build.models import CommandResult
from proxmox_install_automation.local_build.prerequisites import (
    REQUIRED_PACKAGES,
    PrerequisiteChecker,
    compute_missing_packages,
    detect_os_family,
)

# Module path used when patching the filesystem probes that check() performs.
_PREREQ_MODULE = "proxmox_install_automation.local_build.prerequisites"

# Tokens that, as ID or inside ID_LIKE, indicate a Debian/Ubuntu lineage.
_DEBIAN_TOKENS = ("debian", "ubuntu", "Debian", "UBUNTU", "Ubuntu")
# Tokens outside the Debian/Ubuntu lineage.
_NON_DEBIAN_TOKENS = (
    "fedora",
    "rhel",
    "centos",
    "arch",
    "suse",
    "alpine",
    "gentoo",
    "void",
)


def _oracle_is_debian_family(os_release):
    """Independent oracle: does ID or ID_LIKE indicate debian/ubuntu lineage?

    Deliberately re-derived from the Req 2.1 statement rather than reusing the
    production helper's internals, so the property compares two independent
    implementations.
    """
    lineage = {"debian", "ubuntu"}
    identifiers = set()

    primary = os_release.get("ID")
    if primary:
        identifiers.add(primary.strip().lower())

    id_like = os_release.get("ID_LIKE")
    if id_like:
        for token in id_like.split():
            if token:
                identifiers.add(token.lower())

    return len(identifiers & lineage) > 0


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# A single os-release identifier token: a mix of debian/ubuntu and non-debian
# values, plus arbitrary free-form tokens to probe the detector's boundaries.
_id_tokens = st.one_of(
    st.sampled_from(_DEBIAN_TOKENS),
    st.sampled_from(_NON_DEBIAN_TOKENS),
    st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu")), min_size=1, max_size=8),
)


@st.composite
def _os_release_dicts(draw):
    """Generate os-release dicts with optional ID and ID_LIKE fields.

    ID is a single token; ID_LIKE is a space-separated list of tokens. Either
    key may be absent to exercise the detector's handling of missing fields.
    """
    os_release = {}

    if draw(st.booleans()):
        os_release["ID"] = draw(_id_tokens)

    if draw(st.booleans()):
        tokens = draw(st.lists(_id_tokens, min_size=0, max_size=4))
        os_release["ID_LIKE"] = " ".join(tokens)

    # Occasionally include unrelated keys that must not influence the result.
    if draw(st.booleans()):
        os_release["PRETTY_NAME"] = draw(st.text(max_size=12))
        os_release["VERSION_ID"] = draw(st.text(max_size=6))

    return os_release


# ---------------------------------------------------------------------------
# Task 3.2 / Property 2: OS family detection correctness (Req 2.1)
# ---------------------------------------------------------------------------


class TestOSFamilyDetectionProperty:
    """Property 2: detect_os_family agrees with an independent oracle."""

    # Feature: proxmox-qcow2-opcp-deployment, Property 2
    @settings(max_examples=100)
    @given(os_release=_os_release_dicts())
    def test_detect_os_family_matches_oracle(self, os_release):
        """Validates: Requirements 2.1

        For any /etc/os-release content, detect_os_family returns True iff the
        parsed ID or ID_LIKE indicates a Debian/Ubuntu lineage.
        """
        assert detect_os_family(os_release) == _oracle_is_debian_family(os_release)


# ---------------------------------------------------------------------------
# Task 3.3 / Property 3: Missing-package computation correctness (Req 2.2, 2.5)
# ---------------------------------------------------------------------------


class TestMissingPackageComputationProperty:
    """Property 3: compute_missing_packages returns exactly the absent set."""

    # Feature: proxmox-qcow2-opcp-deployment, Property 3
    @settings(max_examples=100)
    @given(
        installed=st.sets(
            st.one_of(
                st.sampled_from(REQUIRED_PACKAGES),
                st.text(min_size=1, max_size=10),
            ),
            max_size=12,
        )
    )
    def test_missing_is_exactly_the_absent_required_packages(self, installed):
        """Validates: Requirements 2.2, 2.5

        compute_missing_packages returns exactly the REQUIRED_PACKAGES absent
        from `installed` (order preserved), and the emptiness of that result
        corresponds to package-ok (every required package present).
        """
        missing = compute_missing_packages(installed)

        # Oracle: the required packages not in `installed`, canonical order.
        expected = [pkg for pkg in REQUIRED_PACKAGES if pkg not in installed]
        assert missing == expected

        # The result is a subset of the required packages only.
        assert set(missing) <= set(REQUIRED_PACKAGES)
        # None of the returned packages are actually installed.
        assert all(pkg not in installed for pkg in missing)

        # Emptiness corresponds to package-ok: all required packages present.
        package_ok = set(REQUIRED_PACKAGES) <= set(installed)
        assert (len(missing) == 0) == package_ok


# ---------------------------------------------------------------------------
# Task 3.4: Unit tests for PrerequisiteChecker.check (Req 2.3, 2.4, 2.5)
# ---------------------------------------------------------------------------

# A valid Debian os-release file used by the "happy path" and single-failure
# scenarios so that only the probe under test flips report.ok to False.
_DEBIAN_OS_RELEASE = 'ID=debian\nID_LIKE=debian\nPRETTY_NAME="Debian GNU/Linux 12"\n'


def _dpkg_result(pkg, installed):
    """Build a CommandResult mimicking dpkg-query for one package probe."""
    if installed:
        return CommandResult(
            argv=["dpkg-query", "-W", "-f=${Status}", pkg],
            exit_code=0,
            stdout="install ok installed",
            stderr="",
        )
    return CommandResult(
        argv=["dpkg-query", "-W", "-f=${Status}", pkg],
        exit_code=1,
        stdout="",
        stderr=f"dpkg-query: no packages found matching {pkg}",
    )


def _make_runner(installed_packages):
    """Create a mock LocalCommandRunner whose dpkg-query probes report the
    given set of packages as installed and all others as absent.
    """
    installed_packages = set(installed_packages)

    def _run(argv, check=False, timeout=None):
        pkg = argv[-1]
        return _dpkg_result(pkg, pkg in installed_packages)

    runner = mock.Mock()
    runner.run.side_effect = _run
    return runner


class TestCheck:
    """PrerequisiteChecker.check aggregates OS, package, KVM, and OVMF probes."""

    def _run_check(self, installed_packages, os_release, kvm, ovmf):
        """Drive check() with fully mocked filesystem probes and runner.

        os.path.exists is patched to answer the /dev/kvm and OVMF descriptor
        probes independently; open() is patched to feed os-release content.
        """
        runner = _make_runner(installed_packages)
        checker = PrerequisiteChecker(runner)

        def _exists(path):
            if path == "/dev/kvm":
                return kvm
            if path.endswith("OVMF_CODE.fd"):
                return ovmf
            return False

        m_open = mock.mock_open(read_data=os_release)
        with mock.patch(f"{_PREREQ_MODULE}.os.path.exists", side_effect=_exists), \
                mock.patch(f"{_PREREQ_MODULE}.open", m_open, create=True):
            report = checker.check()
        return report, runner

    def test_all_prerequisites_satisfied(self):
        report, runner = self._run_check(
            installed_packages=REQUIRED_PACKAGES,
            os_release=_DEBIAN_OS_RELEASE,
            kvm=True,
            ovmf=True,
        )

        assert report.os_supported is True
        assert report.missing_packages == []
        assert report.kvm_available is True
        assert report.uefi_available is True
        assert report.ok is True
        # Every required package is probed exactly once.
        assert runner.run.call_count == len(REQUIRED_PACKAGES)

    def test_missing_package_path(self):
        # ovmf is present and kvm available; only one package is absent.
        present = [pkg for pkg in REQUIRED_PACKAGES if pkg != "virtinst"]
        report, _ = self._run_check(
            installed_packages=present,
            os_release=_DEBIAN_OS_RELEASE,
            kvm=True,
            ovmf=True,
        )

        assert report.missing_packages == ["virtinst"]
        assert report.os_supported is True
        assert report.kvm_available is True
        assert report.uefi_available is True
        assert report.ok is False

    def test_multiple_missing_packages_preserve_canonical_order(self):
        present = {"qemu-utils", "libvirt-clients"}
        report, _ = self._run_check(
            installed_packages=present,
            os_release=_DEBIAN_OS_RELEASE,
            kvm=True,
            ovmf=True,
        )

        expected = [pkg for pkg in REQUIRED_PACKAGES if pkg not in present]
        assert report.missing_packages == expected
        assert report.ok is False

    def test_missing_kvm_path(self):
        report, _ = self._run_check(
            installed_packages=REQUIRED_PACKAGES,
            os_release=_DEBIAN_OS_RELEASE,
            kvm=False,
            ovmf=True,
        )

        assert report.kvm_available is False
        assert report.missing_packages == []
        assert report.os_supported is True
        assert report.uefi_available is True
        assert report.ok is False

    def test_missing_ovmf_path(self):
        report, _ = self._run_check(
            installed_packages=REQUIRED_PACKAGES,
            os_release=_DEBIAN_OS_RELEASE,
            kvm=True,
            ovmf=False,
        )

        assert report.uefi_available is False
        assert report.missing_packages == []
        assert report.os_supported is True
        assert report.kvm_available is True
        assert report.ok is False

    def test_unsupported_os_path(self):
        report, _ = self._run_check(
            installed_packages=REQUIRED_PACKAGES,
            os_release="ID=fedora\nID_LIKE=rhel\n",
            kvm=True,
            ovmf=True,
        )

        assert report.os_supported is False
        assert report.ok is False

    def test_os_release_unreadable_marks_os_unsupported(self):
        # When /etc/os-release cannot be opened, the OS is treated as
        # unsupported rather than raising. (Req 2.1)
        runner = _make_runner(REQUIRED_PACKAGES)
        checker = PrerequisiteChecker(runner)

        with mock.patch(f"{_PREREQ_MODULE}.os.path.exists", return_value=True), \
                mock.patch(
                    f"{_PREREQ_MODULE}.open",
                    side_effect=OSError("no such file"),
                    create=True,
                ):
            report = checker.check()

        assert report.os_supported is False
        assert report.ok is False
