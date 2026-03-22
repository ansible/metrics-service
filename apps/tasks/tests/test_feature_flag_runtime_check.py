"""
Tests for runtime feature flag checking in task scheduler.

The implementation reads _feature_flag from task.task_data (live DB) at execution time,
then routes through _execute_database_task. All DB access is mocked here so these tests
do not require @pytest.mark.django_db.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.tasks.cron_scheduler import UnifiedTaskScheduler


def _make_mock_task(task_id=42, task_data=None):
    """Return a MagicMock resembling a Task DB object."""
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.task_data = task_data if task_data is not None else {}
    return mock_task


@pytest.mark.unit
class TestFeatureFlagRuntimeCheck:
    """Test runtime feature flag checking for task execution.

    _execute_scheduled_task reads _feature_flag from the live DB task record so that
    toggling the flag takes effect immediately without restarting the scheduler or
    re-running init-system-tasks.
    """

    @patch.object(UnifiedTaskScheduler, "_execute_database_task")
    @patch("apps.tasks.task_groups.get_feature_enabled_from_db")
    @patch("apps.tasks.models.Task")
    def test_task_executes_when_feature_flag_enabled(self, mock_task_cls, mock_get_feature, mock_execute_db):
        """Task is routed to _execute_database_task when its feature flag is enabled."""
        mock_get_feature.return_value = True
        mock_task_cls.objects.filter.return_value.first.return_value = _make_mock_task(
            task_id=1, task_data={"_feature_flag": "ANONYMIZED_DATA_COLLECTION"}
        )

        scheduler = UnifiedTaskScheduler()
        scheduler._execute_scheduled_task(
            task_id="test_task",
            function_name="hello_world",
            args={},
        )

        mock_get_feature.assert_called_once_with("ANONYMIZED_DATA_COLLECTION")
        mock_execute_db.assert_called_once_with(1)

    @patch.object(UnifiedTaskScheduler, "_execute_database_task")
    @patch("apps.tasks.task_groups.get_feature_enabled_from_db")
    @patch("apps.tasks.models.Task")
    def test_task_skips_when_feature_flag_disabled(self, mock_task_cls, mock_get_feature, mock_execute_db):
        """Task is NOT dispatched when its feature flag is disabled in the DB."""
        mock_get_feature.return_value = False
        mock_task_cls.objects.filter.return_value.first.return_value = _make_mock_task(
            task_data={"_feature_flag": "ANONYMIZED_DATA_COLLECTION"}
        )

        scheduler = UnifiedTaskScheduler()
        scheduler._execute_scheduled_task(
            task_id="test_task",
            function_name="hello_world",
            args={},
        )

        mock_get_feature.assert_called_once_with("ANONYMIZED_DATA_COLLECTION")
        mock_execute_db.assert_not_called()

    @patch.object(UnifiedTaskScheduler, "_execute_database_task")
    @patch("apps.tasks.models.Task")
    def test_task_executes_when_no_feature_flag(self, mock_task_cls, mock_execute_db):
        """Task executes without a feature flag check when task_data has no _feature_flag."""
        mock_task = _make_mock_task(task_id=5, task_data={})
        mock_task_cls.objects.filter.return_value.first.return_value = mock_task

        scheduler = UnifiedTaskScheduler()
        scheduler._execute_scheduled_task(task_id="test_task", function_name="hello_world", args={})

        mock_execute_db.assert_called_once_with(5)

    def test_get_all_enabled_tasks_includes_feature_flag(self):
        """get_all_enabled_tasks propagates the group's feature_flag into each task config."""
        from apps.tasks.task_groups import METRICS_COLLECTION_GROUP, get_all_enabled_tasks

        all_tasks = get_all_enabled_tasks()

        for task in METRICS_COLLECTION_GROUP.tasks:
            task_id = task["task_id"]
            if task_id in all_tasks:
                assert "feature_flag" in all_tasks[task_id]
                assert all_tasks[task_id]["feature_flag"] == "ANONYMIZED_DATA_COLLECTION"

    @patch.object(UnifiedTaskScheduler, "_execute_database_task")
    @patch("apps.tasks.task_groups.get_feature_enabled_from_db")
    @patch("apps.tasks.models.Task")
    def test_feature_flag_checked_at_execution_time(self, mock_task_cls, mock_get_feature, mock_execute_db):
        """Flag is re-read from DB on each fire so runtime changes take effect immediately."""
        mock_task_cls.objects.filter.return_value.first.return_value = _make_mock_task(
            task_id=10, task_data={"_feature_flag": "ANONYMIZED_DATA_COLLECTION"}
        )
        scheduler = UnifiedTaskScheduler()

        # First fire — flag enabled
        mock_get_feature.return_value = True
        scheduler._execute_scheduled_task(task_id="test_task", function_name="hello_world", args={})
        assert mock_execute_db.call_count == 1

        # Second fire — flag disabled at runtime, no restart needed
        mock_get_feature.return_value = False
        scheduler._execute_scheduled_task(task_id="test_task", function_name="hello_world", args={})
        assert mock_execute_db.call_count == 1  # Not incremented

    @patch.object(UnifiedTaskScheduler, "_execute_database_task")
    @patch("apps.tasks.task_groups.get_feature_enabled_from_db")
    @patch("apps.tasks.models.Task")
    def test_feature_flag_error_prevents_execution(self, mock_task_cls, mock_get_feature, mock_execute_db):
        """Errors reading the feature flag are caught by the outer try/except; task is not dispatched."""
        mock_get_feature.side_effect = Exception("Database error")
        mock_task_cls.objects.filter.return_value.first.return_value = _make_mock_task(
            task_data={"_feature_flag": "ANONYMIZED_DATA_COLLECTION"}
        )

        scheduler = UnifiedTaskScheduler()
        scheduler._execute_scheduled_task(
            task_id="test_task",
            function_name="hello_world",
            args={},
        )

        mock_execute_db.assert_not_called()
