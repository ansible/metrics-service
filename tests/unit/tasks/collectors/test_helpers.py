"""
Unit tests for apps/tasks/collectors/helpers.py

Tests cover:
- _compute_rollup_from_dataframe: DataFrame rollup computation
- _collect_hourly_metrics: Core collection pipeline with error handling
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.tasks.collectors.helpers import (
    _collect_hourly_metrics,
    _compute_rollup_from_dataframe,
)


@pytest.mark.unit
@pytest.mark.django_db
class TestComputeRollupFromDataframe:
    """Test _compute_rollup_from_dataframe function."""

    def test_compute_rollup_with_valid_dataframe(self, sample_dataframe, mock_rollup_processor):
        """Test rollup computation with valid DataFrame calls prepare() and base()."""
        # Arrange
        prepared_df = MagicMock()
        mock_rollup_processor.prepare.return_value = prepared_df
        expected_result = {
            "json": {"total": 100, "count": 3},
            "rollup": {"aggregated_data": "test"},
        }
        mock_rollup_processor.base.return_value = expected_result

        # Act
        result = _compute_rollup_from_dataframe(sample_dataframe, mock_rollup_processor)

        # Assert
        mock_rollup_processor.prepare.assert_called_once_with(sample_dataframe)
        mock_rollup_processor.base.assert_called_once_with(prepared_df)
        assert result == expected_result

    def test_compute_rollup_with_none_dataframe(self, mock_rollup_processor):
        """Test rollup computation with None DataFrame returns rollup result without prepare()."""
        # Arrange
        expected_result = {
            "json": {},
            "rollup": {},
        }
        mock_rollup_processor.base.return_value = expected_result

        # Act
        result = _compute_rollup_from_dataframe(None, mock_rollup_processor)

        # Assert
        # prepare() should NOT be called for None dataframe
        mock_rollup_processor.prepare.assert_not_called()
        # base() should be called with None
        mock_rollup_processor.base.assert_called_once_with(None)
        assert result == expected_result

    def test_compute_rollup_with_empty_dataframe(self, empty_dataframe, mock_rollup_processor):
        """Test rollup computation with empty DataFrame skips prepare()."""
        # Arrange
        expected_result = {
            "json": {},
            "rollup": {},
        }
        mock_rollup_processor.base.return_value = expected_result

        # Act
        result = _compute_rollup_from_dataframe(empty_dataframe, mock_rollup_processor)

        # Assert
        # prepare() should NOT be called for empty dataframe
        mock_rollup_processor.prepare.assert_not_called()
        # base() should be called with None (empty dataframe is converted to None)
        mock_rollup_processor.base.assert_called_once_with(None)
        assert result == expected_result


@pytest.mark.unit
@pytest.mark.django_db
class TestCollectHourlyMetrics:
    """Test _collect_hourly_metrics function."""

    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.parse_datetime_string")
    def test_collect_with_date_range_sets_since_until(
        self, mock_parse_datetime, mock_get_db_connection, collection_hour, mock_rollup_processor, sample_dataframe
    ):
        """Test date range collection (uses_date_range=True) sets since/until parameters."""
        # Arrange
        mock_parse_datetime.return_value = collection_hour
        mock_db = MagicMock()
        mock_get_db_connection.return_value = mock_db

        mock_collector_func = MagicMock()
        mock_collector = MagicMock()
        mock_collector.gather.return_value = sample_dataframe
        mock_collector_func.return_value = mock_collector

        # Act
        result = _collect_hourly_metrics(
            collector_name="job_host_summary",
            collector_func=mock_collector_func,
            rollup_processor=mock_rollup_processor,
            task_name="test_task",
            uses_date_range=True,
            hour_timestamp=collection_hour.isoformat(),
        )

        # Assert
        # Verify collector was called with since/until
        expected_since = collection_hour
        expected_until = collection_hour + timedelta(hours=1)
        mock_collector_func.assert_called_once_with(db=mock_db, since=expected_since, until=expected_until)
        assert result["status"] == "success"
        assert result["collector_type"] == "job_host_summary"

    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.parse_datetime_string")
    def test_collect_without_date_range_no_since_until(
        self, mock_parse_datetime, mock_get_db_connection, collection_hour, sample_dataframe
    ):
        """Test non-date-range collection (uses_date_range=False) has no since/until."""
        # Arrange
        mock_parse_datetime.return_value = collection_hour
        mock_db = MagicMock()
        mock_get_db_connection.return_value = mock_db

        mock_collector_func = MagicMock()
        mock_collector = MagicMock()
        # Convert DataFrame to list of dicts (JSON serializable)
        mock_collector.gather.return_value = sample_dataframe.to_dict("records")
        mock_collector_func.return_value = mock_collector

        # Act
        result = _collect_hourly_metrics(
            collector_name="main_host",
            collector_func=mock_collector_func,
            rollup_processor=None,  # No rollup for snapshots
            task_name="test_task",
            uses_date_range=False,
            hour_timestamp=collection_hour.isoformat(),
        )

        # Assert
        # Verify collector was called WITHOUT since/until
        mock_collector_func.assert_called_once_with(db=mock_db)
        assert result["status"] == "success"

    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.parse_datetime_string")
    def test_collect_with_rollup_processor_calls_prepare_base(
        self, mock_parse_datetime, mock_get_db_connection, collection_hour, mock_rollup_processor, sample_dataframe
    ):
        """Test rollup computation with processor calls prepare() and base()."""
        # Arrange
        mock_parse_datetime.return_value = collection_hour
        mock_db = MagicMock()
        mock_get_db_connection.return_value = mock_db

        mock_collector_func = MagicMock()
        mock_collector = MagicMock()
        mock_collector.gather.return_value = sample_dataframe
        mock_collector_func.return_value = mock_collector

        prepared_df = MagicMock()
        mock_rollup_processor.prepare.return_value = prepared_df
        mock_rollup_processor.base.return_value = {
            "json": {"total": 100},
            "rollup": {"test": "data"},
        }

        # Act
        result = _collect_hourly_metrics(
            collector_name="job_host_summary",
            collector_func=mock_collector_func,
            rollup_processor=mock_rollup_processor,
            task_name="test_task",
            uses_date_range=True,
            hour_timestamp=collection_hour.isoformat(),
        )

        # Assert
        mock_rollup_processor.prepare.assert_called_once()
        mock_rollup_processor.base.assert_called_once()
        assert result["status"] == "success"

    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.parse_datetime_string")
    def test_collect_without_rollup_stores_dataframe_as_list(
        self, mock_parse_datetime, mock_get_db_connection, collection_hour, sample_dataframe
    ):
        """Test DataFrame storage without processor stores as records with total_records."""
        # Arrange
        mock_parse_datetime.return_value = collection_hour
        mock_db = MagicMock()
        mock_get_db_connection.return_value = mock_db

        mock_collector_func = MagicMock()
        mock_collector = MagicMock()
        # Convert DataFrame to list of dicts (JSON serializable)
        data_as_list = sample_dataframe.to_dict("records")
        mock_collector.gather.return_value = data_as_list
        mock_collector_func.return_value = mock_collector

        # Act
        result = _collect_hourly_metrics(
            collector_name="main_host",
            collector_func=mock_collector_func,
            rollup_processor=None,  # No rollup processor
            task_name="test_task",
            uses_date_range=False,
            hour_timestamp=collection_hour.isoformat(),
        )

        # Assert
        from apps.tasks.models import HourlyMetricsCollection

        collection = HourlyMetricsCollection.objects.get(id=result["collection_id"])
        assert "records" in collection.raw_data
        assert "total_records" in collection.raw_data
        assert collection.raw_data["total_records"] == len(data_as_list)

    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.parse_datetime_string")
    def test_collect_creates_hourly_collection_record(
        self, mock_parse_datetime, mock_get_db_connection, collection_hour, sample_dataframe
    ):
        """Test HourlyMetricsCollection creation with proper fields."""
        # Arrange
        mock_parse_datetime.return_value = collection_hour
        mock_db = MagicMock()
        mock_get_db_connection.return_value = mock_db

        mock_collector_func = MagicMock()
        mock_collector = MagicMock()
        # Convert DataFrame to list of dicts (JSON serializable)
        mock_collector.gather.return_value = sample_dataframe.to_dict("records")
        mock_collector_func.return_value = mock_collector

        # Act
        result = _collect_hourly_metrics(
            collector_name="test_collector",
            collector_func=mock_collector_func,
            rollup_processor=None,
            task_name="test_task",
            uses_date_range=False,
            hour_timestamp=collection_hour.isoformat(),
        )

        # Assert
        from apps.tasks.models import HourlyMetricsCollection

        collection = HourlyMetricsCollection.objects.get(id=result["collection_id"])
        assert collection.collector_type == "test_collector"
        assert collection.collection_timestamp == collection_hour
        assert collection.status == "collected"
        assert collection.error_message == ""

    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.parse_datetime_string")
    def test_collect_updates_existing_on_retry(
        self, mock_parse_datetime, mock_get_db_connection, collection_hour, hourly_collection_factory, sample_dataframe
    ):
        """Test update_or_create updates existing record on retry."""
        # Arrange
        mock_parse_datetime.return_value = collection_hour
        mock_db = MagicMock()
        mock_get_db_connection.return_value = mock_db

        # Create existing collection
        existing = hourly_collection_factory(
            collector_type="test_collector",
            collection_timestamp=collection_hour,
            status="failed",
            error_message="Previous error",
        )

        mock_collector_func = MagicMock()
        mock_collector = MagicMock()
        # Convert DataFrame to list of dicts (JSON serializable)
        mock_collector.gather.return_value = sample_dataframe.to_dict("records")
        mock_collector_func.return_value = mock_collector

        # Act
        result = _collect_hourly_metrics(
            collector_name="test_collector",
            collector_func=mock_collector_func,
            rollup_processor=None,
            task_name="test_task",
            uses_date_range=False,
            hour_timestamp=collection_hour.isoformat(),
        )

        # Assert
        from apps.tasks.models import HourlyMetricsCollection

        # Should still be only one record
        assert HourlyMetricsCollection.objects.filter(collector_type="test_collector").count() == 1
        # Should be updated, not created
        assert result["was_retry"] is True
        # Verify error was cleared
        collection = HourlyMetricsCollection.objects.get(id=existing.id)
        assert collection.status == "collected"
        assert collection.error_message == ""

    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.parse_datetime_string")
    def test_collect_handles_collection_error(self, mock_parse_datetime, mock_get_db_connection, collection_hour):
        """Test collection error handling stores failed collection with error_message."""
        # Arrange
        mock_parse_datetime.return_value = collection_hour
        mock_db = MagicMock()
        mock_get_db_connection.return_value = mock_db

        mock_collector_func = MagicMock()
        mock_collector = MagicMock()
        mock_collector.gather.side_effect = Exception("Collection failed")
        mock_collector_func.return_value = mock_collector

        # Act
        result = _collect_hourly_metrics(
            collector_name="test_collector",
            collector_func=mock_collector_func,
            rollup_processor=None,
            task_name="test_task",
            uses_date_range=False,
            hour_timestamp=collection_hour.isoformat(),
        )

        # Assert
        assert result["status"] == "error"
        assert "Collection failed" in result["error"]

        # Verify failed collection was stored
        from apps.tasks.models import HourlyMetricsCollection

        failed_collection = HourlyMetricsCollection.objects.get(
            collector_type="test_collector", collection_timestamp=collection_hour
        )
        assert failed_collection.status == "failed"
        assert "Collection failed" in failed_collection.error_message
        assert failed_collection.raw_data == {}

    @patch("apps.tasks.utils.get_db_connection")
    def test_collect_uses_explicit_hour_timestamp(self, mock_get_db_connection, sample_dataframe):
        """Test hour_timestamp parsing from kwargs uses explicit timestamp."""
        # Arrange
        explicit_hour = timezone.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=5)
        mock_db = MagicMock()
        mock_get_db_connection.return_value = mock_db

        mock_collector_func = MagicMock()
        mock_collector = MagicMock()
        # Convert DataFrame to list of dicts (JSON serializable)
        mock_collector.gather.return_value = sample_dataframe.to_dict("records")
        mock_collector_func.return_value = mock_collector

        # Act
        result = _collect_hourly_metrics(
            collector_name="test_collector",
            collector_func=mock_collector_func,
            rollup_processor=None,
            task_name="test_task",
            uses_date_range=False,
            hour_timestamp=explicit_hour.isoformat(),
        )

        # Assert
        from apps.tasks.models import HourlyMetricsCollection

        collection = HourlyMetricsCollection.objects.get(id=result["collection_id"])
        assert collection.collection_timestamp == explicit_hour

    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.parse_datetime_string")
    def test_collect_defaults_to_previous_hour(self, mock_parse_datetime, mock_get_db_connection, sample_dataframe):
        """Test default to previous hour when no timestamp provided."""
        # Arrange
        # Simulate parse_datetime_string returning None (invalid/missing timestamp)
        mock_parse_datetime.return_value = None
        mock_db = MagicMock()
        mock_get_db_connection.return_value = mock_db

        mock_collector_func = MagicMock()
        mock_collector = MagicMock()
        # Convert DataFrame to list of dicts (JSON serializable)
        mock_collector.gather.return_value = sample_dataframe.to_dict("records")
        mock_collector_func.return_value = mock_collector

        # Act
        before_call = timezone.now()
        result = _collect_hourly_metrics(
            collector_name="test_collector",
            collector_func=mock_collector_func,
            rollup_processor=None,
            task_name="test_task",
            uses_date_range=False,
            # No hour_timestamp provided
        )
        after_call = timezone.now()

        # Assert
        from apps.tasks.models import HourlyMetricsCollection

        collection = HourlyMetricsCollection.objects.get(id=result["collection_id"])
        # Should be previous hour (between before_call - 1 hour and after_call - 1 hour)
        expected_min = before_call.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        expected_max = after_call.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        assert expected_min <= collection.collection_timestamp <= expected_max

    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.parse_datetime_string")
    def test_collect_with_dict_data(self, mock_parse_datetime, mock_get_db_connection, collection_hour):
        """Test collection with dict data (e.g., config collector) sets total_records=1."""
        # Arrange
        mock_parse_datetime.return_value = collection_hour
        mock_db = MagicMock()
        mock_get_db_connection.return_value = mock_db

        mock_collector_func = MagicMock()
        mock_collector = MagicMock()
        # Config collector returns dict, not DataFrame
        mock_collector.gather.return_value = {"config_key": "config_value"}
        mock_collector_func.return_value = mock_collector

        # Act
        result = _collect_hourly_metrics(
            collector_name="config",
            collector_func=mock_collector_func,
            rollup_processor=None,
            task_name="test_task",
            uses_date_range=False,
            hour_timestamp=collection_hour.isoformat(),
        )

        # Assert
        from apps.tasks.models import HourlyMetricsCollection

        collection = HourlyMetricsCollection.objects.get(id=result["collection_id"])
        assert "records" in collection.raw_data
        assert collection.raw_data["total_records"] == 1  # Single dict = 1 record

    @patch("apps.tasks.utils.get_db_connection")
    @patch("apps.tasks.utils.parse_datetime_string")
    def test_collect_with_list_data(self, mock_parse_datetime, mock_get_db_connection, collection_hour):
        """Test collection with list data sets total_records correctly."""
        # Arrange
        mock_parse_datetime.return_value = collection_hour
        mock_db = MagicMock()
        mock_get_db_connection.return_value = mock_db

        mock_collector_func = MagicMock()
        mock_collector = MagicMock()
        mock_collector.gather.return_value = [{"item": 1}, {"item": 2}, {"item": 3}]
        mock_collector_func.return_value = mock_collector

        # Act
        result = _collect_hourly_metrics(
            collector_name="test_list",
            collector_func=mock_collector_func,
            rollup_processor=None,
            task_name="test_task",
            uses_date_range=False,
            hour_timestamp=collection_hour.isoformat(),
        )

        # Assert
        from apps.tasks.models import HourlyMetricsCollection

        collection = HourlyMetricsCollection.objects.get(id=result["collection_id"])
        assert collection.raw_data["total_records"] == 3  # 3 items in list
