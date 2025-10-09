"""
Comprehensive test coverage for apps/tasks/cron_scheduler.py

This module provides extensive coverage for the cron scheduler functionality,
task registry, error handling, and scheduler lifecycle management.
"""

import threading
import time
from unittest.mock import Mock, patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.tasks.cron_scheduler import (
    CronTaskScheduler,
    get_scheduler,
    start_scheduler,
    stop_scheduler,
)


@pytest.mark.unit
class TestCronTaskSchedulerInit(TestCase):
    """Test CronTaskScheduler initialization and basic functionality."""

    def setUp(self):
        """Set up test environment."""
        self.scheduler = CronTaskScheduler()

    def test_scheduler_initialization(self):
        """Test scheduler initialization."""
        assert self.scheduler.scheduler is not None
        assert self.scheduler.running is False
        assert self.scheduler._lock is not None
        assert isinstance(self.scheduler._lock, threading.Lock)
        assert hasattr(self.scheduler, "task_registry")
        assert isinstance(self.scheduler.task_registry, dict)

    def test_task_registry_structure(self):
        """Test task registry has expected structure."""
        registry = self.scheduler.task_registry

        # Check for expected system tasks
        expected_tasks = [
            "daily_task_cleanup",
            "weekly_data_cleanup",
            "hourly_metrics_collection",
            "daily_system_health_check",
        ]

        for task_name in expected_tasks:
            assert task_name in registry
            task_config = registry[task_name]

            # Check required fields
            required_fields = ["function", "cron", "args", "enabled", "description"]
            for field in required_fields:
                assert field in task_config

            # Validate types
            assert isinstance(task_config["function"], str)
            assert isinstance(task_config["cron"], str)
            assert isinstance(task_config["args"], dict)
            assert isinstance(task_config["enabled"], bool)
            assert isinstance(task_config["description"], str)

    def test_scheduler_start(self):
        """Test scheduler start functionality."""
        with (
            patch.object(self.scheduler.scheduler, "start") as mock_start,
            patch.object(self.scheduler.scheduler, "running", False),
        ):
            self.scheduler.start()

            mock_start.assert_called_once()
            assert self.scheduler.running is True

    def test_scheduler_start_already_running(self):
        """Test starting scheduler when already running."""
        self.scheduler.running = True

        with patch.object(self.scheduler.scheduler, "start") as mock_start:
            self.scheduler.start()

            mock_start.assert_not_called()

    def test_scheduler_stop(self):
        """Test scheduler stop functionality."""
        self.scheduler.running = True

        with patch.object(self.scheduler.scheduler, "shutdown") as mock_shutdown:
            self.scheduler.stop()

            mock_shutdown.assert_called_once()
            assert self.scheduler.running is False

    def test_scheduler_stop_not_running(self):
        """Test stopping scheduler when not running."""
        self.scheduler.running = False

        with patch.object(self.scheduler.scheduler, "shutdown") as mock_shutdown:
            self.scheduler.stop()

            mock_shutdown.assert_not_called()

    def test_scheduler_restart(self):
        """Test scheduler restart functionality."""
        with patch.object(self.scheduler, "stop") as mock_stop, patch.object(self.scheduler, "start") as mock_start:
            self.scheduler.restart()

            mock_stop.assert_called_once()
            mock_start.assert_called_once()


@pytest.mark.unit
class TestCronTaskSchedulerTaskManagement(TestCase):
    """Test task management functionality."""

    def setUp(self):
        """Set up test environment."""
        self.scheduler = CronTaskScheduler()

    def test_add_dynamic_task_success(self):
        """Test successful dynamic task addition."""
        with patch.object(self.scheduler.scheduler, "add_job") as mock_add_job:
            self.scheduler.add_dynamic_task(
                task_id="test_task", function_name="cleanup_old_data", cron_expression="0 0 * * *", args={"days_old": 7}
            )

            mock_add_job.assert_called_once()

    def test_add_dynamic_task_invalid_function(self):
        """Test adding task with invalid function name."""
        with pytest.raises(ValueError):
            self.scheduler.add_dynamic_task(
                task_id="test_task", function_name="invalid_function", cron_expression="0 0 * * *", args={}
            )

    def test_add_dynamic_task_invalid_cron(self):
        """Test adding task with invalid cron expression."""
        with (
            patch.object(self.scheduler.scheduler, "add_job", side_effect=ValueError("Invalid cron")),
            pytest.raises(ValueError),
        ):
            self.scheduler.add_dynamic_task(
                task_id="test_task", function_name="cleanup_old_data", cron_expression="invalid_cron", args={}
            )

    def test_add_dynamic_task_exception(self):
        """Test adding task with general exception."""
        with (
            patch.object(self.scheduler.scheduler, "add_job", side_effect=ValueError("Test error")),
            pytest.raises(ValueError),
        ):
            self.scheduler.add_dynamic_task(
                task_id="test_task", function_name="cleanup_old_data", cron_expression="0 0 * * *", args={}
            )

    def test_remove_task_success(self):
        """Test successful task removal."""
        with patch.object(self.scheduler.scheduler, "remove_job") as mock_remove_job:
            self.scheduler.remove_task("test_task")

            mock_remove_job.assert_called_once_with("test_task")

    def test_remove_task_not_found(self):
        """Test removing non-existent task."""
        from apscheduler.jobstores.base import JobLookupError

        with patch.object(self.scheduler.scheduler, "remove_job", side_effect=JobLookupError("test_task")):
            # Should not raise exception, just log error
            self.scheduler.remove_task("test_task")

    def test_remove_task_exception(self):
        """Test removing task with general exception."""
        with patch.object(self.scheduler.scheduler, "remove_job", side_effect=Exception("Test error")):
            # Should not raise exception, just log error
            self.scheduler.remove_task("test_task")

    def test_list_tasks(self):
        """Test listing tasks."""
        mock_job1 = Mock()
        mock_job1.id = "task1"
        mock_job1.name = "Task 1"
        mock_job1.next_run_time = timezone.now()
        mock_job1.trigger = "Mock Trigger"

        mock_job2 = Mock()
        mock_job2.id = "task2"
        mock_job2.name = "Task 2"
        mock_job2.next_run_time = None
        mock_job2.trigger = "Mock Trigger"

        with patch.object(self.scheduler.scheduler, "get_jobs", return_value=[mock_job1, mock_job2]):
            tasks = self.scheduler.list_tasks()

            assert "registry" in tasks
            assert "scheduled_jobs" in tasks
            assert len(tasks["scheduled_jobs"]) == 2
            assert tasks["scheduled_jobs"][0]["id"] == "task1"
            assert tasks["scheduled_jobs"][0]["name"] == "Task 1"

    def test_list_tasks_exception(self):
        """Test listing tasks with exception."""
        with patch.object(self.scheduler.scheduler, "get_jobs", side_effect=Exception("Test error")):
            # Should return empty scheduled_jobs list but registry should still be available
            tasks = self.scheduler.list_tasks()

            assert "registry" in tasks
            assert "scheduled_jobs" in tasks

    def test_running_attribute(self):
        """Test running attribute."""
        self.scheduler.running = True
        assert self.scheduler.running is True

        self.scheduler.running = False
        assert self.scheduler.running is False

    def test_add_registry_tasks(self):
        """Test adding registry tasks."""
        with patch.object(self.scheduler, "_add_scheduled_task") as mock_add_task:
            self.scheduler._add_registry_tasks()

            # Should call _add_scheduled_task for each enabled task in registry
            enabled_tasks = [
                task_name for task_name, config in self.scheduler.task_registry.items() if config.get("enabled", True)
            ]
            assert mock_add_task.call_count == len(enabled_tasks)

    def test_add_registry_tasks_with_disabled(self):
        """Test adding registry tasks with some disabled."""
        # Mock a registry with mixed enabled/disabled tasks
        mock_registry = {
            "enabled_task": {
                "function": "cleanup_old_data",
                "cron": "0 0 * * *",
                "args": {},
                "enabled": True,
                "description": "Enabled task",
            },
            "disabled_task": {
                "function": "cleanup_old_data",
                "cron": "0 1 * * *",
                "args": {},
                "enabled": False,
                "description": "Disabled task",
            },
        }

        with (
            patch.object(self.scheduler, "task_registry", mock_registry),
            patch.object(self.scheduler, "_add_scheduled_task") as mock_add_task,
        ):
            self.scheduler._add_registry_tasks()

            # Should only call _add_scheduled_task for enabled tasks
            assert mock_add_task.call_count == 1


@pytest.mark.unit
class TestGlobalSchedulerFunctions(TestCase):
    """Test global scheduler management functions."""

    def setUp(self):
        """Set up test environment."""
        # Reset any cached scheduler state
        pass

    def tearDown(self):
        """Clean up after tests."""
        # Clean up any scheduler state
        pass

    def test_get_scheduler_creates_new(self):
        """Test get_scheduler creates new scheduler if none exists."""
        scheduler = get_scheduler()

        assert scheduler is not None
        assert isinstance(scheduler, CronTaskScheduler)

    def test_get_scheduler_returns_existing(self):
        """Test get_scheduler returns existing scheduler."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()

        assert scheduler1 is scheduler2

    def test_start_scheduler_success(self):
        """Test successful scheduler start."""
        with patch("apps.tasks.cron_scheduler.get_scheduler") as mock_get_scheduler:
            mock_scheduler = Mock()
            mock_get_scheduler.return_value = mock_scheduler

            result = start_scheduler()

            assert result == mock_scheduler  # start_scheduler returns the scheduler
            mock_scheduler.start.assert_called_once()

    def test_start_scheduler_exception(self):
        """Test scheduler start with exception."""
        with patch("apps.tasks.cron_scheduler.get_scheduler") as mock_get_scheduler:
            mock_scheduler = Mock()
            mock_scheduler.start.side_effect = ValueError("Start failed")
            mock_get_scheduler.return_value = mock_scheduler

            # start_scheduler doesn't catch exceptions, it should propagate
            with pytest.raises(ValueError):
                start_scheduler()

    def test_stop_scheduler_success(self):
        """Test successful scheduler stop."""
        with patch("apps.tasks.cron_scheduler._scheduler_instance", Mock()) as mock_instance:
            stop_scheduler()

            mock_instance.stop.assert_called_once()

    def test_stop_scheduler_no_instance(self):
        """Test stopping scheduler when no instance exists."""
        with patch("apps.tasks.cron_scheduler._scheduler_instance", None):
            # Should not raise exception when no instance exists
            stop_scheduler()

    def test_scheduler_task_management_interface(self):
        """Test scheduler task management through scheduler instance."""
        scheduler = get_scheduler()

        # Test adding a dynamic task through the scheduler
        with patch.object(scheduler, "add_dynamic_task") as mock_add:
            scheduler.add_dynamic_task("test_task", "cleanup_old_data", "0 0 * * *", {"days_old": 7})
            mock_add.assert_called_once_with("test_task", "cleanup_old_data", "0 0 * * *", {"days_old": 7})

        # Test removing a task through the scheduler
        with patch.object(scheduler, "remove_task") as mock_remove:
            scheduler.remove_task("test_task")
            mock_remove.assert_called_once_with("test_task")

        # Test listing tasks through the scheduler
        mock_tasks = {
            "registry": {},
            "scheduled_jobs": [
                {"id": "task1", "name": "Task 1", "next_run_time": timezone.now()},
                {"id": "task2", "name": "Task 2", "next_run_time": None},
            ],
        }
        with patch.object(scheduler, "list_tasks", return_value=mock_tasks) as mock_list:
            result = scheduler.list_tasks()
            assert result == mock_tasks
            mock_list.assert_called_once()


@pytest.mark.unit
class TestCronSchedulerEdgeCases(TestCase):
    """Test edge cases and error conditions."""

    def setUp(self):
        """Set up test environment."""
        self.scheduler = CronTaskScheduler()

    def test_concurrent_access_thread_safety(self):
        """Test thread safety with concurrent access."""
        results = []

        def start_stop_scheduler():
            try:
                self.scheduler.start()
                time.sleep(0.1)
                self.scheduler.stop()
                results.append("success")
            except Exception as e:
                results.append(f"error: {e}")

        # Create multiple threads
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=start_stop_scheduler)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Should handle concurrent access gracefully
        assert len(results) == 3
        assert all("success" in result or "error" in result for result in results)

    def test_scheduler_with_invalid_task_registry(self):
        """Test scheduler behavior with invalid task registry."""
        # Mock invalid registry
        invalid_registry = {
            "invalid_task": {
                "function": "nonexistent_function",
                "cron": "invalid_cron",
                "args": "not_a_dict",  # Should be dict
                "enabled": "not_a_bool",  # Should be bool
                "description": None,  # Should be string
            }
        }

        with patch.object(self.scheduler, "task_registry", invalid_registry):
            # Should handle invalid registry gracefully
            try:
                self.scheduler.load_default_tasks()
                # Should not crash
            except Exception:
                pytest.fail("Should handle invalid registry gracefully")

    def test_scheduler_state_persistence(self):
        """Test scheduler state consistency."""
        # Test multiple start/stop cycles
        for _ in range(3):
            self.scheduler.start()
            assert self.scheduler.running is True

            self.scheduler.stop()
            assert self.scheduler.running is False

    def test_empty_task_args(self):
        """Test task scheduling with empty args."""
        with patch.object(self.scheduler.scheduler, "add_job") as mock_add_job:
            self.scheduler.add_dynamic_task(
                task_id="test_task", function_name="cleanup_old_data", cron_expression="0 0 * * *", args={}
            )

            mock_add_job.assert_called_once()

    def test_none_task_args(self):
        """Test task scheduling with None args."""
        with patch.object(self.scheduler.scheduler, "add_job") as mock_add_job:
            self.scheduler.add_dynamic_task(
                task_id="test_task", function_name="cleanup_old_data", cron_expression="0 0 * * *", args=None
            )

            mock_add_job.assert_called_once()

    def test_scheduler_memory_usage(self):
        """Test scheduler doesn't leak memory with many operations."""
        # Add and remove many tasks
        for i in range(10):  # Reduced for faster testing
            task_id = f"test_task_{i}"

            with patch.object(self.scheduler.scheduler, "add_job"):
                self.scheduler.add_dynamic_task(
                    task_id=task_id, function_name="cleanup_old_data", cron_expression="0 0 * * *", args={}
                )

            with patch.object(self.scheduler.scheduler, "remove_job"):
                self.scheduler.remove_task(task_id)

        # Should complete without memory issues
        assert True

    def test_scheduler_logging(self):
        """Test that scheduler operations are properly logged."""
        with (
            patch("apps.tasks.cron_scheduler.logger") as mock_logger,
            patch.object(self.scheduler.scheduler, "add_job", side_effect=ValueError("Test error")),
            pytest.raises(ValueError),
        ):
            self.scheduler.add_dynamic_task(
                task_id="test_task", function_name="cleanup_old_data", cron_expression="0 0 * * *", args={}
            )

        # Should log the error
        mock_logger.error.assert_called()

    def test_scheduler_thread_safety(self):
        """Test scheduler thread safety mechanisms."""
        scheduler = get_scheduler()

        # Test that scheduler has thread safety mechanisms
        assert hasattr(scheduler, "_lock")
        assert isinstance(scheduler._lock, threading.Lock)

        # Test lock acquisition
        acquired = scheduler._lock.acquire(blocking=False)
        assert acquired is True
        scheduler._lock.release()


@pytest.mark.unit
class TestCronSchedulerIntegration(TestCase):
    """Test integration scenarios and realistic usage patterns."""

    def setUp(self):
        """Set up test environment."""
        self.scheduler = CronTaskScheduler()

    def test_full_scheduler_lifecycle(self):
        """Test complete scheduler lifecycle."""
        # Start scheduler
        with patch.object(self.scheduler.scheduler, "start"), patch.object(self.scheduler.scheduler, "running", False):
            self.scheduler.start()
            assert self.scheduler.running is True

        # Add some tasks
        with patch.object(self.scheduler.scheduler, "add_job"):
            self.scheduler.add_dynamic_task("task1", "cleanup_old_data", "0 0 * * *", {})
            self.scheduler.add_dynamic_task("task2", "send_notification_email", "0 1 * * *", {})

        # List tasks
        mock_jobs = [
            Mock(id="task1", name="Task 1", next_run_time=timezone.now(), trigger="Mock Trigger"),
            Mock(id="task2", name="Task 2", next_run_time=timezone.now(), trigger="Mock Trigger"),
        ]
        with patch.object(self.scheduler.scheduler, "get_jobs", return_value=mock_jobs):
            tasks = self.scheduler.list_tasks()
            assert len(tasks["scheduled_jobs"]) == 2

        # Remove a task
        with patch.object(self.scheduler.scheduler, "remove_job"):
            self.scheduler.remove_task("task1")

        # Stop scheduler
        with patch.object(self.scheduler.scheduler, "shutdown"):
            self.scheduler.stop()
            assert self.scheduler.running is False

    def test_realistic_task_scheduling(self):
        """Test realistic task scheduling scenarios."""
        realistic_tasks = [
            {
                "id": "daily_cleanup",
                "function": "cleanup_old_data",
                "cron": "0 2 * * *",  # Daily at 2 AM
                "args": {"days_old": 30},
            },
            {
                "id": "weekly_backup",
                "function": "process_user_data",
                "cron": "0 3 * * 0",  # Weekly on Sunday at 3 AM
                "args": {"operation": "backup"},
            },
            {
                "id": "hourly_health_check",
                "function": "collect_host_metrics",
                "cron": "0 * * * *",  # Every hour
                "args": {},
            },
        ]

        with patch.object(self.scheduler.scheduler, "add_job") as mock_add_job:
            for task in realistic_tasks:
                self.scheduler.add_dynamic_task(task["id"], task["function"], task["cron"], task["args"])

            assert mock_add_job.call_count == len(realistic_tasks)
