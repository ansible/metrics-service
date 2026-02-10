"""
Advanced tests for tasks_collector.py to improve code coverage.

This test file focuses on covering helper functions and advanced workflows
that aren't covered by the basic comprehensive tests.
"""

import tempfile
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.tasks.collectors.collect_host_metrics_hourly import collect_host_metrics_hourly
from apps.tasks.collectors.collect_job_host_summary_hourly import collect_job_host_summary_hourly
from apps.tasks.collectors.collect_main_host_hourly import collect_main_host_hourly
from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare
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
class TestAggregationHelpers(TestCase):
    """Test aggregation helper functions."""

    def test_aggregate_collector_data_empty(self):
        """Test _aggregate_collector_data with empty collections."""
        from apps.tasks.collectors.daily_metrics_rollup import _aggregate_collector_data

        result = _aggregate_collector_data([])
        assert result["total_records"] == 0
        assert result["hourly_snapshots"] == []
        assert result["records"] == []

    def test_aggregate_collector_data_with_dict_data(self):
        """Test _aggregate_collector_data with dict data containing records."""
        from apps.tasks.collectors.daily_metrics_rollup import _aggregate_collector_data

        # Create mock collections using csv_to_json format
        collection1 = Mock()
        collection1.raw_data = {
            "records": [{"host": "host1"}, {"host": "host2"}, {"host": "host3"}],
            "total_records": 3,
            "file_count": 1,
        }
        collection1.collection_timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        collection1.id = 1

        collection2 = Mock()
        collection2.raw_data = {
            "records": [{"host": "host4"}, {"host": "host5"}],
            "total_records": 2,
            "file_count": 1,
        }
        collection2.collection_timestamp = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)
        collection2.id = 2

        result = _aggregate_collector_data([collection1, collection2])
        assert result["total_records"] == 5
        assert len(result["hourly_snapshots"]) == 2
        assert result["hourly_snapshots"][0]["hour"] == 12
        assert result["hourly_snapshots"][0]["record_count"] == 3
        assert result["hourly_snapshots"][1]["hour"] == 13
        assert result["hourly_snapshots"][1]["record_count"] == 2
        # Verify records are merged
        assert len(result["records"]) == 5
        assert result["records"][0] == {"host": "host1"}
        assert result["records"][4] == {"host": "host5"}

    def test_aggregate_collector_data_with_list_data(self):
        """Test _aggregate_collector_data with list data (legacy format)."""
        from apps.tasks.collectors.daily_metrics_rollup import _aggregate_collector_data

        collection = Mock()
        collection.raw_data = [{"item": 1}, {"item": 2}, {"item": 3}]
        collection.collection_timestamp = datetime(2024, 1, 1, 14, 0, 0, tzinfo=UTC)
        collection.id = 3

        result = _aggregate_collector_data([collection])
        assert result["total_records"] == 3
        # Records should be merged from raw list
        assert len(result["records"]) == 3
        assert result["records"] == [{"item": 1}, {"item": 2}, {"item": 3}]

    def test_aggregate_collector_data_with_other_data(self):
        """Test _aggregate_collector_data with non-dict/list data."""
        from apps.tasks.collectors.daily_metrics_rollup import _aggregate_collector_data

        collection = Mock()
        collection.raw_data = "some string"
        collection.collection_timestamp = datetime(2024, 1, 1, 15, 0, 0, tzinfo=UTC)
        collection.id = 4

        result = _aggregate_collector_data([collection])
        assert result["total_records"] == 0
        # No records extracted from invalid data
        assert result["records"] == []

    def test_aggregate_collector_data_merges_multiple_hours(self):
        """Test _aggregate_collector_data properly merges records from multiple hours."""
        from apps.tasks.collectors.daily_metrics_rollup import _aggregate_collector_data

        # Simulate 3 hourly collections with different record counts
        collections = []
        for hour in range(3):
            collection = Mock()
            collection.raw_data = {
                "records": [{"hour": hour, "record": i} for i in range(hour + 1)],
                "total_records": hour + 1,
                "file_count": 1,
            }
            collection.collection_timestamp = datetime(2024, 1, 1, hour, 0, 0, tzinfo=UTC)
            collection.id = hour + 1
            collections.append(collection)

        result = _aggregate_collector_data(collections)
        # Total: 1 + 2 + 3 = 6 records
        assert result["total_records"] == 6
        assert len(result["records"]) == 6
        assert len(result["hourly_snapshots"]) == 3


@pytest.mark.unit
@pytest.mark.django_db
class TestAggregationToAnonymizationIntegration(TestCase):
    """Test that aggregated data is correctly extracted for anonymization."""

    @patch("apps.tasks.collectors.daily_anonymize_and_prepare.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.daily_anonymize_and_prepare.anonymize_rollup_data")
    def test_daily_anonymize_extracts_records_from_new_structure(self, mock_anonymize):
        """Test daily_anonymize_and_prepare extracts records from new aggregated structure."""
        from apps.tasks.models import DailyMetricsSummary

        mock_anonymize.return_value = None

        # Create summary with the NEW aggregated structure (with records key)
        DailyMetricsSummary.objects.create(
            summary_date=date(2024, 4, 1),
            aggregated_metrics={
                "job_host_summary": {
                    "records": [{"host": "host1"}, {"host": "host2"}],
                    "total_records": 2,
                    "hourly_snapshots": [{"hour": 0, "record_count": 2}],
                },
                "main_host": {
                    "records": [{"host_id": 1}, {"host_id": 2}, {"host_id": 3}],
                    "total_records": 3,
                    "hourly_snapshots": [{"hour": 0, "record_count": 3}],
                },
                "main_jobevent": {
                    "records": [{"event": "runner_on_ok"}],
                    "total_records": 1,
                    "hourly_snapshots": [{"hour": 0, "record_count": 1}],
                },
            },
            config_data={"version": "4.5.0"},
            status="aggregated",
            hourly_collections_count=24,
            missing_hours=[],
            aggregation_completed_at=timezone.now(),
        )

        result = daily_anonymize_and_prepare(summary_date=date(2024, 4, 1).isoformat())

        assert result["status"] == "success"
        mock_anonymize.assert_called_once()

        # Verify records were extracted, not the entire structure with metadata
        call_data = mock_anonymize.call_args[0][0]
        assert call_data["job_host_summary"] == [{"host": "host1"}, {"host": "host2"}]
        assert call_data["main_host"] == [{"host_id": 1}, {"host_id": 2}, {"host_id": 3}]
        assert call_data["main_jobevent"] == [{"event": "runner_on_ok"}]


@pytest.mark.unit
@pytest.mark.django_db
class TestHourlyCollectionTasks(TestCase):
    """Test hourly collection tasks."""

    @patch("apps.tasks.collectors.helpers.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_job_host_summary_hourly_utility_unavailable(self):
        """Test hourly collection when metrics-utility not available."""
        result = collect_job_host_summary_hourly()
        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]

    @patch("apps.tasks.collectors.helpers.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.collect_job_host_summary_hourly.job_host_summary")
    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.csv_to_json")
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

    @patch("apps.tasks.collectors.helpers.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.collect_host_metrics_hourly.main_jobevent")
    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.csv_to_json")
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

    @patch("apps.tasks.collectors.helpers.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.collect_main_host_hourly.main_host")
    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.csv_to_json")
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

    @patch("apps.tasks.collectors.helpers.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.collect_job_host_summary_hourly.job_host_summary")
    @patch("apps.tasks.utils.get_db_connection")
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

        with patch("apps.tasks.utils.csv_to_json", return_value={"total_records": 0}):
            result = collect_job_host_summary_hourly(hour_timestamp=hour_timestamp)

        assert result["status"] == "success"
        collection = HourlyMetricsCollection.objects.get(id=result["collection_id"])
        assert collection.collection_timestamp.hour == 10

    @patch("apps.tasks.collectors.helpers.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.collect_job_host_summary_hourly.job_host_summary")
    @patch("apps.tasks.utils.get_db_connection")
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

    @patch("apps.tasks.collectors.daily_metrics_rollup.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.helpers.config")
    @patch("apps.tasks.utils.get_db_connection")
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

    @patch("apps.tasks.collectors.daily_metrics_rollup.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.helpers.config")
    @patch("apps.tasks.utils.get_db_connection")
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

    @patch("apps.tasks.collectors.daily_metrics_rollup.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.helpers.config")
    @patch("apps.tasks.utils.get_db_connection")
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

    @patch("apps.tasks.collectors.daily_anonymize_and_prepare.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.daily_anonymize_and_prepare.anonymize_rollup_data")
    def test_daily_anonymize_no_summary(self, mock_anonymize):
        """Test anonymization when daily summary doesn't exist."""
        from datetime import date

        # Mock is not used because the error happens before calling it
        mock_anonymize.return_value = None

        summary_date = date(2024, 1, 20)
        result = daily_anonymize_and_prepare(summary_date=summary_date.isoformat())

        assert result["status"] == "error"
        assert "No daily summary found" in result["error"]

    @patch("apps.tasks.collectors.daily_anonymize_and_prepare.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.daily_anonymize_and_prepare.anonymize_rollup_data")
    @patch("apps.tasks.utils.generate_salt")
    def test_daily_anonymize_success(self, mock_generate_salt, mock_anonymize):
        """Test successful anonymization."""
        from datetime import date

        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        mock_generate_salt.return_value = "test-salt-12345"
        # Mock anonymize_rollup_data to modify data in-place (like the real function)
        mock_anonymize.return_value = None

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

    @patch("apps.tasks.collectors.daily_anonymize_and_prepare.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.daily_anonymize_and_prepare.anonymize_rollup_data")
    def test_daily_anonymize_custom_salt(self, mock_anonymize):
        """Test anonymization with custom salt."""
        from datetime import date

        from apps.tasks.models import DailyMetricsSummary

        # Mock anonymize_rollup_data to modify data in-place
        mock_anonymize.return_value = None

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

    @patch("apps.tasks.utils.send_to_segment")
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

    @patch("apps.tasks.utils.send_to_segment")
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

    @patch("apps.tasks.utils.send_to_segment")
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

    @patch("apps.tasks.collectors.send_anonymized_to_segment.send_to_segment")
    def test_send_to_segment_not_available(self, mock_send_to_segment):
        """Test sending when Segment not available."""
        from datetime import date

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
        from datetime import date

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

    @patch("apps.tasks.collectors.daily_anonymize_and_prepare.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.collectors.daily_anonymize_and_prepare.anonymize_rollup_data")
    def test_transaction_rollback_on_error(self, mock_anonymize):
        """Test transaction rollback prevents partial state (Issue #8)."""
        from datetime import date

        from apps.tasks.models import DailyMetricsSummary

        # Create daily summary
        summary = DailyMetricsSummary.objects.create(
            summary_date=date(2024, 1, 31),
            aggregated_metrics={"job_host_summary": {"total": 100}},
            config_data={},
            status="aggregated",
        )

        original_status = summary.status

        # Mock the anonymize_rollup_data function from metrics-utility to raise an error
        mock_anonymize.side_effect = Exception("Anonymization error")

        # Call the function, should fail
        result = daily_anonymize_and_prepare(summary_date=date(2024, 1, 31).isoformat())

        assert result["status"] == "error"
        assert "Anonymization failed" in result["error"]

        # Verify summary status was NOT changed (transaction rolled back)
        summary.refresh_from_db()
        assert summary.status == original_status  # Should still be "aggregated"

        # Verify no payload was created
        from apps.tasks.models import AnonymizedMetricsPayload

        assert AnonymizedMetricsPayload.objects.filter(daily_summary=summary).count() == 0

    def test_cleanup_all_payload_statuses(self):
        """Test cleanup includes all payload statuses, not just failed (Issue #7)."""
        from datetime import date, timedelta

        from django.utils import timezone

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

    @patch("apps.tasks.collectors.helpers.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.utils.csv_to_json")
    @patch("apps.tasks.collectors.collect_job_host_summary_hourly.job_host_summary")
    @patch("apps.tasks.utils.get_db_connection")
    def test_retry_after_failure_updates_existing_record(self, mock_get_db, mock_collector_class, mock_csv_to_json):
        """
        Test that a successful retry updates the failed record instead of creating a new one.

        This verifies the fix for the IntegrityError that would occur when a task
        is retried after failure (since unique_together constraint on collector_type + timestamp).
        """
        from apps.tasks.models import HourlyMetricsCollection

        # Set up a fixed collection hour
        collection_hour = timezone.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

        # Create an existing "failed" record for this hour
        failed_record = HourlyMetricsCollection.objects.create(
            collector_type="job_host_summary",
            collection_timestamp=collection_hour,
            raw_data={},
            status="failed",
            error_message="Initial failure",
        )
        original_id = failed_record.id

        # Mock successful collection
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_collector = MagicMock()
        mock_collector.gather.return_value = ["/tmp/test.csv"]  # noqa: S108
        mock_collector_class.return_value = mock_collector
        mock_csv_to_json.return_value = {"total_records": 100, "data": [{"host": "test"}]}

        # Run the collection with the same timestamp
        result = collect_job_host_summary_hourly(hour_timestamp=collection_hour.isoformat())

        # Should succeed
        assert result["status"] == "success"
        assert result["was_retry"] is True  # Indicates it was an update, not a create

        # Verify only one record exists (the original one was updated)
        records = HourlyMetricsCollection.objects.filter(
            collector_type="job_host_summary",
            collection_timestamp=collection_hour,
        )
        assert records.count() == 1

        # Verify the record was updated (same ID, new status)
        updated_record = records.first()
        assert updated_record.id == original_id
        assert updated_record.status == "collected"
        assert updated_record.raw_data["total_records"] == 100
        assert updated_record.error_message == ""  # Error cleared

    @patch("apps.tasks.collectors.helpers.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.utils.csv_to_json")
    @patch("apps.tasks.collectors.collect_job_host_summary_hourly.job_host_summary")
    @patch("apps.tasks.utils.get_db_connection")
    def test_scheduler_double_trigger_updates_existing_record(
        self, mock_get_db, mock_collector_class, mock_csv_to_json
    ):
        """
        Test that a double-triggered task updates the existing record.

        This simulates a scheduler double-trigger scenario where the same collection
        is triggered twice for the same hour.
        """
        from apps.tasks.models import HourlyMetricsCollection

        # Set up mocks
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_collector = MagicMock()
        mock_collector.gather.return_value = ["/tmp/test.csv"]  # noqa: S108
        mock_collector_class.return_value = mock_collector

        collection_hour = timezone.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

        # First call - data with 50 records
        mock_csv_to_json.return_value = {"total_records": 50, "data": [{"host": "first"}]}
        result1 = collect_job_host_summary_hourly(hour_timestamp=collection_hour.isoformat())

        assert result1["status"] == "success"
        assert result1["was_retry"] is False  # First creation

        first_id = result1["collection_id"]

        # Second call (double-trigger) - data with 100 records
        mock_csv_to_json.return_value = {"total_records": 100, "data": [{"host": "second"}]}
        result2 = collect_job_host_summary_hourly(hour_timestamp=collection_hour.isoformat())

        assert result2["status"] == "success"
        assert result2["was_retry"] is True  # Update of existing
        assert result2["collection_id"] == first_id  # Same record ID

        # Verify only one record exists
        records = HourlyMetricsCollection.objects.filter(
            collector_type="job_host_summary",
            collection_timestamp=collection_hour,
        )
        assert records.count() == 1

        # Verify the record has the latest data
        updated_record = records.first()
        assert updated_record.raw_data["total_records"] == 100
