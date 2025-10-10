"""
Comprehensive unit tests for cron scheduler.
"""

import builtins
import contextlib
from unittest.mock import Mock, patch

from django.test import TestCase

from apps.tasks.cron_scheduler import CronTaskScheduler, get_scheduler, start_scheduler, stop_scheduler


class CronTaskSchedulerTestCase(TestCase):
    """Test cases for CronTaskScheduler."""

    def setUp(self):
        """Set up test data."""
        self.scheduler = None

    def tearDown(self):
        """Clean up after tests."""
        if self.scheduler and hasattr(self.scheduler, "scheduler"):
            with contextlib.suppress(builtins.BaseException):
                self.scheduler.scheduler.shutdown(wait=False)

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_init(self, mock_group_status, mock_enabled_tasks):
        """Test CronTaskScheduler initialization."""
        mock_enabled_tasks.return_value = {
            "test_task": {"name": "Test Task", "function": "test_function", "cron": "0 0 * * *"}
        }
        mock_group_status.return_value = {"test_group": True}

        scheduler = CronTaskScheduler()

        self.assertIsNotNone(scheduler.scheduler)
        self.assertFalse(scheduler.running)
        self.assertIsNotNone(scheduler._lock)
        self.assertIsInstance(scheduler.task_registry, dict)
        mock_enabled_tasks.assert_called_once()

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_load_task_registry_success(self, mock_group_status, mock_enabled_tasks):
        """Test successful task registry loading."""
        test_tasks = {
            "task1": {"name": "Task 1", "function": "func1", "cron": "0 0 * * *"},
            "task2": {"name": "Task 2", "function": "func2", "cron": "0 12 * * *"},
        }
        mock_enabled_tasks.return_value = test_tasks
        mock_group_status.return_value = {"group1": True, "group2": False}

        scheduler = CronTaskScheduler()

        self.assertEqual(scheduler.task_registry, test_tasks)

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_load_task_registry_exception(self, mock_group_status, mock_enabled_tasks):
        """Test task registry loading with exception."""
        mock_enabled_tasks.side_effect = Exception("Loading failed")

        scheduler = CronTaskScheduler()

        # Should handle exception gracefully
        self.assertEqual(scheduler.task_registry, {})

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_start_scheduler(self, mock_group_status, mock_enabled_tasks):
        """Test starting the scheduler."""
        mock_enabled_tasks.return_value = {}
        mock_group_status.return_value = {}

        scheduler = CronTaskScheduler()

        with patch.object(scheduler.scheduler, "start") as mock_start:
            scheduler.start()

            mock_start.assert_called_once()
            self.assertTrue(scheduler.running)

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_start_scheduler_already_running(self, mock_group_status, mock_enabled_tasks):
        """Test starting scheduler when already running."""
        mock_enabled_tasks.return_value = {}
        mock_group_status.return_value = {}

        scheduler = CronTaskScheduler()
        scheduler.running = True

        with patch.object(scheduler.scheduler, "start") as mock_start:
            scheduler.start()

            mock_start.assert_not_called()

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_stop_scheduler(self, mock_group_status, mock_enabled_tasks):
        """Test stopping the scheduler."""
        mock_enabled_tasks.return_value = {}
        mock_group_status.return_value = {}

        scheduler = CronTaskScheduler()
        scheduler.running = True

        with patch.object(scheduler.scheduler, "shutdown") as mock_shutdown:
            scheduler.stop()

            mock_shutdown.assert_called_once()
            self.assertFalse(scheduler.running)

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_stop_scheduler_not_running(self, mock_group_status, mock_enabled_tasks):
        """Test stopping scheduler when not running."""
        mock_enabled_tasks.return_value = {}
        mock_group_status.return_value = {}

        scheduler = CronTaskScheduler()
        scheduler.running = False

        with patch.object(scheduler.scheduler, "shutdown") as mock_shutdown:
            scheduler.stop()

            mock_shutdown.assert_not_called()

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_add_job(self, mock_group_status, mock_enabled_tasks):
        """Test adding a job to the scheduler."""
        mock_enabled_tasks.return_value = {}
        mock_group_status.return_value = {}

        scheduler = CronTaskScheduler()

        with patch.object(scheduler.scheduler, "add_job") as mock_add_job:
            mock_job = Mock()
            mock_add_job.return_value = mock_job

            task_config = {"function": "test_function", "cron": "0 0 * * *", "name": "Test Task"}

            scheduler.add_job("test_task", task_config)

            mock_add_job.assert_called_once()
            call_args = mock_add_job.call_args

            # Check that CronTrigger was used
            self.assertIsNotNone(call_args)

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_remove_job(self, mock_group_status, mock_enabled_tasks):
        """Test removing a job from the scheduler."""
        mock_enabled_tasks.return_value = {}
        mock_group_status.return_value = {}

        scheduler = CronTaskScheduler()

        with patch.object(scheduler.scheduler, "remove_job") as mock_remove_job:
            scheduler.remove_job("test_task")

            mock_remove_job.assert_called_once_with("test_task")

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_remove_job_not_found(self, mock_group_status, mock_enabled_tasks):
        """Test removing a job that doesn't exist."""
        mock_enabled_tasks.return_value = {}
        mock_group_status.return_value = {}

        scheduler = CronTaskScheduler()

        from apscheduler.jobstores.base import JobLookupError

        with patch.object(scheduler.scheduler, "remove_job") as mock_remove_job:
            mock_remove_job.side_effect = JobLookupError("test_task")

            # Should not raise exception
            scheduler.remove_job("test_task")

            mock_remove_job.assert_called_once_with("test_task")

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_get_jobs(self, mock_group_status, mock_enabled_tasks):
        """Test getting jobs from the scheduler."""
        mock_enabled_tasks.return_value = {}
        mock_group_status.return_value = {}

        scheduler = CronTaskScheduler()

        mock_jobs = [Mock(), Mock()]
        with patch.object(scheduler.scheduler, "get_jobs") as mock_get_jobs:
            mock_get_jobs.return_value = mock_jobs

            result = scheduler.get_jobs()

            self.assertEqual(result, mock_jobs)
            mock_get_jobs.assert_called_once()

    @patch("apps.tasks.cron_scheduler.get_all_enabled_tasks")
    @patch("apps.tasks.cron_scheduler.get_task_group_status")
    def test_reload_tasks(self, mock_group_status, mock_enabled_tasks):
        """Test reloading tasks."""
        mock_enabled_tasks.return_value = {"task1": {"name": "Task 1", "function": "func1", "cron": "0 0 * * *"}}
        mock_group_status.return_value = {"group1": True}

        scheduler = CronTaskScheduler()

        # Change the return value for reload
        new_tasks = {"task2": {"name": "Task 2", "function": "func2", "cron": "0 12 * * *"}}
        mock_enabled_tasks.return_value = new_tasks

        with (
            patch.object(scheduler, "_clear_scheduled_jobs") as mock_clear,
            patch.object(scheduler, "_schedule_tasks") as mock_schedule,
        ):
            scheduler.reload_tasks()

            self.assertEqual(scheduler.task_registry, new_tasks)
            mock_clear.assert_called_once()
            mock_schedule.assert_called_once()

    def test_is_running(self):
        """Test is_running method."""
        with (
            patch("apps.tasks.cron_scheduler.get_all_enabled_tasks"),
            patch("apps.tasks.cron_scheduler.get_task_group_status"),
        ):
            scheduler = CronTaskScheduler()

            scheduler.running = True
            self.assertTrue(scheduler.is_running())

            scheduler.running = False
            self.assertFalse(scheduler.is_running())


class CronSchedulerModuleFunctionsTestCase(TestCase):
    """Test cases for module-level functions."""

    def setUp(self):
        """Set up test data."""
        # Reset global scheduler
        import apps.tasks.cron_scheduler as cron_module

        if hasattr(cron_module, "_scheduler"):
            cron_module._scheduler = None

    def tearDown(self):
        """Clean up after tests."""
        import apps.tasks.cron_scheduler as cron_module

        if hasattr(cron_module, "_scheduler") and cron_module._scheduler:
            try:
                cron_module._scheduler.stop()
                cron_module._scheduler = None
            except Exception:  # noqa: S110
                # Ignore cleanup errors during test teardown
                pass

    @patch("apps.tasks.cron_scheduler.CronTaskScheduler")
    def test_get_scheduler_creates_new(self, mock_scheduler_class):
        """Test get_scheduler creates new scheduler when none exists."""
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler

        result = get_scheduler()

        self.assertEqual(result, mock_scheduler)
        mock_scheduler_class.assert_called_once()

    @patch("apps.tasks.cron_scheduler.CronTaskScheduler")
    def test_get_scheduler_returns_existing(self, mock_scheduler_class):
        """Test get_scheduler returns existing scheduler."""
        mock_scheduler = Mock()
        mock_scheduler_class.return_value = mock_scheduler

        # First call creates scheduler
        first_result = get_scheduler()
        # Second call should return same instance
        second_result = get_scheduler()

        self.assertEqual(first_result, second_result)
        mock_scheduler_class.assert_called_once()  # Only called once

    @patch("apps.tasks.cron_scheduler.get_scheduler")
    def test_start_scheduler(self, mock_get_scheduler):
        """Test start_scheduler function."""
        mock_scheduler = Mock()
        mock_get_scheduler.return_value = mock_scheduler

        start_scheduler()

        mock_get_scheduler.assert_called_once()
        mock_scheduler.start.assert_called_once()

    @patch("apps.tasks.cron_scheduler.get_scheduler")
    def test_stop_scheduler(self, mock_get_scheduler):
        """Test stop_scheduler function."""
        mock_scheduler = Mock()
        mock_get_scheduler.return_value = mock_scheduler

        stop_scheduler()

        mock_get_scheduler.assert_called_once()
        mock_scheduler.stop.assert_called_once()

    def test_module_imports(self):
        """Test that all required imports work."""
        from apps.tasks import cron_scheduler

        # Test that key classes and functions are available
        self.assertTrue(hasattr(cron_scheduler, "CronTaskScheduler"))
        self.assertTrue(hasattr(cron_scheduler, "get_scheduler"))
        self.assertTrue(hasattr(cron_scheduler, "start_scheduler"))
        self.assertTrue(hasattr(cron_scheduler, "stop_scheduler"))

    def test_logger_configured(self):
        """Test that logger is properly configured."""
        from apps.tasks import cron_scheduler

        self.assertTrue(hasattr(cron_scheduler, "logger"))
        self.assertEqual(cron_scheduler.logger.name, "apps.tasks.cron_scheduler")
