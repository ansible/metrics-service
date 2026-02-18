"""
Unit tests for apps/tasks/collectors/daily_metrics_rollup.py

Tests cover:
- _merge_rollup_dataframes: DataFrame restoration from JSON
- _aggregate_collector_rollups: rollup computation with merged data
- _collect_and_group_hourly_collections: missing hours detection
- _collect_config_data: config collection with error handling
- _collect_main_host_data: both existing and fresh collection paths
- _collect_unified_jobs_data: jobs collection with error handling
- _collect_execution_environments_data: EE collection with error handling
"""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from django.utils import timezone

from apps.tasks.collectors.daily_metrics_rollup import (
    _aggregate_collector_rollups,
    _collect_and_group_hourly_collections,
    _collect_config_data,
    _collect_execution_environments_data,
    _collect_main_host_data,
    _collect_unified_jobs_data,
    _merge_rollup_dataframes,
)


@pytest.mark.unit
@pytest.mark.django_db
class TestMergeRollupDataframes:
    """Test _merge_rollup_dataframes function."""

    def test_restores_dataframes_from_json(self, hourly_collection_factory):
        """Test restores pandas DataFrames from JSON list of dicts."""
        # Arrange
        mock_processor = MagicMock()
        mock_processor.merge.return_value = {"merged": "data"}

        # Create collections with DataFrame data (stored as list of dicts)
        collection1 = hourly_collection_factory(
            collector_type="job_host_summary",
            raw_data={
                "aggregated": [
                    {"id": 1, "name": "job1"},
                    {"id": 2, "name": "job2"},
                ],
                "total": 100,
            },
        )

        collection2 = hourly_collection_factory(
            collector_type="job_host_summary",
            raw_data={
                "aggregated": [
                    {"id": 3, "name": "job3"},
                ],
                "total": 50,
            },
        )

        collections = [collection1, collection2]

        # Act
        result = _merge_rollup_dataframes(collections, mock_processor)

        # Assert
        assert result == {"merged": "data"}
        assert mock_processor.merge.call_count == 2

        # Verify first call had DataFrame restored
        first_call_arg = mock_processor.merge.call_args_list[0][0][1]
        assert isinstance(first_call_arg["aggregated"], pd.DataFrame)
        assert len(first_call_arg["aggregated"]) == 2
        assert first_call_arg["total"] == 100

    def test_preserves_scalar_values(self, hourly_collection_factory):
        """Test preserves scalar values (totals, etc.) without conversion."""
        # Arrange
        mock_processor = MagicMock()
        mock_processor.merge.return_value = {"result": "merged"}

        collection = hourly_collection_factory(
            raw_data={
                "total": 100,
                "count": 5,
                "average": 20.5,
            }
        )

        # Act
        _merge_rollup_dataframes([collection], mock_processor)

        # Assert
        call_arg = mock_processor.merge.call_args[0][1]
        assert call_arg["total"] == 100
        assert call_arg["count"] == 5
        assert call_arg["average"] == pytest.approx(20.5)

    def test_handles_empty_collections(self):
        """Test handles empty collections list."""
        # Arrange
        mock_processor = MagicMock()

        # Act
        result = _merge_rollup_dataframes([], mock_processor)

        # Assert
        assert result is None
        mock_processor.merge.assert_not_called()

    def test_skips_empty_raw_data(self, hourly_collection_factory):
        """Test skips collections with empty raw_data."""
        # Arrange
        mock_processor = MagicMock()
        mock_processor.merge.return_value = {"merged": "data"}

        collection1 = hourly_collection_factory(raw_data={})
        collection2 = hourly_collection_factory(raw_data={"data": [{"id": 1}]})

        # Act
        _merge_rollup_dataframes([collection1, collection2], mock_processor)

        # Assert - only called once for non-empty collection
        assert mock_processor.merge.call_count == 1


@pytest.mark.unit
@pytest.mark.django_db
class TestAggregateCollectorRollups:
    """Test _aggregate_collector_rollups function."""

    def test_computes_rollup_when_merged_data_exists(self, hourly_collection_factory):
        """Test computes final rollup when merged data is not None."""
        # Arrange
        mock_processor = MagicMock()
        mock_processor.merge.return_value = {"aggregated_df": pd.DataFrame({"id": [1, 2]})}
        mock_processor.base.return_value = {
            "json": {"total": 100, "count": 2},
            "rollup": {"data": "rollup"},
        }

        collection = hourly_collection_factory(raw_data={"data": [{"id": 1}], "total": 10})

        # Act
        result = _aggregate_collector_rollups([collection], mock_processor)

        # Assert
        assert result == {"total": 100, "count": 2}
        mock_processor.base.assert_called_once()

    def test_returns_empty_dict_when_no_merged_data(self):
        """Test returns empty dict when merged_rollup is None."""
        # Arrange
        mock_processor = MagicMock()
        mock_processor.merge.return_value = None

        # Act
        result = _aggregate_collector_rollups([], mock_processor)

        # Assert
        assert result == {}
        mock_processor.base.assert_not_called()


@pytest.mark.unit
@pytest.mark.django_db
class TestCollectAndGroupHourlyCollections:
    """Test _collect_and_group_hourly_collections function."""

    def test_detects_missing_hours(self, hourly_collection_factory):
        """Test detects missing hours in collections."""
        # Arrange
        summary_date = date(2024, 1, 15)
        base_time = timezone.make_aware(datetime.combine(summary_date, datetime.min.time()))

        # Create collections for only hours 0, 1, 2 (missing 3-23)
        for hour in [0, 1, 2]:
            hourly_collection_factory(
                collector_type="job_host_summary",
                collection_timestamp=base_time + timedelta(hours=hour),
                status="collected",
            )

        # Act
        collections_by_type, _, _ = _collect_and_group_hourly_collections(summary_date)

        # Assert
        assert "job_host_summary" in collections_by_type
        assert len(collections_by_type["job_host_summary"]) == 3

    def test_groups_collections_by_type(self, hourly_collection_factory):
        """Test groups collections by collector_type."""
        # Arrange
        summary_date = date(2024, 1, 15)
        base_time = timezone.make_aware(datetime.combine(summary_date, datetime.min.time()))

        # Create different collector types
        hourly_collection_factory(
            collector_type="job_host_summary",
            collection_timestamp=base_time,
            status="collected",
        )
        hourly_collection_factory(
            collector_type="main_jobevent",
            collection_timestamp=base_time,
            status="collected",
        )
        hourly_collection_factory(
            collector_type="main_host",
            collection_timestamp=base_time,
            status="collected",
        )

        # Act
        collections_by_type, _, _ = _collect_and_group_hourly_collections(summary_date)

        # Assert
        assert len(collections_by_type) == 3
        assert "job_host_summary" in collections_by_type
        assert "main_jobevent" in collections_by_type
        assert "main_host" in collections_by_type


@pytest.mark.unit
@pytest.mark.django_db
class TestCollectConfigData:
    """Test _collect_config_data function."""

    @patch("apps.tasks.collectors.daily_metrics_rollup.get_db_connection")
    @patch("metrics_utility.library.collectors.controller.config")
    def test_collects_config_successfully(self, mock_config_class, mock_get_db):
        """Test successfully collects config data."""
        # Arrange
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_collector = MagicMock()
        mock_collector.gather.return_value = {"version": "1.0", "settings": {}}
        mock_config_class.return_value = mock_collector

        # Act
        result = _collect_config_data("awx")

        # Assert
        assert result == {"version": "1.0", "settings": {}}
        mock_config_class.assert_called_once_with(db=mock_db)

    @patch("apps.tasks.collectors.daily_metrics_rollup.get_db_connection")
    @patch("metrics_utility.library.collectors.controller.config")
    def test_handles_config_collection_error(self, mock_config_class, mock_get_db):
        """Test handles error during config collection."""
        # Arrange
        mock_config_class.side_effect = Exception("Config collection failed")

        # Act
        result = _collect_config_data("awx")

        # Assert
        assert "error" in result
        assert "Config collection failed" in result["error"]


@pytest.mark.unit
@pytest.mark.django_db
class TestCollectMainHostData:
    """Test _collect_main_host_data function."""

    def test_uses_latest_main_host_from_collections(self, hourly_collection_factory):
        """Test uses latest main_host snapshot from existing collections."""
        # Arrange
        summary_date = date(2024, 1, 15)
        base_time = timezone.make_aware(datetime.combine(summary_date, datetime.min.time()))

        # Create multiple main_host collections
        hourly_collection_factory(
            collector_type="main_host",
            collection_timestamp=base_time,
            raw_data={"records": [{"id": 1}], "total_records": 1},
        )
        latest = hourly_collection_factory(
            collector_type="main_host",
            collection_timestamp=base_time + timedelta(hours=23),
            raw_data={"records": [{"id": 2}], "total_records": 1},
        )

        collections_by_type = {
            "main_host": [latest]  # Simulating grouped collections
        }

        # Act
        result = _collect_main_host_data(collections_by_type, "awx")

        # Assert
        assert result == {"records": [{"id": 2}], "total_records": 1}

    @patch("apps.tasks.collectors.daily_metrics_rollup.get_db_connection")
    @patch("metrics_utility.library.collectors.controller.main_host")
    def test_collects_fresh_main_host_when_no_collections(self, mock_main_host_class, mock_get_db):
        """Test collects fresh main_host data when not in hourly collections."""
        # Arrange
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_collector = MagicMock()
        mock_collector.gather.return_value = [{"hostname": "host1"}, {"hostname": "host2"}]
        mock_main_host_class.return_value = mock_collector

        collections_by_type = {}  # No main_host collections

        # Act
        result = _collect_main_host_data(collections_by_type, "awx")

        # Assert
        assert result == {"records": [{"hostname": "host1"}, {"hostname": "host2"}], "total_records": 2}
        mock_main_host_class.assert_called_once_with(db=mock_db)

    @patch("apps.tasks.collectors.daily_metrics_rollup.get_db_connection")
    @patch("metrics_utility.library.collectors.controller.main_host")
    def test_handles_main_host_collection_error(self, mock_main_host_class, mock_get_db):
        """Test handles error during main_host collection."""
        # Arrange
        mock_main_host_class.side_effect = Exception("Main host collection failed")

        collections_by_type = {}

        # Act
        result = _collect_main_host_data(collections_by_type, "awx")

        # Assert
        assert "error" in result
        assert "Main host collection failed" in result["error"]


@pytest.mark.unit
@pytest.mark.django_db
class TestCollectUnifiedJobsData:
    """Test _collect_unified_jobs_data function."""

    @patch("apps.tasks.collectors.daily_metrics_rollup.get_db_connection")
    @patch("metrics_utility.library.collectors.controller.unified_jobs")
    @patch("apps.tasks.collectors.daily_metrics_rollup._compute_rollup_from_dataframe")
    def test_collects_unified_jobs_successfully(self, mock_compute_rollup, mock_unified_jobs_class, mock_get_db):
        """Test successfully collects unified_jobs data."""
        # Arrange
        summary_date = date(2024, 1, 15)
        start_datetime = timezone.make_aware(datetime.combine(summary_date, datetime.min.time()))
        end_datetime = start_datetime + timedelta(days=1)

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_collector = MagicMock()
        mock_df = pd.DataFrame({"job_id": [1, 2, 3]})
        mock_collector.gather.return_value = mock_df
        mock_unified_jobs_class.return_value = mock_collector

        mock_compute_rollup.return_value = {
            "json": {"jobs_total": 3, "jobs_by_template": []},
            "rollup": {},
        }

        # Act
        result = _collect_unified_jobs_data(summary_date, start_datetime, end_datetime, "awx")

        # Assert
        assert result == {"jobs_total": 3, "jobs_by_template": []}
        mock_unified_jobs_class.assert_called_once_with(db=mock_db, since=start_datetime, until=end_datetime)

    @patch("apps.tasks.collectors.daily_metrics_rollup.get_db_connection")
    @patch("metrics_utility.library.collectors.controller.unified_jobs")
    def test_handles_unified_jobs_collection_error(self, mock_unified_jobs_class, mock_get_db):
        """Test handles error during unified_jobs collection."""
        # Arrange
        summary_date = date(2024, 1, 15)
        start_datetime = timezone.make_aware(datetime.combine(summary_date, datetime.min.time()))
        end_datetime = start_datetime + timedelta(days=1)

        mock_unified_jobs_class.side_effect = Exception("Unified jobs collection failed")

        # Act
        result = _collect_unified_jobs_data(summary_date, start_datetime, end_datetime, "awx")

        # Assert
        assert "error" in result
        assert "Unified jobs collection failed" in result["error"]


@pytest.mark.unit
@pytest.mark.django_db
class TestCollectExecutionEnvironmentsData:
    """Test _collect_execution_environments_data function."""

    @patch("apps.tasks.collectors.daily_metrics_rollup.get_db_connection")
    @patch("metrics_utility.library.collectors.controller.execution_environments")
    @patch("apps.tasks.collectors.daily_metrics_rollup._compute_rollup_from_dataframe")
    def test_collects_execution_environments_successfully(self, mock_compute_rollup, mock_ee_class, mock_get_db):
        """Test successfully collects execution_environments data."""
        # Arrange
        summary_date = date(2024, 1, 15)

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        mock_collector = MagicMock()
        mock_df = pd.DataFrame({"ee_id": [1, 2]})
        mock_collector.gather.return_value = mock_df
        mock_ee_class.return_value = mock_collector

        mock_compute_rollup.return_value = {
            "json": {"EE_total": 2, "EE_by_image": []},
            "rollup": {},
        }

        # Act
        result = _collect_execution_environments_data(summary_date, "awx")

        # Assert
        assert result == {"EE_total": 2, "EE_by_image": []}
        mock_ee_class.assert_called_once_with(db=mock_db)

    @patch("apps.tasks.collectors.daily_metrics_rollup.get_db_connection")
    @patch("metrics_utility.library.collectors.controller.execution_environments")
    def test_handles_execution_environments_collection_error(self, mock_ee_class, mock_get_db):
        """Test handles error during execution_environments collection."""
        # Arrange
        summary_date = date(2024, 1, 15)
        mock_ee_class.side_effect = Exception("EE collection failed")

        # Act
        result = _collect_execution_environments_data(summary_date, "awx")

        # Assert
        assert "error" in result
        assert "EE collection failed" in result["error"]
