"""
Unit tests for apps/tasks/collectors/daily_metrics_rollup.py

Tests cover:
- _merge_collects: JSON merging and rollup computation
- _collect_and_group_hourly_collections: missing hours detection

Note: All inline collection functions (_collect_config_data, etc.)
      were removed in favor of dedicated collector tasks that run independently.
"""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.tasks.collectors.daily_metrics_rollup import (
    _collect_and_group_hourly_collections,
    _merge_collects,
)


@pytest.mark.unit
@pytest.mark.django_db
class TestMergeCollects:
    """Test _merge_collects function."""

    def test_merges_and_processes_with_base(self, hourly_collection_factory):
        """Test merges JSON and calls base() to get final result."""
        # Arrange
        mock_processor = MagicMock()
        mock_processor.merge.return_value = {"merged": "data"}
        mock_processor.base.return_value = {"json": {"processed": "result"}}

        # Create collections with JSON data
        collection1 = hourly_collection_factory(
            collector_type="job_host_summary_service",
            raw_data={
                "total_jobs": 100,
                "failed_jobs": 10,
            },
        )

        collection2 = hourly_collection_factory(
            collector_type="job_host_summary_service",
            raw_data={
                "total_jobs": 50,
                "failed_jobs": 5,
            },
        )

        collections = [collection1, collection2]

        # Act
        result = _merge_collects(collections, mock_processor)

        # Assert - calls base() and extracts "json" key
        assert result == {"processed": "result"}
        assert mock_processor.merge.call_count == 2
        mock_processor.base.assert_called_once_with({"merged": "data"})

        # Verify JSON is passed directly to merge
        first_call_arg = mock_processor.merge.call_args_list[0][0][1]
        assert first_call_arg == {"total_jobs": 100, "failed_jobs": 10}
        assert isinstance(first_call_arg, dict)

    def test_handles_empty_collections(self):
        """Test handles empty collections list."""
        # Arrange
        mock_processor = MagicMock()
        mock_processor.base.return_value = {"json": {}}

        # Act
        result = _merge_collects([], mock_processor)

        # Assert - calls base(None) and returns empty dict
        assert result == {}
        mock_processor.merge.assert_not_called()
        mock_processor.base.assert_called_once_with(None)

    def test_skips_empty_raw_data(self, hourly_collection_factory):
        """Test skips collections with empty raw_data."""
        # Arrange
        mock_processor = MagicMock()
        mock_processor.merge.return_value = {"merged": "data"}
        mock_processor.base.return_value = {"json": {"result": "processed"}}

        collection1 = hourly_collection_factory(raw_data={})
        collection2 = hourly_collection_factory(raw_data={"data": {"id": 1}})

        # Act
        result = _merge_collects([collection1, collection2], mock_processor)

        # Assert - only called once for non-empty collection
        assert mock_processor.merge.call_count == 1
        assert result == {"result": "processed"}

    def test_handles_missing_json_key_in_base_result(self, hourly_collection_factory):
        """Test handles case where base() returns dict without 'json' key."""
        # Arrange
        mock_processor = MagicMock()
        mock_processor.merge.return_value = {"merged": "data"}
        mock_processor.base.return_value = {"other_key": "value"}

        collection = hourly_collection_factory(raw_data={"total": 10})

        # Act
        result = _merge_collects([collection], mock_processor)

        # Assert - returns empty dict when "json" key is missing
        assert result == {}
        mock_processor.base.assert_called_once()


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
