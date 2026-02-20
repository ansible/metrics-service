"""
Advanced tests for tasks_collector.py to improve code coverage.

This test file focuses on covering helper functions and advanced workflows
that aren't covered by the basic comprehensive tests.
"""

from datetime import UTC, date, timedelta
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.tasks.collectors.daily_metrics_rollup import daily_metrics_rollup
from apps.tasks.collectors.send_anonymized_to_segment import send_anonymized_to_segment


@pytest.mark.unit
@pytest.mark.django_db
class TestHourlyCollectionTasks(TestCase):
    """Test hourly collection tasks."""

    @patch("apps.tasks.collectors.collect_hourly_metrics.generic_collect_metrics")
    @patch("apps.tasks.collectors.collect_hourly_metrics.get_db_connection")
    def test_collect_hourly_metrics_with_since_until(self, mock_db_conn, mock_collect):
        """Test collect_hourly_metrics with custom since/until timestamps."""
        from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

        mock_collect.return_value = {"status": "success", "record_id": 123}

        result = collect_hourly_metrics(
            collector_type="job_host_summary_service",
            since="2024-01-15T10:00:00Z",
            until="2024-01-15T11:00:00Z",
        )

        assert result["status"] == "success"
        # Verify generic_collect_metrics was called with the correct time window
        call_args = mock_collect.call_args
        assert call_args.kwargs["collector_kwargs"]["since"].hour == 10
        assert call_args.kwargs["collector_kwargs"]["until"].hour == 11

    @patch("apps.tasks.collectors.collect_hourly_metrics.generic_collect_metrics")
    @patch("apps.tasks.collectors.collect_hourly_metrics.get_db_connection")
    def test_collect_hourly_metrics_default_time_window(self, mock_db_conn, mock_collect):
        """Test collect_hourly_metrics defaults to previous hour when no timestamps provided."""
        from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

        mock_collect.return_value = {"status": "success", "record_id": 123}

        with patch("apps.tasks.collectors.collect_hourly_metrics.timezone") as mock_tz:
            # Mock current time as 2024-01-15 15:30:45
            mock_now = timezone.datetime(2024, 1, 15, 15, 30, 45, tzinfo=UTC)
            mock_tz.now.return_value = mock_now

            result = collect_hourly_metrics(collector_type="unified_jobs")

            assert result["status"] == "success"
            # Should default to 14:00 - 15:00 (previous hour)
            call_args = mock_collect.call_args
            assert call_args.kwargs["collector_kwargs"]["since"].hour == 14
            assert call_args.kwargs["collector_kwargs"]["until"].hour == 15

    def test_collect_hourly_metrics_requires_both_since_and_until(self):
        """Test that since and until must both be provided or neither."""
        from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

        # Test only since provided
        result = collect_hourly_metrics(
            collector_type="unified_jobs",
            since="2024-01-15T10:00:00Z",
        )
        assert result["status"] == "error"
        assert "Both 'since' and 'until' must be provided together" in result["error"]

        # Test only until provided
        result = collect_hourly_metrics(
            collector_type="unified_jobs",
            until="2024-01-15T11:00:00Z",
        )
        assert result["status"] == "error"
        assert "Both 'since' and 'until' must be provided together" in result["error"]

    def test_collect_hourly_metrics_validates_since_before_until(self):
        """Test that since must be before until."""
        from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

        # Test until before since
        result = collect_hourly_metrics(
            collector_type="unified_jobs",
            since="2024-01-15T11:00:00Z",
            until="2024-01-15T10:00:00Z",
        )
        assert result["status"] == "error"
        assert "'since'" in result["error"] and "must be before 'until'" in result["error"]

        # Test equal times
        result = collect_hourly_metrics(
            collector_type="unified_jobs",
            since="2024-01-15T10:00:00Z",
            until="2024-01-15T10:00:00Z",
        )
        assert result["status"] == "error"
        assert "'since'" in result["error"] and "must be before 'until'" in result["error"]

    def test_collect_hourly_metrics_invalid_since_format(self):
        """Test error handling for invalid since timestamp format."""
        from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

        result = collect_hourly_metrics(
            collector_type="unified_jobs",
            since="not-a-date",
            until="2024-01-15T11:00:00Z",
        )
        assert result["status"] == "error"
        assert "Invalid 'since' timestamp format" in result["error"]

    def test_collect_hourly_metrics_invalid_until_format(self):
        """Test error handling for invalid until timestamp format."""
        from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

        result = collect_hourly_metrics(
            collector_type="unified_jobs",
            since="2024-01-15T10:00:00Z",
            until="not-a-date",
        )
        assert result["status"] == "error"
        assert "Invalid 'until' timestamp format" in result["error"]

    def test_collect_hourly_metrics_requires_collector_type(self):
        """Test that collector_type is required."""
        from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

        result = collect_hourly_metrics()
        assert result["status"] == "error"
        assert "collector_type parameter is required" in result["error"]

    @patch("apps.tasks.collectors.collect_hourly_metrics.generic_collect_metrics")
    @patch("apps.tasks.collectors.collect_hourly_metrics.get_db_connection")
    def test_collect_hourly_metrics_with_execution_id(self, mock_db_conn, mock_collect):
        """Test collect_hourly_metrics passes execution_id to generic_collect_metrics."""
        from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics

        mock_collect.return_value = {"status": "success", "record_id": 123}

        result = collect_hourly_metrics(
            collector_type="credentials_service",
            since="2024-01-15T10:00:00Z",
            until="2024-01-15T11:00:00Z",
            execution_id=456,
        )

        assert result["status"] == "success"
        # Verify execution_id was passed to generic_collect_metrics
        call_args = mock_collect.call_args
        assert call_args.kwargs["task_execution_id"] == 456


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

    The generic_collect_metrics function uses update_or_create to handle cases where:
    1. A failed task is retried and now succeeds
    2. Scheduler double-triggers the same hour
    3. Multiple attempts for the same collection period
    4. Re-collection after a record was already processed by daily rollup
    """

    def test_resets_processed_status_on_update(self):
        """
        Verify that re-collecting a processed record resets its status to 'collected'.

        Scenario: A collection was already processed by daily rollup (status='processed')
        and the collector runs again for the same timestamp (e.g., manual re-run or retry).
        The update should reset status to 'collected' so the new data is picked up by
        the next daily rollup.
        """
        from datetime import datetime
        from unittest.mock import MagicMock, patch

        from apps.tasks.models import HourlyMetricsCollection
        from apps.tasks.utils import generic_collect_metrics

        # Create initial collection that was already processed by rollup
        collection_timestamp = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        HourlyMetricsCollection.objects.create(
            collector_type="unified_jobs",
            collection_timestamp=collection_timestamp,
            raw_data={"old": "data"},
            status="processed",  # Already processed by previous rollup
            error_message="",
        )

        # Mock the collector and database connection
        mock_collector = MagicMock()
        mock_collector.gather.return_value = {"new": "data"}
        mock_db = MagicMock()

        # Mock collector registry with a simple collector
        collector_registry = {
            "unified_jobs": {
                "collector_func": lambda db: mock_collector,
                "rollup_processor": None,  # No processor for this test
            }
        }

        # Re-collect the same timestamp
        with patch("apps.tasks.utils.get_db_connection", return_value=mock_db):
            result = generic_collect_metrics(
                collector_type="unified_jobs",
                collector_registry=collector_registry,
                collection_mode="hourly",
                timestamp=collection_timestamp,
                db_connection=mock_db,
            )

        # Verify the result indicates update
        assert result["status"] == "success"
        assert "Updated" in result["message"]

        # Verify the collection was updated and status was reset to 'collected'
        collection = HourlyMetricsCollection.objects.get(
            collector_type="unified_jobs", collection_timestamp=collection_timestamp
        )
        assert collection.status == "collected", "Status should be reset to 'collected' after re-collection"
        assert collection.error_message == "", "Error message should be cleared"
        assert collection.raw_data == {"new": "data"}, "Data should be updated"

    def test_creates_with_collected_status_on_first_run(self):
        """
        Verify that first-time collection creates record with status='collected'.
        """
        from datetime import datetime
        from unittest.mock import MagicMock, patch

        from apps.tasks.models import HourlyMetricsCollection
        from apps.tasks.utils import generic_collect_metrics

        collection_timestamp = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

        # Mock the collector and database connection
        mock_collector = MagicMock()
        mock_collector.gather.return_value = {"new": "data"}
        mock_db = MagicMock()

        # Mock collector registry
        collector_registry = {
            "unified_jobs": {
                "collector_func": lambda db: mock_collector,
                "rollup_processor": None,
            }
        }

        # Collect for the first time
        with patch("apps.tasks.utils.get_db_connection", return_value=mock_db):
            result = generic_collect_metrics(
                collector_type="unified_jobs",
                collector_registry=collector_registry,
                collection_mode="hourly",
                timestamp=collection_timestamp,
                db_connection=mock_db,
            )

        # Verify the result indicates creation
        assert result["status"] == "success"
        assert "Created" in result["message"]

        # Verify the collection was created with correct status
        collection = HourlyMetricsCollection.objects.get(
            collector_type="unified_jobs", collection_timestamp=collection_timestamp
        )
        assert collection.status == "collected", "New collection should have status='collected'"
        assert collection.error_message == ""
        assert collection.raw_data == {"new": "data"}
