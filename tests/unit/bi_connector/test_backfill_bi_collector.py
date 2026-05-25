"""
Tests for apps/bi_connector/collectors/backfill_bi_collector.py
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.bi_connector.collectors.backfill_bi_collector import (
    _resume_cursor,
    backfill_bi_collector,
)
from apps.bi_connector.models import CollectionBatch

_COLLECT_HOURLY_PATCH = "apps.bi_connector.collectors.backfill_bi_collector.collect_hourly_metrics"
_COLLECT_SNAPSHOT_PATCH = "apps.bi_connector.collectors.backfill_bi_collector.collect_snapshot_metrics"
_COLLECT_ONE_WINDOW_PATCH = "apps.bi_connector.collectors.backfill_bi_collector._collect_one_window"

SINCE = "2025-03-01T00:00:00Z"
UNTIL = "2025-03-01T03:00:00Z"  # 3 hours
SINCE_DAY = "2025-03-01T00:00:00Z"
UNTIL_DAY = "2025-03-03T00:00:00Z"  # 2 days


@pytest.mark.unit
class TestBackfillBiCollectorValidation:
    """Validation tests that do not require DB access."""

    def test_missing_collector_type_raises(self):
        with pytest.raises(ValueError, match="collector_type is required"):
            backfill_bi_collector({"since": SINCE, "until": UNTIL})

    def test_missing_since_raises(self):
        with pytest.raises(ValueError, match="since and until are required"):
            backfill_bi_collector({"collector_type": "unified_jobs", "until": UNTIL})

    def test_missing_until_raises(self):
        with pytest.raises(ValueError, match="since and until are required"):
            backfill_bi_collector({"collector_type": "unified_jobs", "since": SINCE})

    def test_missing_both_since_and_until_raises(self):
        with pytest.raises(ValueError, match="since and until are required"):
            backfill_bi_collector({"collector_type": "unified_jobs"})

    def test_invalid_since_datetime_raises(self):
        with pytest.raises(ValueError, match="Invalid since datetime"):
            backfill_bi_collector({"collector_type": "unified_jobs", "since": "not-a-date", "until": UNTIL})

    def test_invalid_until_datetime_raises(self):
        with pytest.raises(ValueError, match="Invalid until datetime"):
            backfill_bi_collector({"collector_type": "unified_jobs", "since": SINCE, "until": "not-a-date"})

    def test_empty_task_data_raises(self):
        with pytest.raises(ValueError, match="collector_type is required"):
            backfill_bi_collector({})

    def test_none_task_data_raises(self):
        with pytest.raises(ValueError, match="collector_type is required"):
            backfill_bi_collector(None)


@pytest.mark.unit
@pytest.mark.django_db
class TestBackfillBiCollectorExecution:
    """Tests that exercise the collection loop."""

    def test_hourly_collector_iterates_by_hour(self):
        # 3-hour window should call _collect_one_window 3 times
        with patch(_COLLECT_ONE_WINDOW_PATCH) as mock_window:
            result = backfill_bi_collector({"collector_type": "unified_jobs", "since": SINCE, "until": UNTIL})
        assert result["status"] == "success"
        assert mock_window.call_count == 3
        assert result["periods_collected"] == 3
        assert result["collector_type"] == "unified_jobs"

    def test_snapshot_collector_iterates_by_day(self):
        # 2-day window should call _collect_one_window 2 times (snapshot uses 1-day step)
        with patch(_COLLECT_ONE_WINDOW_PATCH) as mock_window:
            result = backfill_bi_collector(
                {"collector_type": "execution_environments", "since": SINCE_DAY, "until": UNTIL_DAY}
            )
        assert result["status"] == "success"
        assert mock_window.call_count == 2

    def test_snapshot_collector_called_with_is_snapshot_true(self):
        captured = []

        def capture_window(is_snapshot, collector_type, current):
            captured.append(is_snapshot)

        with patch(_COLLECT_ONE_WINDOW_PATCH, side_effect=capture_window):
            backfill_bi_collector({"collector_type": "config", "since": SINCE_DAY, "until": UNTIL_DAY})
        assert all(captured), "Expected is_snapshot=True for snapshot collector"

    def test_hourly_collector_called_with_is_snapshot_false(self):
        captured = []

        def capture_window(is_snapshot, collector_type, current):
            captured.append(is_snapshot)

        with patch(_COLLECT_ONE_WINDOW_PATCH, side_effect=capture_window):
            backfill_bi_collector({"collector_type": "unified_jobs", "since": SINCE, "until": UNTIL})
        assert not any(captured), "Expected is_snapshot=False for time-series collector"

    def test_batch_marked_running_and_completed(self):
        batch = CollectionBatch.objects.create(
            collector_type="unified_jobs",
            batch_type="backfill",
            status="pending",
        )
        with patch(_COLLECT_ONE_WINDOW_PATCH):
            backfill_bi_collector(
                {
                    "collector_type": "unified_jobs",
                    "since": SINCE,
                    "until": UNTIL,
                    "batch_id": batch.id,
                }
            )
        batch.refresh_from_db()
        assert batch.status == "completed"
        assert batch.completed_at is not None

    def test_batch_marked_failed_on_exception(self):
        batch = CollectionBatch.objects.create(
            collector_type="unified_jobs",
            batch_type="backfill",
            status="pending",
        )
        task_data = {
            "collector_type": "unified_jobs",
            "since": SINCE,
            "until": UNTIL,
            "batch_id": batch.id,
        }
        with (
            patch(_COLLECT_ONE_WINDOW_PATCH, side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError, match="boom"),
        ):
            backfill_bi_collector(task_data)
        batch.refresh_from_db()
        assert batch.status == "failed"
        assert "boom" in batch.error_message

    def test_batch_records_imported_incremented(self):
        batch = CollectionBatch.objects.create(
            collector_type="unified_jobs",
            batch_type="backfill",
            status="pending",
        )
        with patch(_COLLECT_ONE_WINDOW_PATCH):
            backfill_bi_collector(
                {
                    "collector_type": "unified_jobs",
                    "since": SINCE,
                    "until": UNTIL,
                    "batch_id": batch.id,
                }
            )
        batch.refresh_from_db()
        # 3 hourly windows → records_imported incremented 3 times
        assert batch.records_imported == 3

    def test_resume_from_cursor(self):
        """When batch has a cursor, collection starts from last_committed."""
        # Resume from hour 2, so only 1 hour remains in the 3-hour window
        batch = CollectionBatch.objects.create(
            collector_type="unified_jobs",
            batch_type="backfill",
            status="pending",
            cursor={"last_committed": "2025-03-01T02:00:00+00:00"},
        )
        with patch(_COLLECT_ONE_WINDOW_PATCH) as mock_window:
            backfill_bi_collector(
                {
                    "collector_type": "unified_jobs",
                    "since": SINCE,
                    "until": UNTIL,
                    "batch_id": batch.id,
                }
            )
        # Only 1 hour from 02:00 to 03:00 should be collected
        assert mock_window.call_count == 1

    def test_no_batch_id_still_runs_successfully(self):
        with patch(_COLLECT_ONE_WINDOW_PATCH) as mock_window:
            result = backfill_bi_collector({"collector_type": "unified_jobs", "since": SINCE, "until": UNTIL})
        assert result["status"] == "success"
        assert mock_window.call_count == 3


@pytest.mark.unit
class TestResumeCursor:
    """Unit tests for the _resume_cursor helper."""

    def _make_since(self):
        from apps.tasks.utils import parse_datetime_string

        return parse_datetime_string("2025-03-01T00:00:00Z")

    def test_returns_since_when_no_batch(self):
        since = self._make_since()
        result = _resume_cursor(None, since)
        assert result == since

    def test_returns_since_when_batch_has_no_cursor(self):
        since = self._make_since()
        batch = MagicMock()
        batch.cursor = {}
        result = _resume_cursor(batch, since)
        assert result == since

    def test_returns_since_when_cursor_missing_last_committed(self):
        since = self._make_since()
        batch = MagicMock()
        batch.cursor = {"other_key": "value"}
        result = _resume_cursor(batch, since)
        assert result == since

    def test_returns_cursor_value_when_set(self):
        since = self._make_since()
        batch = MagicMock()
        batch.cursor = {"last_committed": "2025-03-01T02:00:00+00:00"}
        result = _resume_cursor(batch, since)
        # Result should be the parsed cursor datetime, not since
        assert result != since
        assert result.hour == 2

    def test_returns_since_when_cursor_value_is_invalid(self):
        since = self._make_since()
        batch = MagicMock()
        batch.cursor = {"last_committed": "not-a-datetime"}
        result = _resume_cursor(batch, since)
        assert result == since
