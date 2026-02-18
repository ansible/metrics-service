"""
Enhanced unit tests for cron_scheduler.py to improve coverage.

Tests cover:
- Feature flag checking in _execute_scheduled_task
- _periodic_database_sync task discovery and routing
- Error handling in _add_database_scheduled_task
- Error handling in _add_database_recurring_task
- Error handling in _execute_database_task
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.tasks.cron_scheduler import UnifiedTaskScheduler


@pytest.mark.unit
@pytest.mark.django_db
class TestExecuteScheduledTaskFeatureFlags:
    """Test feature flag checking in _execute_scheduled_task."""

    @patch("dispatcherd.publish.submit_task")
    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    @patch("apps.tasks.task_groups.get_feature_enabled_from_db")
    def test_skips_task_when_feature_flag_disabled(
        self, mock_get_feature_enabled, mock_ensure_config, mock_submit_task
    ):
        """Test task is skipped when feature flag is disabled."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        mock_get_feature_enabled.return_value = False

        task_id = "test_task"
        function_name = "hello_world"
        args = {"_feature_flag": "ANONYMIZED_DATA_COLLECTION", "message": "test"}

        # Act
        scheduler._execute_scheduled_task(task_id, function_name, args)

        # Assert
        mock_get_feature_enabled.assert_called_once_with("ANONYMIZED_DATA_COLLECTION", False)
        mock_submit_task.assert_not_called()

    @patch("dispatcherd.publish.submit_task")
    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    @patch("apps.tasks.task_groups.get_feature_enabled_from_db")
    def test_executes_task_when_feature_flag_enabled(
        self, mock_get_feature_enabled, mock_ensure_config, mock_submit_task
    ):
        """Test task executes when feature flag is enabled."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        mock_get_feature_enabled.return_value = True

        task_id = "test_task"
        function_name = "hello_world"
        args = {"_feature_flag": "ANONYMIZED_DATA_COLLECTION", "message": "test"}

        # Act
        scheduler._execute_scheduled_task(task_id, function_name, args)

        # Assert
        mock_get_feature_enabled.assert_called_once_with("ANONYMIZED_DATA_COLLECTION", False)
        mock_submit_task.assert_called_once()
        # Verify _feature_flag was removed from args
        call_kwargs = mock_submit_task.call_args.kwargs
        assert "_feature_flag" not in call_kwargs["kwargs"]
        assert call_kwargs["kwargs"]["message"] == "test"

    @patch("dispatcherd.publish.submit_task")
    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    def test_executes_task_when_no_feature_flag(self, mock_ensure_config, mock_submit_task):
        """Test task executes normally when no feature flag is specified."""
        # Arrange
        scheduler = UnifiedTaskScheduler()

        task_id = "test_task"
        function_name = "hello_world"
        args = {"message": "test"}  # No _feature_flag

        # Act
        scheduler._execute_scheduled_task(task_id, function_name, args)

        # Assert
        mock_submit_task.assert_called_once()
        call_kwargs = mock_submit_task.call_args.kwargs
        assert call_kwargs["kwargs"]["message"] == "test"


@pytest.mark.unit
@pytest.mark.django_db
class TestPeriodicDatabaseSync:
    """Test _periodic_database_sync task discovery and routing."""

    @patch("apps.tasks.models.Task")
    @patch.object(UnifiedTaskScheduler, "_execute_database_task")
    def test_discovers_and_executes_immediate_tasks(self, mock_execute, mock_task_model):
        """Test periodic sync discovers new immediate tasks and executes them."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        scheduler.running = True

        mock_immediate_task = MagicMock()
        mock_immediate_task.id = 1
        mock_immediate_task.name = "Immediate Task"
        mock_immediate_task.is_ready_to_run.return_value = True

        mock_task_model.immediate_tasks.return_value = [mock_immediate_task]
        mock_task_model.scheduled_tasks.return_value = []
        mock_task_model.recurring_tasks.return_value = []

        # Act
        scheduler._periodic_database_sync()

        # Assert
        mock_execute.assert_called_once_with(1)
        assert 1 in scheduler._db_task_jobs
        assert scheduler._db_task_jobs[1] == "db_immediate_1"

    @patch("apps.tasks.models.Task")
    @patch.object(UnifiedTaskScheduler, "_add_database_scheduled_task")
    def test_discovers_and_adds_scheduled_tasks(self, mock_add_scheduled, mock_task_model):
        """Test periodic sync discovers new scheduled tasks."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        scheduler.running = True

        mock_scheduled_task = MagicMock()
        mock_scheduled_task.id = 2
        mock_scheduled_task.name = "Scheduled Task"

        mock_task_model.immediate_tasks.return_value = []
        mock_task_model.scheduled_tasks.return_value = [mock_scheduled_task]
        mock_task_model.recurring_tasks.return_value = []

        # Act
        scheduler._periodic_database_sync()

        # Assert
        mock_add_scheduled.assert_called_once_with(mock_scheduled_task)

    @patch("apps.tasks.models.Task")
    @patch.object(UnifiedTaskScheduler, "_add_database_recurring_task")
    def test_discovers_and_adds_recurring_tasks(self, mock_add_recurring, mock_task_model):
        """Test periodic sync discovers new recurring tasks."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        scheduler.running = True

        mock_recurring_task = MagicMock()
        mock_recurring_task.id = 3
        mock_recurring_task.name = "Recurring Task"

        mock_task_model.immediate_tasks.return_value = []
        mock_task_model.scheduled_tasks.return_value = []
        mock_task_model.recurring_tasks.return_value = [mock_recurring_task]

        # Act
        scheduler._periodic_database_sync()

        # Assert
        mock_add_recurring.assert_called_once_with(mock_recurring_task)

    @patch("apps.tasks.models.Task")
    def test_skips_already_tracked_tasks(self, mock_task_model):
        """Test periodic sync skips tasks already in tracking."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        scheduler.running = True
        scheduler._db_task_jobs[2] = "db_task_2"  # Already tracked

        mock_scheduled_task = MagicMock()
        mock_scheduled_task.id = 2
        mock_scheduled_task.name = "Already Tracked Task"

        mock_task_model.immediate_tasks.return_value = []
        mock_task_model.scheduled_tasks.return_value = [mock_scheduled_task]
        mock_task_model.recurring_tasks.return_value = []

        # Act
        with patch.object(scheduler, "_add_database_scheduled_task") as mock_add:
            scheduler._periodic_database_sync()

        # Assert
        mock_add.assert_not_called()

    @patch("apps.tasks.models.Task")
    def test_skips_immediate_task_not_ready_to_run(self, mock_task_model):
        """Test periodic sync skips immediate tasks not ready to run."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        scheduler.running = True

        mock_immediate_task = MagicMock()
        mock_immediate_task.id = 1
        mock_immediate_task.name = "Not Ready Task"
        mock_immediate_task.is_ready_to_run.return_value = False

        mock_task_model.immediate_tasks.return_value = [mock_immediate_task]
        mock_task_model.scheduled_tasks.return_value = []
        mock_task_model.recurring_tasks.return_value = []

        # Act
        with patch.object(scheduler, "_execute_database_task") as mock_execute:
            scheduler._periodic_database_sync()

        # Assert
        mock_execute.assert_not_called()


@pytest.mark.unit
@pytest.mark.django_db
class TestAddDatabaseScheduledTaskErrors:
    """Test error handling in _add_database_scheduled_task."""

    def test_skips_if_already_in_tracking(self, pending_task):
        """Test returns early if task is already in tracking."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        scheduler._db_task_jobs[pending_task.id] = f"db_task_{pending_task.id}"

        # Act
        with patch.object(scheduler.scheduler, "add_job") as mock_add_job:
            scheduler._add_database_scheduled_task(pending_task)

        # Assert
        mock_add_job.assert_not_called()

    @patch.object(UnifiedTaskScheduler, "_execute_database_task")
    def test_executes_immediately_if_past_due(self, mock_execute, pending_task):
        """Test executes task immediately if scheduled time is in the past."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        pending_task.scheduled_time = timezone.now() - timedelta(hours=1)

        # Act
        scheduler._add_database_scheduled_task(pending_task)

        # Assert
        mock_execute.assert_called_once_with(pending_task.id)

    def test_handles_exception_during_add(self, pending_task):
        """Test handles exception during job addition."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        pending_task.scheduled_time = timezone.now() + timedelta(hours=1)

        # Act - should not raise
        with patch.object(scheduler.scheduler, "add_job", side_effect=Exception("Scheduler error")):
            scheduler._add_database_scheduled_task(pending_task)

        # Task should not be in tracking after error
        assert pending_task.id not in scheduler._db_task_jobs


@pytest.mark.unit
@pytest.mark.django_db
class TestAddDatabaseRecurringTaskErrors:
    """Test error handling in _add_database_recurring_task."""

    def test_skips_if_already_in_tracking(self, recurring_task):
        """Test returns early if task is already in tracking."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        scheduler._db_task_jobs[recurring_task.id] = f"db_recurring_{recurring_task.id}"

        # Act
        with patch.object(scheduler.scheduler, "add_job") as mock_add_job:
            scheduler._add_database_recurring_task(recurring_task)

        # Assert
        mock_add_job.assert_not_called()

    def test_handles_exception_during_add(self, recurring_task):
        """Test handles exception during job addition."""
        # Arrange
        scheduler = UnifiedTaskScheduler()

        # Act - should not raise
        with patch.object(scheduler.scheduler, "add_job", side_effect=Exception("Scheduler error")):
            scheduler._add_database_recurring_task(recurring_task)

        # Task should not be in tracking after error
        assert recurring_task.id not in scheduler._db_task_jobs


@pytest.mark.unit
@pytest.mark.django_db
class TestExecuteDatabaseTaskErrors:
    """Test error handling in _execute_database_task."""

    @patch.object(UnifiedTaskScheduler, "_remove_database_task")
    def test_handles_task_not_found(self, mock_remove):
        """Test handles Task.DoesNotExist exception."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        from apps.tasks.models import Task

        with patch("apps.tasks.models.Task.objects.get", side_effect=Task.DoesNotExist):
            # Act
            scheduler._execute_database_task(999)

        # Assert
        mock_remove.assert_called_once_with(999)

    @patch("apps.tasks.models.Task")
    @patch.object(UnifiedTaskScheduler, "_remove_database_task")
    def test_handles_non_pending_task(self, mock_remove, mock_task_model):
        """Test handles task in non-pending status."""
        # Arrange
        scheduler = UnifiedTaskScheduler()

        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.status = "running"
        mock_task.cron_expression = None
        mock_task_model.objects.get.return_value = mock_task

        # Act
        scheduler._execute_database_task(1)

        # Assert
        mock_remove.assert_called_once_with(1)


@pytest.mark.unit
@pytest.mark.django_db
class TestSyncDatabaseTasks:
    """Test _sync_database_tasks functionality."""

    @patch("apps.tasks.models.Task")
    @patch.object(UnifiedTaskScheduler, "_add_database_scheduled_task")
    @patch.object(UnifiedTaskScheduler, "_add_database_recurring_task")
    def test_syncs_scheduled_and_recurring_tasks(self, mock_add_recurring, mock_add_scheduled, mock_task_model):
        """Test syncs both scheduled and recurring tasks."""
        # Arrange
        scheduler = UnifiedTaskScheduler()

        mock_scheduled_task = MagicMock()
        mock_recurring_task = MagicMock()

        mock_task_model.scheduled_tasks.return_value = [mock_scheduled_task]
        mock_task_model.recurring_tasks.return_value = [mock_recurring_task]

        # Act
        scheduler._sync_database_tasks()

        # Assert
        mock_add_scheduled.assert_called_once_with(mock_scheduled_task)
        mock_add_recurring.assert_called_once_with(mock_recurring_task)


@pytest.mark.unit
@pytest.mark.django_db
class TestRemoveDatabaseTask:
    """Test _remove_database_task functionality."""

    def test_removes_job_from_scheduler_and_tracking(self):
        """Test removes job from both scheduler and tracking dict."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        scheduler._db_task_jobs[1] = "db_task_1"

        mock_remove_job = MagicMock()
        scheduler.scheduler.remove_job = mock_remove_job

        # Act
        scheduler._remove_database_task(1)

        # Assert
        mock_remove_job.assert_called_once_with("db_task_1")
        assert 1 not in scheduler._db_task_jobs

    def test_handles_exception_during_remove(self):
        """Test handles exception when removing job from scheduler."""
        # Arrange
        scheduler = UnifiedTaskScheduler()
        scheduler._db_task_jobs[1] = "db_task_1"

        scheduler.scheduler.remove_job = MagicMock(side_effect=Exception("Job not found"))

        # Act - should not raise
        scheduler._remove_database_task(1)

        # Assert - still removed from tracking
        assert 1 not in scheduler._db_task_jobs
