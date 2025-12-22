"""
Advanced tests for tasks_collector.py to improve code coverage.

This test file focuses on covering helper functions and advanced workflows
that aren't covered by the basic comprehensive tests.
"""

import tempfile
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.tasks.tasks_collector import (
    collect_host_metrics_hourly,
    collect_job_host_summary_hourly,
    collect_main_host_hourly,
    daily_anonymize_and_prepare,
    daily_metrics_rollup,
    send_anonymized_to_segment,
)


@pytest.mark.unit
class TestCSVHelperFunctions(TestCase):
    """Test CSV reading helper functions."""

    @patch("apps.tasks.tasks_collector.logger")
    def test_csv_to_json_empty_list(self, mock_logger):
        """Test _csv_to_json with empty file list."""
        from apps.tasks.tasks_collector import _csv_to_json

        result = _csv_to_json([])
        assert result["records"] == []
        assert result["file_count"] == 0
        assert result["total_records"] == 0

    @patch("apps.tasks.tasks_collector.logger")
    def test_csv_to_json_nonexistent_file(self, mock_logger):
        """Test _csv_to_json with nonexistent file."""
        from apps.tasks.tasks_collector import _csv_to_json

        result = _csv_to_json(["/nonexistent/file.csv"])
        assert result["file_count"] == 0
        mock_logger.warning.assert_called()

    @patch("apps.tasks.tasks_collector.logger")
    def test_csv_to_json_success(self, mock_logger):
        """Test _csv_to_json with valid CSV files."""
        from apps.tasks.tasks_collector import _csv_to_json

        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,value\n")
            f.write("test1,100\n")
            f.write("test2,200\n")
            csv_path = f.name

        try:
            result = _csv_to_json([csv_path])
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

    @patch("apps.tasks.tasks_collector.logger")
    def test_csv_to_json_error_handling(self, mock_logger):
        """Test _csv_to_json error handling."""
        from apps.tasks.tasks_collector import _csv_to_json

        # Create a file with invalid CSV content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("\x00\x01\x02")  # Invalid content
            csv_path = f.name

        try:
            # Mock open to raise an exception
            with patch("builtins.open", side_effect=Exception("Read error")):
                result = _csv_to_json([csv_path])
                assert result["file_count"] == 0
                mock_logger.error.assert_called()
        finally:
            import os

            if os.path.exists(csv_path):
                os.remove(csv_path)


@pytest.mark.unit
class TestAggregationHelpers(TestCase):
    """Test aggregation helper functions."""

    def test_aggregate_collector_data_empty(self):
        """Test _aggregate_collector_data with empty collections."""
        from apps.tasks.tasks_collector import _aggregate_collector_data

        result = _aggregate_collector_data([])
        assert result["total_records"] == 0
        assert result["hourly_snapshots"] == []

    def test_aggregate_collector_data_with_dict_data(self):
        """Test _aggregate_collector_data with dict data."""
        from apps.tasks.tasks_collector import _aggregate_collector_data

        # Create mock collections
        collection1 = Mock()
        collection1.raw_data = {"total_records": 5, "data": "test"}
        collection1.collection_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        collection1.id = 1

        collection2 = Mock()
        collection2.raw_data = {"total_records": 3}
        collection2.collection_timestamp = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)
        collection2.id = 2

        result = _aggregate_collector_data([collection1, collection2])
        assert result["total_records"] == 8
        assert len(result["hourly_snapshots"]) == 2
        assert result["hourly_snapshots"][0]["hour"] == 12
        assert result["hourly_snapshots"][0]["record_count"] == 5
        assert result["hourly_snapshots"][1]["hour"] == 13

    def test_aggregate_collector_data_with_list_data(self):
        """Test _aggregate_collector_data with list data."""
        from apps.tasks.tasks_collector import _aggregate_collector_data

        collection = Mock()
        collection.raw_data = [{"item": 1}, {"item": 2}, {"item": 3}]
        collection.collection_timestamp = datetime(2024, 1, 1, 14, 0, 0, tzinfo=UTC)
        collection.id = 3

        result = _aggregate_collector_data([collection])
        assert result["total_records"] == 3

    def test_aggregate_collector_data_with_other_data(self):
        """Test _aggregate_collector_data with non-dict/list data."""
        from apps.tasks.tasks_collector import _aggregate_collector_data

        collection = Mock()
        collection.raw_data = "some string"
        collection.collection_timestamp = datetime(2024, 1, 1, 15, 0, 0, tzinfo=UTC)
        collection.id = 4

        result = _aggregate_collector_data([collection])
        assert result["total_records"] == 1


@pytest.mark.unit
class TestAnonymizationHelpers(TestCase):
    """Test anonymization helper functions."""

    def test_is_sensitive_field(self):
        """Test _is_sensitive_field detection."""
        from apps.tasks.tasks_collector import _is_sensitive_field

        assert _is_sensitive_field("username")
        assert _is_sensitive_field("email")
        assert _is_sensitive_field("hostname")
        assert _is_sensitive_field("ip_address")
        assert _is_sensitive_field("host")
        assert _is_sensitive_field("user_name")  # Contains 'name'
        assert not _is_sensitive_field("count")
        assert not _is_sensitive_field("id")
        assert not _is_sensitive_field("status")

    def test_anonymize_dict_basic(self):
        """Test _anonymize_dict with basic data."""
        from apps.tasks.tasks_collector import _anonymize_dict

        data = {
            "username": "alice",
            "count": 42,
            "status": "active",
        }

        result = _anonymize_dict(data, "test-salt")
        assert "username" in result
        assert result["username"] != "alice"  # Should be hashed
        assert len(result["username"]) == 16  # Hash truncated to 16 chars
        assert result["count"] == 42  # Not anonymized
        assert result["status"] == "active"  # Not anonymized

    def test_anonymize_dict_nested(self):
        """Test _anonymize_dict with nested structures."""
        from apps.tasks.tasks_collector import _anonymize_dict

        data = {
            "user": {
                "name": "bob",
                "count": 10,
            },
            "hosts": [{"hostname": "server1"}, {"hostname": "server2"}],
        }

        result = _anonymize_dict(data, "test-salt")
        assert isinstance(result["user"], dict)
        assert result["user"]["name"] != "bob"
        assert result["user"]["count"] == 10
        assert isinstance(result["hosts"], list)
        assert result["hosts"][0]["hostname"] != "server1"

    def test_anonymize_dict_structural_fields(self):
        """Test _anonymize_dict preserves structural fields."""
        from apps.tasks.tasks_collector import _anonymize_dict

        data = {
            "hourly_snapshots": [{"hour": 0}, {"hour": 1}],
            "collection_id": 123,
            "total_records": 456,
            "username": "test",
        }

        result = _anonymize_dict(data, "salt")
        # Structural fields preserved
        assert result["hourly_snapshots"] == data["hourly_snapshots"]
        assert result["collection_id"] == 123
        assert result["total_records"] == 456
        # Sensitive field anonymized
        assert result["username"] != "test"

    def test_anonymize_daily_summary(self):
        """Test _anonymize_daily_summary."""
        from apps.tasks.tasks_collector import _anonymize_daily_summary

        aggregated_metrics = {
            "job_host_summary": {"total": 100},
            "main_jobevent": {"total": 200},
            "main_host": {"total": 50},
        }
        config_data = {"version": "4.5.0"}

        result = _anonymize_daily_summary(aggregated_metrics, config_data, "salt")
        assert "job_host_summary" in result
        assert "main_jobevent" in result
        assert "main_host" in result
        assert "config" in result
        assert result["config"] == {"version": "4.5.0"}


@pytest.mark.unit
@pytest.mark.django_db
class TestHourlyCollectionTasks(TestCase):
    """Test hourly collection tasks."""

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_job_host_summary_hourly_utility_unavailable(self):
        """Test hourly collection when metrics-utility not available."""
        result = collect_job_host_summary_hourly()
        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.job_host_summary")
    @patch("apps.tasks.tasks_collector._get_db_connection")
    @patch("apps.tasks.tasks_collector._csv_to_json")
    def test_collect_job_host_summary_hourly_success(self, mock_csv_to_json, mock_get_db, mock_job_host_summary):
        """Test successful hourly job_host_summary collection."""
        from apps.tasks.models import HourlyMetricsCollection

        # Setup mocks
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_collector = MagicMock()
        mock_collector.gather.return_value = [f"{tempfile.gettempdir()}/test.csv"]
        mock_job_host_summary.return_value = mock_collector

        mock_csv_to_json.return_value = {"records": [{"job": 1}], "total_records": 1, "file_count": 1}

        # Run task
        result = collect_job_host_summary_hourly()

        # Verify
        assert result["status"] == "success"
        assert result["task_type"] == "collect_job_host_summary_hourly"
        assert "collection_id" in result
        assert result["records_collected"] == 1

        # Check database record created
        collection = HourlyMetricsCollection.objects.get(id=result["collection_id"])
        assert collection.collector_type == "job_host_summary"
        assert collection.status == "collected"

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.main_jobevent")
    @patch("apps.tasks.tasks_collector._get_db_connection")
    @patch("apps.tasks.tasks_collector._csv_to_json")
    def test_collect_host_metrics_hourly_success(self, mock_csv_to_json, mock_get_db, mock_main_jobevent):
        """Test successful hourly main_jobevent collection."""

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_collector = MagicMock()
        mock_collector.gather.return_value = [f"{tempfile.gettempdir()}/test.csv"]
        mock_main_jobevent.return_value = mock_collector

        mock_csv_to_json.return_value = {"records": [], "total_records": 0, "file_count": 0}

        result = collect_host_metrics_hourly()

        assert result["status"] == "success"
        assert "collection_id" in result

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.main_host")
    @patch("apps.tasks.tasks_collector._get_db_connection")
    @patch("apps.tasks.tasks_collector._csv_to_json")
    def test_collect_main_host_hourly_success(self, mock_csv_to_json, mock_get_db, mock_main_host):
        """Test successful hourly main_host collection."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_collector = MagicMock()
        mock_collector.gather.return_value = []
        mock_main_host.return_value = mock_collector

        mock_csv_to_json.return_value = {"records": [], "total_records": 0, "file_count": 0}

        result = collect_main_host_hourly()

        assert result["status"] == "success"

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.job_host_summary")
    @patch("apps.tasks.tasks_collector._get_db_connection")
    def test_collect_hourly_with_custom_timestamp(self, mock_get_db, mock_job_host_summary):
        """Test hourly collection with custom timestamp."""
        from apps.tasks.models import HourlyMetricsCollection

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_collector = MagicMock()
        mock_collector.gather.return_value = []
        mock_job_host_summary.return_value = mock_collector

        # Use specific hour timestamp
        hour_timestamp = "2024-01-15T10:00:00+00:00"

        with patch("apps.tasks.tasks_collector._csv_to_json", return_value={"total_records": 0}):
            result = collect_job_host_summary_hourly(hour_timestamp=hour_timestamp)

        assert result["status"] == "success"
        collection = HourlyMetricsCollection.objects.get(id=result["collection_id"])
        assert collection.collection_timestamp.hour == 10

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.job_host_summary")
    @patch("apps.tasks.tasks_collector._get_db_connection")
    def test_collect_hourly_error_handling(self, mock_get_db, mock_job_host_summary):
        """Test error handling in hourly collection."""
        from apps.tasks.models import HourlyMetricsCollection

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Make collector raise exception
        mock_job_host_summary.side_effect = Exception("Collection failed")

        result = collect_job_host_summary_hourly()

        assert result["status"] == "error"
        assert "Collection failed" in result["error"]

        # Check failed collection record created
        failed_collections = HourlyMetricsCollection.objects.filter(status="failed")
        assert failed_collections.exists()


@pytest.mark.unit
@pytest.mark.django_db
class TestDailyRollupTask(TestCase):
    """Test daily metrics rollup task."""

    def test_daily_metrics_rollup_no_collections(self):
        """Test daily rollup with no hourly collections."""
        from datetime import date

        summary_date = date(2024, 1, 15)
        result = daily_metrics_rollup(summary_date=summary_date.isoformat())

        assert result["status"] == "success"
        assert "summary_id" in result
        assert result["hourly_collections_count"] == 0

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.config")
    @patch("apps.tasks.tasks_collector._get_db_connection")
    def test_daily_metrics_rollup_with_collections(self, mock_get_db, mock_config):
        """Test daily rollup with hourly collections."""
        from datetime import date

        from apps.tasks.models import DailyMetricsSummary, HourlyMetricsCollection

        summary_date = date(2024, 1, 15)
        start_datetime = timezone.make_aware(datetime.combine(summary_date, datetime.min.time()))

        # Create hourly collections
        for hour in range(24):
            collection_time = start_datetime + timedelta(hours=hour)
            HourlyMetricsCollection.objects.create(
                collector_type="job_host_summary",
                collection_timestamp=collection_time,
                raw_data={"total_records": 10},
                status="collected",
            )

        # Mock config collector
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_collector = MagicMock()
        mock_collector.gather.return_value = {"version": "4.5.0"}
        mock_config.return_value = mock_collector

        result = daily_metrics_rollup(summary_date=summary_date.isoformat())

        assert result["status"] == "success"
        assert result["hourly_collections_count"] == 24
        # Will have missing hours for main_host and main_jobevent (48 missing = 24*2 collector types)
        assert len(result["missing_hours"]) == 48

        # Verify summary created
        summary = DailyMetricsSummary.objects.get(id=result["summary_id"])
        assert summary.status == "aggregated"
        assert summary.hourly_collections_count == 24

        # Verify hourly collections marked as processed
        processed = HourlyMetricsCollection.objects.filter(status="processed").count()
        assert processed == 24

    def test_daily_metrics_rollup_default_date(self):
        """Test daily rollup with default date (yesterday)."""
        result = daily_metrics_rollup()

        assert result["status"] == "success"
        # Should use yesterday's date
        assert "summary_date" in result

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.config")
    @patch("apps.tasks.tasks_collector._get_db_connection")
    def test_daily_metrics_rollup_missing_hours(self, mock_get_db, mock_config):
        """Test daily rollup detects missing hours."""
        from datetime import date

        from apps.tasks.models import HourlyMetricsCollection

        summary_date = date(2024, 1, 16)
        start_datetime = timezone.make_aware(datetime.combine(summary_date, datetime.min.time()))

        # Create only 12 hours of collections
        for hour in range(12):
            collection_time = start_datetime + timedelta(hours=hour)
            HourlyMetricsCollection.objects.create(
                collector_type="job_host_summary",
                collection_timestamp=collection_time,
                raw_data={"total_records": 5},
                status="collected",
            )

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_collector = MagicMock()
        mock_collector.gather.return_value = {}
        mock_config.return_value = mock_collector

        result = daily_metrics_rollup(summary_date=summary_date.isoformat())

        assert result["status"] == "success"
        assert len(result["missing_hours"]) > 0  # Should detect missing hours

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.config")
    @patch("apps.tasks.tasks_collector._get_db_connection")
    def test_daily_metrics_rollup_config_error(self, mock_get_db, mock_config):
        """Test daily rollup handles config collection errors."""
        from datetime import date

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_config.side_effect = Exception("Config collection failed")

        summary_date = date(2024, 1, 17)
        result = daily_metrics_rollup(summary_date=summary_date.isoformat())

        # Should still succeed but with error in config_data
        assert result["status"] == "success"


@pytest.mark.unit
@pytest.mark.django_db
class TestAnonymizationTask(TestCase):
    """Test daily anonymization and preparation task."""

    def test_daily_anonymize_no_summary(self):
        """Test anonymization when daily summary doesn't exist."""
        from datetime import date

        summary_date = date(2024, 1, 20)
        result = daily_anonymize_and_prepare(summary_date=summary_date.isoformat())

        assert result["status"] == "error"
        assert "No daily summary found" in result["error"]

    @patch("apps.tasks.tasks_collector._generate_salt")
    def test_daily_anonymize_success(self, mock_generate_salt):
        """Test successful anonymization."""
        from datetime import date

        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        mock_generate_salt.return_value = "test-salt-12345"

        summary_date = date(2024, 1, 20)

        # Create daily summary
        summary = DailyMetricsSummary.objects.create(
            summary_date=summary_date,
            aggregated_metrics={
                "job_host_summary": {"total": 100},
                "main_jobevent": {"total": 200},
            },
            config_data={"version": "4.5.0"},
            status="aggregated",
            hourly_collections_count=24,
            missing_hours=[],
        )

        result = daily_anonymize_and_prepare(summary_date=summary_date.isoformat())

        assert result["status"] == "success"
        assert "payload_id" in result

        # Verify payload created
        payload = AnonymizedMetricsPayload.objects.get(id=result["payload_id"])
        assert payload.status == "pending"
        assert "job_host_summary" in payload.anonymized_data

        # Verify summary updated
        summary.refresh_from_db()
        assert summary.status == "anonymized"

    def test_daily_anonymize_custom_salt(self):
        """Test anonymization with custom salt."""
        from datetime import date

        from apps.tasks.models import DailyMetricsSummary

        summary_date = date(2024, 1, 21)

        DailyMetricsSummary.objects.create(
            summary_date=summary_date,
            aggregated_metrics={},
            config_data={},
            status="aggregated",
            hourly_collections_count=0,
        )

        result = daily_anonymize_and_prepare(summary_date=summary_date.isoformat(), salt="custom-salt-abc")

        assert result["status"] == "success"


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

    @patch("apps.tasks.tasks_collector.SEGMENT_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector._send_to_segment")
    def test_send_to_segment_success(self, mock_send_to_segment):
        """Test successful sending to Segment."""
        from datetime import date

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

    @patch("apps.tasks.tasks_collector.SEGMENT_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector._send_to_segment")
    def test_send_to_segment_specific_payload(self, mock_send_to_segment):
        """Test sending specific payload by ID."""
        from datetime import date

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

    @patch("apps.tasks.tasks_collector.SEGMENT_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector._send_to_segment")
    def test_send_to_segment_retry_logic(self, mock_send_to_segment):
        """Test retry logic for failed sends."""
        from datetime import date

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

    @patch("apps.tasks.tasks_collector.SEGMENT_AVAILABLE", True)
    def test_send_to_segment_max_retries_exceeded(self):
        """Test handling when max retries exceeded."""
        from datetime import date

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

    @patch("apps.tasks.tasks_collector.SEGMENT_AVAILABLE", False)
    def test_send_to_segment_not_available(self):
        """Test sending when Segment not available."""
        from datetime import date

        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

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
