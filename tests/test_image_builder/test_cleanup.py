"""
Tests for the cleanup manager component.

Tests cover:
- Successful cleanup of all resource types
- Retry logic on transient failures
- Failure handling after max retries
- Cleanup ordering (snapshots → instances → floating IPs)
- CleanupReport correctness
- Logging of operations
"""

from unittest.mock import MagicMock, call, patch

import pytest

from proxmox_install_automation.image_builder.cleanup import (
    ImageBuildCleanupManager,
    MAX_RETRIES,
)
from proxmox_install_automation.image_builder.models import (
    CleanupReport,
    CleanupResource,
)


@pytest.fixture
def mock_connection():
    """Create a mock OpenStack connection."""
    conn = MagicMock()
    conn.image.delete_image = MagicMock()
    conn.compute.delete_server = MagicMock()
    conn.network.delete_ip = MagicMock()
    return conn


@pytest.fixture
def cleanup_manager(mock_connection):
    """Create an ImageBuildCleanupManager with a mock connection."""
    return ImageBuildCleanupManager(connection=mock_connection)


class TestCleanupManagerSuccess:
    """Tests for successful cleanup operations."""

    def test_cleanup_snapshot(self, cleanup_manager, mock_connection):
        """Test successful deletion of a snapshot resource."""
        resources = [
            CleanupResource(
                resource_type="snapshot",
                resource_id="snap-123",
                resource_name="test-snapshot",
            )
        ]

        report = cleanup_manager.cleanup(resources)

        mock_connection.image.delete_image.assert_called_once_with("snap-123")
        assert report.total == 1
        assert report.succeeded == 1
        assert report.failed == 0
        assert report.failures == []

    def test_cleanup_instance(self, cleanup_manager, mock_connection):
        """Test successful deletion of an instance resource."""
        resources = [
            CleanupResource(
                resource_type="instance",
                resource_id="srv-456",
                resource_name="proxmox-installer-1234567890",
            )
        ]

        report = cleanup_manager.cleanup(resources)

        mock_connection.compute.delete_server.assert_called_once_with("srv-456")
        assert report.total == 1
        assert report.succeeded == 1
        assert report.failed == 0

    def test_cleanup_floating_ip(self, cleanup_manager, mock_connection):
        """Test successful deletion of a floating IP resource."""
        resources = [
            CleanupResource(
                resource_type="floating_ip",
                resource_id="fip-789",
                resource_name="192.168.1.100",
            )
        ]

        report = cleanup_manager.cleanup(resources)

        mock_connection.network.delete_ip.assert_called_once_with("fip-789")
        assert report.total == 1
        assert report.succeeded == 1
        assert report.failed == 0

    def test_cleanup_all_resource_types(self, cleanup_manager, mock_connection):
        """Test successful cleanup of all three resource types."""
        resources = [
            CleanupResource("snapshot", "snap-1", "my-snapshot"),
            CleanupResource("instance", "srv-1", "my-server"),
            CleanupResource("floating_ip", "fip-1", "10.0.0.1"),
        ]

        report = cleanup_manager.cleanup(resources)

        mock_connection.image.delete_image.assert_called_once_with("snap-1")
        mock_connection.compute.delete_server.assert_called_once_with("srv-1")
        mock_connection.network.delete_ip.assert_called_once_with("fip-1")
        assert report.total == 3
        assert report.succeeded == 3
        assert report.failed == 0

    def test_cleanup_empty_list(self, cleanup_manager):
        """Test cleanup with no resources returns empty report."""
        report = cleanup_manager.cleanup([])

        assert report.total == 0
        assert report.succeeded == 0
        assert report.failed == 0
        assert report.failures == []


class TestCleanupOrdering:
    """Tests for resource cleanup ordering."""

    def test_cleanup_order_snapshots_first(self, cleanup_manager, mock_connection):
        """Test resources are cleaned in order: snapshots → instances → floating IPs."""
        call_order = []
        mock_connection.image.delete_image.side_effect = (
            lambda _id: call_order.append(("snapshot", _id))
        )
        mock_connection.compute.delete_server.side_effect = (
            lambda _id: call_order.append(("instance", _id))
        )
        mock_connection.network.delete_ip.side_effect = (
            lambda _id: call_order.append(("floating_ip", _id))
        )

        # Provide resources in mixed order
        resources = [
            CleanupResource("floating_ip", "fip-1"),
            CleanupResource("instance", "srv-1"),
            CleanupResource("snapshot", "snap-1"),
        ]

        cleanup_manager.cleanup(resources)

        assert call_order == [
            ("snapshot", "snap-1"),
            ("instance", "srv-1"),
            ("floating_ip", "fip-1"),
        ]

    def test_cleanup_multiple_same_type_preserves_input_order(
        self, cleanup_manager, mock_connection
    ):
        """Test that resources of the same type maintain their relative order."""
        call_order = []
        mock_connection.image.delete_image.side_effect = (
            lambda _id: call_order.append(_id)
        )

        resources = [
            CleanupResource("snapshot", "snap-1"),
            CleanupResource("snapshot", "snap-2"),
            CleanupResource("snapshot", "snap-3"),
        ]

        cleanup_manager.cleanup(resources)

        assert call_order == ["snap-1", "snap-2", "snap-3"]


class TestCleanupRetryLogic:
    """Tests for retry behavior on failures."""

    @patch("proxmox_install_automation.image_builder.cleanup.time.sleep")
    def test_retry_on_failure_then_succeed(
        self, mock_sleep, cleanup_manager, mock_connection
    ):
        """Test resource is destroyed after retries on transient failure."""
        mock_connection.image.delete_image.side_effect = [
            Exception("Connection timeout"),
            None,  # Success on second attempt
        ]

        resources = [CleanupResource("snapshot", "snap-1")]
        report = cleanup_manager.cleanup(resources)

        assert report.succeeded == 1
        assert report.failed == 0
        assert mock_connection.image.delete_image.call_count == 2
        mock_sleep.assert_called_once()

    @patch("proxmox_install_automation.image_builder.cleanup.time.sleep")
    def test_max_retries_then_failure(
        self, mock_sleep, cleanup_manager, mock_connection
    ):
        """Test resource reports failure after exhausting all retries."""
        mock_connection.compute.delete_server.side_effect = Exception("API unavailable")

        resources = [CleanupResource("instance", "srv-1", "my-server")]
        report = cleanup_manager.cleanup(resources)

        assert report.succeeded == 0
        assert report.failed == 1
        assert len(report.failures) == 1
        assert "instance" in report.failures[0]
        assert "srv-1" in report.failures[0]
        assert mock_connection.compute.delete_server.call_count == MAX_RETRIES

    @patch("proxmox_install_automation.image_builder.cleanup.time.sleep")
    def test_failure_continues_to_next_resource(
        self, mock_sleep, cleanup_manager, mock_connection
    ):
        """Test that failure of one resource doesn't prevent cleanup of others."""
        mock_connection.image.delete_image.side_effect = Exception("Permanent failure")
        # Instance deletion succeeds
        mock_connection.compute.delete_server.return_value = None

        resources = [
            CleanupResource("snapshot", "snap-1"),
            CleanupResource("instance", "srv-1"),
        ]
        report = cleanup_manager.cleanup(resources)

        assert report.total == 2
        assert report.succeeded == 1
        assert report.failed == 1
        # Both resources were attempted
        assert mock_connection.image.delete_image.call_count == MAX_RETRIES
        mock_connection.compute.delete_server.assert_called_once_with("srv-1")

    @patch("proxmox_install_automation.image_builder.cleanup.time.sleep")
    def test_retry_succeeds_on_last_attempt(
        self, mock_sleep, cleanup_manager, mock_connection
    ):
        """Test resource succeeds when it passes on the last retry attempt."""
        mock_connection.network.delete_ip.side_effect = [
            Exception("Timeout"),
            Exception("Timeout"),
            None,  # Success on 3rd (final) attempt
        ]

        resources = [CleanupResource("floating_ip", "fip-1")]
        report = cleanup_manager.cleanup(resources)

        assert report.succeeded == 1
        assert report.failed == 0
        assert mock_connection.network.delete_ip.call_count == 3


class TestCleanupReport:
    """Tests for CleanupReport generation."""

    @patch("proxmox_install_automation.image_builder.cleanup.time.sleep")
    def test_report_counts_mixed_results(
        self, mock_sleep, cleanup_manager, mock_connection
    ):
        """Test report correctly counts mixed success/failure results."""
        mock_connection.image.delete_image.return_value = None  # success
        mock_connection.compute.delete_server.side_effect = Exception("fail")
        mock_connection.network.delete_ip.return_value = None  # success

        resources = [
            CleanupResource("snapshot", "snap-1"),
            CleanupResource("instance", "srv-1"),
            CleanupResource("floating_ip", "fip-1"),
        ]
        report = cleanup_manager.cleanup(resources)

        assert report.total == 3
        assert report.succeeded == 2
        assert report.failed == 1
        assert len(report.failures) == 1

    def test_report_with_resource_without_name(self, cleanup_manager, mock_connection):
        """Test cleanup works with resources that have no name set."""
        mock_connection.image.delete_image.return_value = None

        resources = [CleanupResource("snapshot", "snap-no-name")]
        report = cleanup_manager.cleanup(resources)

        assert report.succeeded == 1
        mock_connection.image.delete_image.assert_called_once_with("snap-no-name")
