"""
Tests for runtime feature flag checking in task scheduler.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from apps.tasks.cron_scheduler import UnifiedTaskScheduler


@pytest.mark.unit
class TestFeatureFlagRuntimeCheck:
    """Test runtime feature flag checking for task execution."""

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.task_groups.get_feature_enabled_from_db")
    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    @patch("dispatcherd.publish.submit_task")
    def test_task_executes_when_feature_flag_enabled(
        self, mock_submit, mock_ensure, mock_get_feature, mock_get_tasks
    ):
        """Test that task executes when its feature flag is enabled."""
        mock_get_tasks.return_value = {}
        mock_get_feature.return_value = True  # Feature is enabled

        scheduler = UnifiedTaskScheduler()

        # Execute a task with a feature flag
        scheduler._execute_scheduled_task(
            task_id="test_task",
            function_name="hello_world",
            args={},
            feature_flag="METRICS_COLLECTION_ENABLED",
        )

        # Verify task was submitted
        mock_submit.assert_called_once()

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.task_groups.get_feature_enabled_from_db")
    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    @patch("dispatcherd.publish.submit_task")
    def test_task_skips_when_feature_flag_disabled(
        self, mock_submit, mock_ensure, mock_get_feature, mock_get_tasks
    ):
        """Test that task is skipped when its feature flag is disabled."""
        mock_get_tasks.return_value = {}
        mock_get_feature.return_value = False  # Feature is disabled

        scheduler = UnifiedTaskScheduler()

        # Execute a task with a feature flag
        scheduler._execute_scheduled_task(
            task_id="test_task",
            function_name="hello_world",
            args={},
            feature_flag="METRICS_COLLECTION_ENABLED",
        )

        # Verify task was NOT submitted
        mock_submit.assert_not_called()

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    @patch("dispatcherd.publish.submit_task")
    def test_task_executes_when_no_feature_flag(self, mock_submit, mock_ensure, mock_get_tasks):
        """Test that task executes normally when no feature flag is specified."""
        mock_get_tasks.return_value = {}

        scheduler = UnifiedTaskScheduler()

        # Execute a task without a feature flag
        scheduler._execute_scheduled_task(task_id="test_task", function_name="hello_world", args={}, feature_flag=None)

        # Verify task was submitted
        mock_submit.assert_called_once()

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    def test_get_all_enabled_tasks_includes_feature_flag(self, mock_get_tasks):
        """Test that get_all_enabled_tasks includes feature_flag in task configs."""
        from apps.tasks.task_groups import get_all_enabled_tasks, HOURLY_METRICS_GROUP

        # Get all enabled tasks
        all_tasks = get_all_enabled_tasks()

        # Check that hourly metrics tasks have the feature flag
        hourly_task_ids = [task["task_id"] for task in HOURLY_METRICS_GROUP.tasks]

        for task_id in hourly_task_ids:
            if task_id in all_tasks:
                assert "feature_flag" in all_tasks[task_id]
                assert all_tasks[task_id]["feature_flag"] == "METRICS_COLLECTION_ENABLED"

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.task_groups.get_feature_enabled_from_db")
    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    @patch("dispatcherd.publish.submit_task")
    def test_feature_flag_checked_at_execution_time(
        self, mock_submit, mock_ensure, mock_get_feature, mock_get_tasks
    ):
        """Test that feature flag is checked at execution time, not at registration."""
        mock_get_tasks.return_value = {}

        scheduler = UnifiedTaskScheduler()

        # First execution - feature enabled
        mock_get_feature.return_value = True
        scheduler._execute_scheduled_task(
            task_id="test_task",
            function_name="hello_world",
            args={},
            feature_flag="METRICS_COLLECTION_ENABLED",
        )

        # Verify task was submitted
        assert mock_submit.call_count == 1

        # Second execution - feature disabled (flag changed at runtime)
        mock_get_feature.return_value = False
        scheduler._execute_scheduled_task(
            task_id="test_task",
            function_name="hello_world",
            args={},
            feature_flag="METRICS_COLLECTION_ENABLED",
        )

        # Verify task was NOT submitted the second time
        assert mock_submit.call_count == 1  # Still 1, not 2

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.task_groups.get_feature_enabled_from_db")
    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    @patch("dispatcherd.publish.submit_task")
    def test_feature_flag_error_prevents_execution(
        self, mock_submit, mock_ensure, mock_get_feature, mock_get_tasks
    ):
        """Test that errors checking feature flag prevent task execution."""
        mock_get_tasks.return_value = {}
        mock_get_feature.side_effect = Exception("Database error")

        scheduler = UnifiedTaskScheduler()

        # Execute task - should handle error gracefully
        scheduler._execute_scheduled_task(
            task_id="test_task",
            function_name="hello_world",
            args={},
            feature_flag="METRICS_COLLECTION_ENABLED",
        )

        # Verify task was NOT submitted due to error
        mock_submit.assert_not_called()
