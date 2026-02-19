"""
Unit tests for apps/tasks/collectors/daily_metrics_rollup.py

Tests cover:
- _merge_rollup_dataframes: DataFrame restoration from JSON
- _aggregate_collector_rollups: rollup computation with merged data
- _collect_and_group_hourly_collections: missing hours detection

Note: All inline collection functions (_collect_config_data, etc.)
      were removed in favor of dedicated collector tasks that run independently.
"""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest
from django.utils import timezone

from apps.tasks.collectors.daily_metrics_rollup import (
    _aggregate_collector_rollups,
    _collect_and_group_hourly_collections,
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
            collector_type="job_host_summary_service",
            raw_data={
                "aggregated": [
                    {"id": 1, "name": "job1"},
                    {"id": 2, "name": "job2"},
                ],
                "total": 100,
            },
        )

        collection2 = hourly_collection_factory(
            collector_type="job_host_summary_service",
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
                collector_type="job_host_summary_service",
                collection_timestamp=base_time + timedelta(hours=hour),
                status="collected",
            )

        # Act
        collections_by_type, _, _ = _collect_and_group_hourly_collections(summary_date)

        # Assert
        assert "job_host_summary_service" in collections_by_type
        assert len(collections_by_type["job_host_summary_service"]) == 3

    def test_groups_collections_by_type(self, hourly_collection_factory):
        """Test groups collections by collector_type."""
        # Arrange
        summary_date = date(2024, 1, 15)
        base_time = timezone.make_aware(datetime.combine(summary_date, datetime.min.time()))

        # Create different collector types
        hourly_collection_factory(
            collector_type="job_host_summary_service",
            collection_timestamp=base_time,
            status="collected",
        )

        # Act
        collections_by_type, _, _ = _collect_and_group_hourly_collections(summary_date)

        # Assert
        assert len(collections_by_type) == 1
        assert "job_host_summary_service" in collections_by_type
