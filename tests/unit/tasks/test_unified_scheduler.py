"""
Comprehensive unit tests for the UnifiedTaskScheduler module.

Tests the task scheduler that combines task group scheduling and database task scheduling
without database polling, using APScheduler for optimal performance.
"""

import logging
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.tasks.cron_scheduler import (
    UnifiedTaskScheduler,
    get_scheduler,
    refresh_scheduler,
    start_scheduler,
    stop_scheduler,
    sync_database_tasks,
)

User = get_user_model()


@pytest.fixture
def mock_task():
    """Create a mock task object."""
    task = Mock()
    task.id = 1
    task.name = "Test Task"
    task.status = "pending"
    task.function_name = "test_function"
    task.task_data = {}
    task.scheduled_time = timezone.now() + timedelta(hours=1)
    task.is_recurring = False
    task.cron_expression = None
    task.created = timezone.now()
    task.modified = timezone.now()
    task.save = Mock()
    return task


@pytest.fixture
def mock_recurring_task():
    """Create a mock recurring task object."""
    task = Mock()
    task.id = 2
    task.name = "Recurring Task"
    task.status = "pending"
    task.function_name = "recurring_function"
    task.task_data = {}
    task.scheduled_time = None
    task.is_recurring = True
    task.cron_expression = "0 * * * *"  # Every hour
    task.created = timezone.now()
    task.modified = timezone.now()
    task.save = Mock()
    return task


@pytest.fixture
def scheduler():
    """Create a UnifiedTaskScheduler instance."""
    with patch("apps.tasks.models.Task") as mock_task_model:
        # Mock empty database
        mock_queryset = Mock()
        mock_queryset.exclude.return_value = []
        mock_task_model.objects.filter.return_value = mock_queryset
        return UnifiedTaskScheduler()


@pytest.mark.unit
class TestUnifiedTaskScheduler:
    """Test the UnifiedTaskScheduler class."""

    def test_init(self):
        """Test scheduler initialization."""
        with patch("apps.tasks.models.Task") as mock_task_model:
            # Mock empty database
            mock_queryset = Mock()
            mock_queryset.exclude.return_value = []
            mock_task_model.objects.filter.return_value = mock_queryset

            scheduler = UnifiedTaskScheduler(check_interval=30)

        assert scheduler.check_interval == 30
        assert not scheduler.running
        assert isinstance(scheduler.task_registry, dict)
        assert isinstance(scheduler._db_task_jobs, dict)

    @patch("apps.tasks.models.Task")
    def test_load_task_registry(self, mock_task_model):
        """Test loading task registry from database."""
        # Create mock task objects
        task1 = Mock()
        task1.id = 1
        task1.name = "test_task"
        task1.function_name = "test_function"
        task1.cron_expression = "0 * * * *"
        task1.task_data = {}
        task1.description = "Test task"
        task1.priority = 5

        mock_queryset = Mock()
        mock_queryset.exclude.return_value = [task1]
        mock_task_model.objects.filter.return_value = mock_queryset

        scheduler = UnifiedTaskScheduler()
        assert "test_task" in scheduler.task_registry

    @patch("apps.tasks.models.Task")
    def test_sync_database_tasks_scheduled(self, mock_task_model, scheduler):
        """Test syncing scheduled database tasks."""
        # Mock scheduled task
        mock_task = Mock()
        mock_task.id = 1
        mock_task.name = "Test"
        mock_task.scheduled_time = timezone.now() + timedelta(hours=1)
        mock_task.is_recurring = False

        # Create mock QuerySets
        mock_scheduled_qs = Mock()
        mock_scheduled_qs.__iter__ = Mock(return_value=iter([mock_task]))
        mock_scheduled_qs.__len__ = Mock(return_value=1)

        mock_recurring_qs = Mock()
        mock_recurring_qs.__iter__ = Mock(return_value=iter([]))
        mock_recurring_qs.__len__ = Mock(return_value=0)
        mock_recurring_qs.exclude.return_value = mock_recurring_qs

        # Set up filter to return different results for different calls
        def filter_side_effect(**kwargs):
            if "is_recurring" in kwargs and kwargs["is_recurring"] is False:
                return mock_scheduled_qs
            return mock_recurring_qs

        mock_task_model.objects.filter.side_effect = filter_side_effect

        with patch.object(scheduler, "_add_database_scheduled_task") as mock_add:
            scheduler._sync_database_tasks()
            mock_add.assert_called_once_with(mock_task)

    @patch("apps.tasks.models.Task")
    def test_sync_database_tasks_recurring(self, mock_task_model, scheduler):
        """Test syncing recurring database tasks."""
        # Mock recurring task
        mock_task = Mock()
        mock_task.id = 2
        mock_task.name = "Recurring Test"
        mock_task.is_recurring = True
        mock_task.cron_expression = "0 * * * *"

        # Create mock QuerySets
        mock_scheduled_qs = Mock()
        mock_scheduled_qs.__iter__ = Mock(return_value=iter([]))
        mock_scheduled_qs.__len__ = Mock(return_value=0)

        mock_recurring_qs = Mock()
        mock_recurring_qs.__iter__ = Mock(return_value=iter([mock_task]))
        mock_recurring_qs.__len__ = Mock(return_value=1)
        mock_recurring_qs.exclude.return_value = mock_recurring_qs

        # Set up filter to return different results for different calls
        def filter_side_effect(**kwargs):
            if "is_recurring" in kwargs and kwargs["is_recurring"] is False:
                return mock_scheduled_qs
            return mock_recurring_qs

        mock_task_model.objects.filter.side_effect = filter_side_effect

        with patch.object(scheduler, "_add_database_recurring_task") as mock_add:
            scheduler._sync_database_tasks()
            mock_add.assert_called_once_with(mock_task)

    def test_add_database_scheduled_task(self, scheduler, mock_task):
        """Test adding a scheduled database task."""
        with patch.object(scheduler.scheduler, "add_job") as mock_add_job:
            scheduler._add_database_scheduled_task(mock_task)

            mock_add_job.assert_called_once()
            assert mock_task.id in scheduler._db_task_jobs

    def test_add_database_recurring_task(self, scheduler, mock_recurring_task):
        """Test adding a recurring database task."""
        with patch.object(scheduler.scheduler, "add_job") as mock_add_job:
            scheduler._add_database_recurring_task(mock_recurring_task)

            mock_add_job.assert_called_once()
            assert mock_recurring_task.id in scheduler._db_task_jobs

    def test_remove_database_task(self, scheduler):
        """Test removing a database task."""
        task_id = 1
        job_id = f"db_task_{task_id}"
        scheduler._db_task_jobs[task_id] = job_id

        with patch.object(scheduler.scheduler, "remove_job") as mock_remove:
            scheduler._remove_database_task(task_id)

            mock_remove.assert_called_once_with(job_id)
            assert task_id not in scheduler._db_task_jobs

    @patch("apps.tasks.models.Task")
    @patch("apps.tasks.tasks_system.submit_task_to_dispatcher")
    def test_execute_database_task(self, mock_submit, mock_task_model, scheduler):
        """Test executing a database task."""
        task_id = 1
        mock_task = Mock()
        mock_task.id = task_id
        mock_task.name = "Test"
        mock_task.is_recurring = False
        mock_task.status = "pending"  # Set status to pending for the test

        mock_task_model.objects.get.return_value = mock_task

        with patch.object(scheduler, "_remove_database_task") as mock_remove:
            scheduler._execute_database_task(task_id)

            mock_submit.assert_called_once_with(mock_task)
            mock_remove.assert_called_once_with(task_id)

    @patch("apps.tasks.models.Task")
    @patch("apps.tasks.tasks_system.submit_task_to_dispatcher")
    def test_execute_database_task_recurring(self, mock_submit, mock_task_model, scheduler):
        """Test executing a recurring database task."""
        task_id = 2
        mock_task = Mock()
        mock_task.id = task_id
        mock_task.name = "Recurring Test"
        mock_task.is_recurring = True
        mock_task.status = "pending"
        mock_task.function_name = "test_function"
        mock_task.task_data = {}
        mock_task.priority = 2
        mock_task.max_attempts = 3
        mock_task.timeout_seconds = 300
        mock_task.created_by = None
        mock_task.is_system_task = False

        # Mock the execution task that gets created
        mock_execution_task = Mock()
        mock_execution_task.id = 999
        mock_execution_task.name = "Recurring Test (Execution 2024-01-01 12:00:00)"

        mock_task_model.objects.get.return_value = mock_task
        mock_task_model.objects.create.return_value = mock_execution_task

        with patch.object(scheduler, "_remove_database_task") as mock_remove:
            scheduler._execute_database_task(task_id)

            # Should create execution task and submit that
            mock_task_model.objects.create.assert_called_once()
            mock_submit.assert_called_once_with(mock_execution_task)
            # Should not remove recurring tasks
            mock_remove.assert_not_called()

    def test_start_scheduler(self, scheduler):
        """Test starting the scheduler."""
        with patch.object(scheduler.scheduler, "start"), patch.object(scheduler, "_sync_database_tasks"):
            scheduler.start()

            assert scheduler.running

    def test_stop_scheduler(self, scheduler):
        """Test stopping the scheduler."""
        scheduler.running = True
        scheduler._db_task_jobs[1] = "job_1"

        with patch.object(scheduler.scheduler, "shutdown"):
            scheduler.stop()

            assert not scheduler.running
            assert len(scheduler._db_task_jobs) == 0

    def test_add_database_task_scheduled(self, scheduler, mock_task):
        """Test adding a database task via the API."""
        scheduler.running = True

        with patch.object(scheduler, "_add_database_scheduled_task") as mock_add:
            scheduler.add_database_task(mock_task)
            mock_add.assert_called_once_with(mock_task)

    def test_add_database_task_recurring(self, scheduler, mock_recurring_task):
        """Test adding a recurring database task via the API."""
        scheduler.running = True

        with patch.object(scheduler, "_add_database_recurring_task") as mock_add:
            scheduler.add_database_task(mock_recurring_task)
            mock_add.assert_called_once_with(mock_recurring_task)

    def test_add_database_task_not_running(self, scheduler, mock_task):
        """Test adding a database task when scheduler is not running."""
        scheduler.running = False

        with patch.object(scheduler, "_add_database_scheduled_task") as mock_add:
            scheduler.add_database_task(mock_task)
            mock_add.assert_not_called()

    def test_update_database_task(self, scheduler, mock_task):
        """Test updating a database task."""
        scheduler.running = True

        with (
            patch.object(scheduler, "_remove_database_task") as mock_remove,
            patch.object(scheduler, "add_database_task") as mock_add,
        ):
            scheduler.update_database_task(mock_task)

            mock_remove.assert_called_once_with(mock_task.id)
            mock_add.assert_called_once_with(mock_task)

    def test_list_tasks(self, scheduler):
        """Test listing all tasks."""
        scheduler.task_registry = {"test": "config"}
        scheduler._db_task_jobs = {1: "job_1", 2: "job_2"}

        with (
            patch.object(scheduler.scheduler, "get_jobs", return_value=[]),
            patch("apps.tasks.cron_scheduler.get_task_group_status", return_value={}),
        ):
            result = scheduler.list_tasks()

            assert "task_groups" in result
            assert "database_tasks" in result
            assert result["database_tasks"] == 2


@pytest.mark.unit
class TestGlobalSchedulerFunctions:
    """Test global scheduler management functions."""

    def test_get_scheduler_creates_instance(self):
        """Test get_scheduler creates a new instance if none exists."""
        with (
            patch("apps.tasks.cron_scheduler._scheduler_instance", None),
            patch("apps.tasks.cron_scheduler.UnifiedTaskScheduler") as mock_scheduler,
        ):
            get_scheduler()
            mock_scheduler.assert_called_once()

    def test_start_scheduler(self):
        """Test start_scheduler function."""
        with patch("apps.tasks.cron_scheduler.get_scheduler") as mock_get:
            mock_scheduler = Mock()
            mock_get.return_value = mock_scheduler

            start_scheduler()
            mock_scheduler.start.assert_called_once()

    def test_stop_scheduler(self):
        """Test stop_scheduler function."""
        mock_scheduler = Mock()
        with patch("apps.tasks.cron_scheduler._scheduler_instance", mock_scheduler):
            stop_scheduler()
            mock_scheduler.stop.assert_called_once()

    def test_sync_database_tasks(self):
        """Test sync_database_tasks function."""
        mock_scheduler = Mock()
        mock_scheduler.running = True

        with patch("apps.tasks.cron_scheduler.get_scheduler", return_value=mock_scheduler):
            sync_database_tasks()
            mock_scheduler._sync_database_tasks.assert_called_once()

    def test_refresh_scheduler(self):
        """Test refresh_scheduler function."""
        mock_scheduler = Mock()
        mock_scheduler.running = True

        with patch("apps.tasks.cron_scheduler.get_scheduler", return_value=mock_scheduler):
            refresh_scheduler()
            mock_scheduler._sync_database_tasks.assert_called_once()


@pytest.mark.unit
class TestBackwardCompatibility:
    """Test backward compatibility aliases."""

    def test_cron_task_scheduler_alias(self):
        """Test that CronTaskScheduler is aliased to UnifiedTaskScheduler."""
        from apps.tasks.cron_scheduler import CronTaskScheduler, UnifiedTaskScheduler

        assert CronTaskScheduler is UnifiedTaskScheduler


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling in the task scheduler."""

    def test_sync_database_tasks_error(self, scheduler, caplog):
        """Test error handling in _sync_database_tasks."""
        with patch("apps.tasks.models.Task") as mock_task:
            mock_task.objects.filter.side_effect = Exception("DB Error")

            with caplog.at_level(logging.ERROR):
                scheduler._sync_database_tasks()

            assert "Error synchronizing database tasks" in caplog.text

    def test_add_database_scheduled_task_error(self, scheduler, mock_task, caplog):
        """Test error handling when adding scheduled task fails."""
        with patch.object(scheduler.scheduler, "add_job", side_effect=Exception("Scheduler error")):
            with caplog.at_level(logging.ERROR):
                scheduler._add_database_scheduled_task(mock_task)

            assert "Failed to add scheduled database task" in caplog.text

    def test_add_database_recurring_task_error(self, scheduler, mock_recurring_task, caplog):
        """Test error handling when adding recurring task fails."""
        with patch.object(scheduler.scheduler, "add_job", side_effect=Exception("Scheduler error")):
            with caplog.at_level(logging.ERROR):
                scheduler._add_database_recurring_task(mock_recurring_task)

            assert "Failed to add recurring database task" in caplog.text

    @patch("apps.tasks.models.Task")
    def test_execute_database_task_not_found(self, mock_task_model, scheduler, caplog):
        """Test executing a task that doesn't exist."""
        from django.core.exceptions import ObjectDoesNotExist

        mock_task_model.objects.get.side_effect = ObjectDoesNotExist()
        mock_task_model.DoesNotExist = ObjectDoesNotExist

        with patch.object(scheduler, "_remove_database_task") as mock_remove:
            with caplog.at_level(logging.WARNING):
                scheduler._execute_database_task(999)

            assert "Database task 999 not found" in caplog.text
            mock_remove.assert_called_once_with(999)
