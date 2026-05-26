"""Unit tests for collect_hourly_metrics — specifically _build_dashboard_sync_hook."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from apps.tasks.collectors.collect_hourly_metrics import _build_dashboard_sync_hook


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal DataFrame matching the unified_jobs_dashboard schema."""
    defaults = {
        "id": 1,
        "name": "job",
        "unified_job_template_id": 10,
        "organization_id": 1,
        "organization_name": "Org",
        "started": datetime(2024, 1, 1, tzinfo=UTC),
        "finished": datetime(2024, 1, 1, 1, tzinfo=UTC),
        "status": "successful",
        "elapsed": 60.0,
        "launched_by_id": 5,
        "launched_by_username": "user",
        "project_id": 2,
        "project_name": "Project",
        "created": datetime(2024, 1, 1, tzinfo=UTC),
        "modified": datetime(2024, 1, 1, tzinfo=UTC),
        "label_ids": None,
        "num_hosts": 3,
        "launch_type": "manual",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


HOUR_TS = datetime(2024, 1, 1, tzinfo=UTC)

# Both are lazy imports inside function bodies, so patch at the source module.
FEATURE_FLAG_PATH = "apps.tasks.task_groups.get_feature_enabled_from_db"
TASK_MODEL_PATH = "apps.tasks.models.Task"


@pytest.mark.unit
class TestBuildDashboardSyncHook:
    """Tests for _build_dashboard_sync_hook and its returned inner hook."""

    def test_returns_none_when_feature_disabled(self):
        """When DASHBOARD_COLLECTION is off, the builder returns None."""
        with patch(FEATURE_FLAG_PATH, return_value=False):
            result = _build_dashboard_sync_hook(HOUR_TS)
        assert result is None

    def test_returns_callable_when_feature_enabled(self):
        """When DASHBOARD_COLLECTION is on, the builder returns a callable hook."""
        with patch(FEATURE_FLAG_PATH, return_value=True):
            hook = _build_dashboard_sync_hook(HOUR_TS)
        assert callable(hook)

    def _enabled_hook(self):
        with patch(FEATURE_FLAG_PATH, return_value=True):
            return _build_dashboard_sync_hook(HOUR_TS)

    def test_hook_returns_early_when_raw_data_none(self):
        """hook(None) exits immediately without touching Task."""
        hook = self._enabled_hook()
        with patch(TASK_MODEL_PATH) as mock_task:
            hook(None)
        mock_task.objects.get_or_create.assert_not_called()

    def test_hook_returns_early_when_dataframe_empty(self):
        """hook(empty_df) exits without creating a Task."""
        hook = self._enabled_hook()
        with patch(TASK_MODEL_PATH) as mock_task:
            hook(pd.DataFrame())
        mock_task.objects.get_or_create.assert_not_called()

    def test_hook_returns_early_when_no_terminal_jobs(self):
        """If all jobs are pending/running or are sync launches, no Task is created."""
        df = _make_df(
            [
                {"status": "running", "launch_type": "manual"},
                {"id": 2, "status": "successful", "launch_type": "sync"},
            ]
        )
        hook = self._enabled_hook()
        with patch(TASK_MODEL_PATH) as mock_task:
            hook(df)
        mock_task.objects.get_or_create.assert_not_called()

    def test_hook_creates_task_for_terminal_non_sync_jobs(self):
        """Terminal non-sync jobs cause get_or_create to be called."""
        df = _make_df(
            [
                {"status": "successful", "launch_type": "manual"},
                {"id": 2, "status": "failed", "launch_type": "scheduled"},
            ]
        )
        hook = self._enabled_hook()
        with patch(TASK_MODEL_PATH) as mock_task:
            mock_task.objects.get_or_create.return_value = (MagicMock(), True)
            hook(df)
        mock_task.objects.get_or_create.assert_called_once()
        call_kwargs = mock_task.objects.get_or_create.call_args[1]
        assert call_kwargs["defaults"]["function_name"] == "sync_dashboard_job_records"

    def test_hook_serialises_datetime_fields_to_iso(self):
        """Datetime columns are converted to ISO strings before being stored in task_data."""
        started = datetime(2024, 1, 15, 9, 0, tzinfo=UTC)
        df = _make_df([{"status": "successful", "launch_type": "manual", "started": started}])
        hook = self._enabled_hook()
        with patch(TASK_MODEL_PATH) as mock_task:
            mock_task.objects.get_or_create.return_value = (MagicMock(), True)
            hook(df)
        task_data = mock_task.objects.get_or_create.call_args[1]["defaults"]["task_data"]
        raw_jobs = task_data["raw_jobs"]
        assert raw_jobs[0]["started"] == started.isoformat()

    def test_hook_converts_num_hosts_to_int(self):
        """num_hosts is cast to int if not None."""
        df = _make_df([{"status": "successful", "launch_type": "manual", "num_hosts": 7.0}])
        hook = self._enabled_hook()
        with patch(TASK_MODEL_PATH) as mock_task:
            mock_task.objects.get_or_create.return_value = (MagicMock(), True)
            hook(df)
        task_data = mock_task.objects.get_or_create.call_args[1]["defaults"]["task_data"]
        assert task_data["raw_jobs"][0]["num_hosts"] == 7
        assert isinstance(task_data["raw_jobs"][0]["num_hosts"], int)


@pytest.mark.unit
class TestGenericCollectMetricsHook:
    """Tests for the post_collect_hook try/except block in generic_collect_metrics."""

    def _make_registry(self):
        collector = MagicMock()
        collector.gather.return_value = MagicMock()
        return {
            "test_collector": {
                "collector_func": MagicMock(return_value=collector),
                "rollup_processor": None,
            }
        }

    @patch("apps.tasks.models.HourlyMetricsCollection")
    @patch("apps.tasks.utils.log_task_execution")
    def test_hook_is_called_with_raw_data(self, mock_log, mock_hmc):
        """When post_collect_hook is provided it receives raw_data from gather()."""
        from apps.tasks.utils import generic_collect_metrics

        mock_hmc.objects.update_or_create.return_value = (MagicMock(), True)
        registry = self._make_registry()
        raw_data = registry["test_collector"]["collector_func"].return_value.gather.return_value

        hook = MagicMock()
        generic_collect_metrics(
            collector_type="test_collector",
            collector_registry=registry,
            collection_mode="hourly",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            db_connection=MagicMock(),
            post_collect_hook=hook,
        )
        hook.assert_called_once_with(raw_data)

    @patch("apps.tasks.models.HourlyMetricsCollection")
    @patch("apps.tasks.utils.log_task_execution")
    def test_hook_exception_causes_error_result(self, mock_log, mock_hmc):
        """A hook that raises causes the collection to return an error result (not swallow silently)."""
        from apps.tasks.utils import generic_collect_metrics

        # The re-raised exception is caught by generic_collect_metrics' outer handler,
        # so the function returns error rather than propagating. The outer handler also
        # attempts to write a failed-collection record — suppress any mock side effects.
        mock_hmc.objects.update_or_create.return_value = (MagicMock(), True)
        registry = self._make_registry()

        def bad_hook(_):
            raise RuntimeError("hook failed")

        result = generic_collect_metrics(
            collector_type="test_collector",
            collector_registry=registry,
            collection_mode="hourly",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            db_connection=MagicMock(),
            post_collect_hook=bad_hook,
        )
        assert result.get("status") == "error"

    @patch("apps.tasks.models.HourlyMetricsCollection")
    @patch("apps.tasks.utils.log_task_execution")
    def test_no_hook_skips_hook_block(self, mock_log, mock_hmc):
        """When post_collect_hook=None the hook block is skipped and collection succeeds."""
        from apps.tasks.utils import generic_collect_metrics

        mock_hmc.objects.update_or_create.return_value = (MagicMock(), True)
        registry = self._make_registry()

        result = generic_collect_metrics(
            collector_type="test_collector",
            collector_registry=registry,
            collection_mode="hourly",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            db_connection=MagicMock(),
            post_collect_hook=None,
        )
        assert result.get("status") == "success"
