"""
Advanced tests for tasks_collector.py to improve code coverage.

This test file focuses on covering helper functions and advanced workflows
that aren't covered by the basic comprehensive tests.
"""

import tempfile
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.tasks.collectors.daily_metrics_rollup import daily_metrics_rollup
from apps.tasks.collectors.send_anonymized_to_segment import send_anonymized_to_segment


@pytest.mark.unit
class TestCSVHelperFunctions(TestCase):
    """Test CSV reading helper functions."""

    @patch("apps.tasks.utils.logger")
    def test_csv_to_json_empty_list(self, mock_logger):
        """Test csv_to_json with empty file list."""
        from apps.tasks.utils import csv_to_json

        result = csv_to_json([])
        assert result["records"] == []
        assert result["file_count"] == 0
        assert result["total_records"] == 0

    @patch("apps.tasks.utils.logger")
    def test_csv_to_json_nonexistent_file(self, mock_logger):
        """Test csv_to_json with nonexistent file."""
        from apps.tasks.utils import csv_to_json

        result = csv_to_json(["/nonexistent/file.csv"])
        assert result["file_count"] == 0
        mock_logger.warning.assert_called()

    @patch("apps.tasks.utils.logger")
    def test_csv_to_json_success(self, mock_logger):
        """Test csv_to_json with valid CSV files."""
        from apps.tasks.utils import csv_to_json

        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,value\n")
            f.write("test1,100\n")
            f.write("test2,200\n")
            csv_path = f.name

        try:
            result = csv_to_json([csv_path])
            assert result["file_count"] == 1
            assert result["total_records"] == 2
            assert len(result["records"]) == 2
            assert result["records"][0]["name"] == "test1"
            assert result["records"][0]["value"] == "100"
        finally:
            # File should be deleted by the function, but clean up if it still exists
            import os

            if os.path.exists(csv_path):
                os.remove(csv_path)

    @patch("apps.tasks.utils.logger")
    def test_csv_to_json_error_handling(self, mock_logger):
        """Test csv_to_json error handling."""
        from apps.tasks.utils import csv_to_json

        # Create a file with invalid CSV content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("\x00\x01\x02")  # Invalid content
            csv_path = f.name

        try:
            # Mock open to raise an exception
            with patch("builtins.open", side_effect=Exception("Read error")):
                result = csv_to_json([csv_path])
                assert result["file_count"] == 0
                mock_logger.error.assert_called()
        finally:
            import os

            if os.path.exists(csv_path):
                os.remove(csv_path)


@pytest.mark.unit
@pytest.mark.django_db
class TestHourlyCollectionTasks(TestCase):
    """Test hourly collection tasks."""


@pytest.mark.unit
@pytest.mark.django_db
class TestDailyRollupTask(TestCase):
    """Test daily metrics rollup task."""

    def test_daily_metrics_rollup_no_collections(self):
        """Test daily rollup with no hourly collections."""

        summary_date = date(2024, 1, 15)
        result = daily_metrics_rollup(summary_date=summary_date.isoformat())

        assert result["status"] == "success"
        assert "summary_id" in result
        assert result["hourly_collections_count"] == 0

    def test_daily_metrics_rollup_default_date(self):
        """Test daily rollup with default date (yesterday)."""
        result = daily_metrics_rollup()

        assert result["status"] == "success"
        # Should use yesterday's date
        assert "summary_date" in result


@pytest.mark.unit
@pytest.mark.django_db
class TestAnonymizationTask(TestCase):
    """Test daily anonymization and preparation task."""


@pytest.mark.unit
@pytest.mark.django_db
class TestSegmentSendingTask(TestCase):
    """Test sending anonymized data to Segment."""

    def test_send_to_segment_no_payloads(self):
        """Test sending when no payloads exist."""
        result = send_anonymized_to_segment()

        assert result["status"] == "success"
        assert result["results"]["sent"] == 0
        assert result["total_processed"] == 0

    @patch("apps.tasks.utils.send_to_segment")
    def test_send_to_segment_success(self, mock_send_to_segment):
        """Test successful sending to Segment."""

        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        # Create daily summary and payload
        summary = DailyMetricsSummary.objects.create(
            summary_date=date(2024, 1, 22),
            aggregated_metrics={},
            config_data={},
            status="anonymized",
        )

        payload = AnonymizedMetricsPayload.objects.create(
            summary_date=date(2024, 1, 22),
            anonymized_data={"test": "data"},
            status="pending",
            daily_summary=summary,
        )

        mock_send_to_segment.return_value = "success"

        result = send_anonymized_to_segment()

        assert result["status"] == "success"
        assert result["results"]["sent"] == 1

        # Verify payload status updated
        payload.refresh_from_db()
        assert payload.status == "sent"

    @patch("apps.tasks.utils.send_to_segment")
    def test_send_to_segment_specific_payload(self, mock_send_to_segment):
        """Test sending specific payload by ID."""

        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        summary = DailyMetricsSummary.objects.create(
            summary_date=date(2024, 1, 23), aggregated_metrics={}, config_data={}, status="anonymized"
        )

        payload = AnonymizedMetricsPayload.objects.create(
            summary_date=date(2024, 1, 23), anonymized_data={}, status="pending", daily_summary=summary
        )

        mock_send_to_segment.return_value = "success"

        result = send_anonymized_to_segment(payload_id=payload.id)

        assert result["status"] == "success"
        assert result["results"]["sent"] == 1

    @patch("apps.tasks.utils.send_to_segment")
    def test_send_to_segment_retry_logic(self, mock_send_to_segment):
        """Test retry logic for failed sends."""

        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        summary = DailyMetricsSummary.objects.create(
            summary_date=date(2024, 1, 24), aggregated_metrics={}, config_data={}, status="anonymized"
        )

        # Create payload with retry status
        payload = AnonymizedMetricsPayload.objects.create(
            summary_date=date(2024, 1, 24),
            anonymized_data={},
            status="retry",
            daily_summary=summary,
            retry_count=3,
            max_retries=5,  # Still can retry
        )

        mock_send_to_segment.return_value = "success"

        result = send_anonymized_to_segment()

        assert result["results"]["sent"] == 1
        payload.refresh_from_db()
        assert payload.status == "sent"

    def test_send_to_segment_max_retries_exceeded(self):
        """Test handling when max retries exceeded."""

        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        summary = DailyMetricsSummary.objects.create(
            summary_date=date(2024, 1, 25), aggregated_metrics={}, config_data={}, status="anonymized"
        )

        # Create payload that exceeded retries
        payload = AnonymizedMetricsPayload.objects.create(
            summary_date=date(2024, 1, 25),
            anonymized_data={},
            status="retry",
            daily_summary=summary,
            retry_count=5,
            max_retries=3,  # Already exceeded
        )

        result = send_anonymized_to_segment()

        assert result["results"]["skipped"] == 1
        payload.refresh_from_db()
        assert payload.status == "failed"
        assert "Max retries exceeded" in payload.error_message

    @patch("apps.tasks.collectors.send_anonymized_to_segment.send_to_segment")
    def test_send_to_segment_not_available(self, mock_send_to_segment):
        """Test sending when Segment not available."""

        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        # Mock send_to_segment to return segment_not_available
        mock_send_to_segment.return_value = "segment_not_available"

        summary = DailyMetricsSummary.objects.create(
            summary_date=date(2024, 1, 26), aggregated_metrics={}, config_data={}, status="anonymized"
        )

        payload = AnonymizedMetricsPayload.objects.create(
            summary_date=date(2024, 1, 26), anonymized_data={}, status="pending", daily_summary=summary
        )

        result = send_anonymized_to_segment()

        # When segment not available, it counts as failed (retry status)
        assert result["results"]["failed"] == 1
        payload.refresh_from_db()
        assert payload.status == "retry"
        assert "segment_not_available" in payload.error_message


@pytest.mark.unit
@pytest.mark.django_db
class TestPRFixes(TestCase):
    """Test fixes for PR #79 code review issues."""

    def test_duplicate_payload_prevention(self):
        """Test unique constraint prevents duplicate active payloads (Issue #8)."""

        from django.db import IntegrityError, transaction

        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        summary = DailyMetricsSummary.objects.create(
            summary_date=date(2024, 1, 30), aggregated_metrics={}, config_data={}, status="aggregated"
        )

        # Create first payload with pending status
        AnonymizedMetricsPayload.objects.create(
            summary_date=date(2024, 1, 30),
            anonymized_data={"test": "data1"},
            status="pending",
            daily_summary=summary,
        )

        # Try to create second payload with pending status for same summary
        # Should raise IntegrityError due to unique constraint
        # Use transaction.atomic to prevent transaction errors in tests
        with transaction.atomic(), pytest.raises(IntegrityError):
            AnonymizedMetricsPayload.objects.create(
                summary_date=date(2024, 1, 30),
                anonymized_data={"test": "data2"},
                status="pending",
                daily_summary=summary,
            )

        # Verify only one payload exists
        assert AnonymizedMetricsPayload.objects.filter(daily_summary=summary).count() == 1

    def test_cleanup_all_payload_statuses(self):
        """Test cleanup includes all payload statuses, not just failed (Issue #7)."""

        from apps.tasks.cleanup.cleanup_metrics_data import cleanup_metrics_data
        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        # Create old payloads with different statuses
        old_time = timezone.now() - timedelta(days=35)

        # Create payloads with various statuses (all old enough to be cleaned up)
        # Use separate summaries to avoid unique constraint conflicts
        statuses_to_test = ["failed", "pending", "sending", "retry"]
        for idx, status in enumerate(statuses_to_test):
            # Create a separate summary for each payload
            summary = DailyMetricsSummary.objects.create(
                summary_date=date(2024, 1, 15 + idx), aggregated_metrics={}, config_data={}, status="aggregated"
            )

            payload = AnonymizedMetricsPayload.objects.create(
                summary_date=date(2024, 1, 15 + idx),
                anonymized_data={"test": f"data_{status}"},
                status=status,
                daily_summary=summary,
            )
            # Manually set created time to be old
            payload.created = old_time
            payload.save()

        # Verify 4 payloads exist
        assert AnonymizedMetricsPayload.objects.count() == 4

        # Run cleanup with short retention period to clean up all old payloads
        result = cleanup_metrics_data(
            hourly_retention_days=7, daily_retention_days=30, payload_retention_days=7, dry_run=False
        )

        assert result["status"] == "success"

        # Verify all 4 old payloads were cleaned up (not just "failed")
        # The cleanup should have deleted all statuses
        remaining = AnonymizedMetricsPayload.objects.count()
        assert remaining == 0, f"Expected 0 remaining payloads, got {remaining}"


@pytest.mark.unit
@pytest.mark.django_db
class TestHourlyCollectionRetryBehavior(TestCase):
    """
    Test that hourly collection properly handles retries and duplicate triggers.

    The _collect_hourly_metrics function uses update_or_create to handle cases where:
    1. A failed task is retried and now succeeds
    2. Scheduler double-triggers the same hour
    3. Multiple attempts for the same collection period
    """
