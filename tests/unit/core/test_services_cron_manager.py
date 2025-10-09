"""
Unit tests for CronManager service.
"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management.base import CommandError
from django.test import TestCase

from apps.core.services.cron_manager import CronManager
from apps.core.services.output_formatter import OutputFormatter


@pytest.mark.unit
class CronManagerTestCase(TestCase):
    """Test cases for CronManager service."""

    def setUp(self):
        """Set up test fixtures."""
        self.stdout = StringIO()
        self.style = MagicMock()
        # Make style methods return the message string directly
        self.style.SUCCESS.side_effect = lambda msg: msg
        self.style.ERROR.side_effect = lambda msg: msg
        self.style.WARNING.side_effect = lambda msg: msg
        self.output_formatter = OutputFormatter(self.stdout, self.style)
        self.cron_manager = CronManager(self.output_formatter)

    def test_initialization(self):
        """Test CronManager initialization."""
        self.assertEqual(self.cron_manager.output, self.output_formatter)

    @patch("apps.tasks.cron_scheduler.start_scheduler")
    def test_start_scheduler_success(self, mock_start_scheduler):
        """Test successful scheduler start."""
        self.cron_manager.start_scheduler()

        mock_start_scheduler.assert_called_once()
        self.style.SUCCESS.assert_called_once_with("Cron scheduler started")

    @patch(
        "apps.tasks.cron_scheduler.start_scheduler",
        side_effect=Exception("Scheduler error"),
    )
    def test_start_scheduler_exception(self, mock_start_scheduler):
        """Test scheduler start with exception."""
        with self.assertRaises(CommandError) as cm:
            self.cron_manager.start_scheduler()

        self.assertIn("Failed to start cron scheduler", str(cm.exception))
        self.assertIn("Scheduler error", str(cm.exception))

    @patch("apps.tasks.cron_scheduler.stop_scheduler")
    def test_stop_scheduler_success(self, mock_stop_scheduler):
        """Test successful scheduler stop."""
        self.cron_manager.stop_scheduler()

        mock_stop_scheduler.assert_called_once()
        self.style.SUCCESS.assert_called_once_with("Cron scheduler stopped")

    @patch(
        "apps.tasks.cron_scheduler.stop_scheduler",
        side_effect=Exception("Stop error"),
    )
    def test_stop_scheduler_exception(self, mock_stop_scheduler):
        """Test scheduler stop with exception."""
        with self.assertRaises(CommandError) as cm:
            self.cron_manager.stop_scheduler()

        self.assertIn("Failed to stop cron scheduler", str(cm.exception))
        self.assertIn("Stop error", str(cm.exception))

    @patch("apps.tasks.cron_scheduler.get_scheduler")
    def test_show_status_running(self, mock_get_scheduler):
        """Test status check when scheduler is running."""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_get_scheduler.return_value = mock_scheduler

        self.cron_manager.show_status()

        mock_get_scheduler.assert_called_once()
        self.style.SUCCESS.assert_called_once_with("Cron scheduler is running")

    @patch("apps.tasks.cron_scheduler.get_scheduler")
    def test_show_status_not_running(self, mock_get_scheduler):
        """Test status check when scheduler is not running."""
        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_get_scheduler.return_value = mock_scheduler

        self.cron_manager.show_status()

        mock_get_scheduler.assert_called_once()
        self.style.WARNING.assert_called_once_with("Cron scheduler is not running")

    @patch(
        "apps.tasks.cron_scheduler.get_scheduler",
        side_effect=Exception("Status error"),
    )
    def test_show_status_exception(self, mock_get_scheduler):
        """Test status check with exception."""
        with self.assertRaises(CommandError) as cm:
            self.cron_manager.show_status()

        self.assertIn("Failed to get cron scheduler status", str(cm.exception))
        self.assertIn("Status error", str(cm.exception))

    @patch("apps.tasks.cron_scheduler.get_scheduler")
    def test_list_tasks_with_data(self, mock_get_scheduler):
        """Test listing tasks with registry and scheduled jobs."""
        mock_scheduler = MagicMock()
        mock_task_info = {
            "registry": {
                "task1": {
                    "function": "cleanup_old_data",
                    "cron": "0 2 * * *",
                    "enabled": True,
                    "description": "Cleanup old data",
                },
                "task2": {
                    "function": "send_notifications",
                    "cron": "0 9 * * MON",
                    "enabled": False,
                    "description": "Send weekly notifications",
                },
            },
            "scheduled_jobs": [
                {
                    "id": "job1",
                    "name": "Cleanup Job",
                    "next_run_time": "2024-01-01 02:00:00",
                    "trigger": "cron",
                },
                {
                    "id": "job2",
                    "name": "Notification Job",
                    "next_run_time": "2024-01-08 09:00:00",
                    "trigger": "cron",
                },
            ],
        }
        mock_scheduler.list_tasks.return_value = mock_task_info
        mock_get_scheduler.return_value = mock_scheduler

        self.cron_manager.list_tasks()

        mock_get_scheduler.assert_called_once()
        mock_scheduler.list_tasks.assert_called_once()

        # Verify output was written (we can't easily check exact output due to
        # StringIO complexity)
        output = self.stdout.getvalue()
        self.assertIn("Task Registry", output)

    @patch("apps.tasks.cron_scheduler.get_scheduler")
    def test_list_tasks_empty(self, mock_get_scheduler):
        """Test listing tasks with empty data."""
        mock_scheduler = MagicMock()
        mock_task_info = {"registry": {}, "scheduled_jobs": []}
        mock_scheduler.list_tasks.return_value = mock_task_info
        mock_get_scheduler.return_value = mock_scheduler

        self.cron_manager.list_tasks()

        mock_get_scheduler.assert_called_once()
        output = self.stdout.getvalue()
        self.assertIn("Task Registry (0 tasks)", output)
        self.assertIn("No jobs currently scheduled", output)

    @patch(
        "apps.tasks.cron_scheduler.get_scheduler",
        side_effect=Exception("List error"),
    )
    def test_list_tasks_exception(self, mock_get_scheduler):
        """Test listing tasks with exception."""
        with self.assertRaises(CommandError) as cm:
            self.cron_manager.list_tasks()

        self.assertIn("Failed to list cron tasks", str(cm.exception))
        self.assertIn("List error", str(cm.exception))

    def test_display_task_registry_with_tasks(self):
        """Test displaying task registry."""
        registry = {
            "enabled_task": {
                "function": "cleanup_function",
                "cron": "0 2 * * *",
                "enabled": True,
                "description": "Cleanup task",
            },
            "disabled_task": {
                "function": "backup_function",
                "cron": "0 3 * * *",
                "enabled": False,
                "description": "Backup task",
            },
            "minimal_task": {
                "function": "minimal_function",
                "cron": "0 4 * * *",
                # No enabled or description keys
            },
        }

        self.cron_manager._display_task_registry(registry)

        output = self.stdout.getvalue()

        # Check header
        self.assertIn("Task Registry (3 tasks)", output)

        # Check enabled task
        self.assertIn("✓ enabled_task", output)
        self.assertIn("cleanup_function", output)
        self.assertIn("0 2 * * *", output)
        self.assertIn("Cleanup task", output)

        # Check disabled task
        self.assertIn("✗ disabled_task", output)
        self.assertIn("backup_function", output)

        # Check minimal task (should default to enabled)
        self.assertIn("✓ minimal_task", output)
        self.assertIn("minimal_function", output)
        self.assertIn("N/A", output)  # Default description

    def test_display_task_registry_empty(self):
        """Test displaying empty task registry."""
        registry = {}

        self.cron_manager._display_task_registry(registry)

        output = self.stdout.getvalue()
        self.assertIn("Task Registry (0 tasks)", output)

    def test_display_scheduled_jobs_with_jobs(self):
        """Test displaying scheduled jobs."""
        scheduled_jobs = [
            {
                "id": "job1",
                "name": "Test Job 1",
                "next_run_time": "2024-01-01 12:00:00",
                "trigger": "cron",
            },
            {
                "id": "job2",
                "name": "Test Job 2",
                "next_run_time": "2024-01-02 13:00:00",
                "trigger": "interval",
            },
        ]

        self.cron_manager._display_scheduled_jobs(scheduled_jobs)

        output = self.stdout.getvalue()

        # Check header
        self.assertIn("Scheduled Jobs (2)", output)

        # Check job details
        self.assertIn("ID: job1", output)
        self.assertIn("Name: Test Job 1", output)
        self.assertIn("Next run: 2024-01-01 12:00:00", output)
        self.assertIn("Trigger: cron", output)

        self.assertIn("ID: job2", output)
        self.assertIn("Name: Test Job 2", output)
        self.assertIn("Trigger: interval", output)

    def test_display_scheduled_jobs_empty(self):
        """Test displaying empty scheduled jobs."""
        scheduled_jobs = []

        self.cron_manager._display_scheduled_jobs(scheduled_jobs)

        output = self.stdout.getvalue()
        self.assertIn("No jobs currently scheduled", output)

    def test_complex_task_registry_edge_cases(self):
        """Test task registry with edge cases."""
        registry = {
            "unicode_task": {
                "function": "unicode_func_测试",
                "cron": "0 2 * * *",
                "enabled": True,
                "description": "Unicode test 🎉",
            },
            "long_description_task": {
                "function": "long_func",
                "cron": "*/5 * * * *",
                "enabled": True,
                "description": "A" * 200,  # Very long description
            },
        }

        # Should not raise any exceptions
        self.cron_manager._display_task_registry(registry)

        output = self.stdout.getvalue()
        self.assertIn("unicode_func_测试", output)
        self.assertIn("Unicode test 🎉", output)
        self.assertIn("A" * 200, output)

    def test_scheduled_jobs_edge_cases(self):
        """Test scheduled jobs with edge cases."""
        scheduled_jobs = [
            {
                "id": "unicode_job_测试",
                "name": "Unicode Job 🚀",
                "next_run_time": "2024-12-31 23:59:59",
                "trigger": "cron",
            }
        ]

        # Should not raise any exceptions
        self.cron_manager._display_scheduled_jobs(scheduled_jobs)

        output = self.stdout.getvalue()
        self.assertIn("unicode_job_测试", output)
        self.assertIn("Unicode Job 🚀", output)

    @patch("apps.tasks.cron_scheduler.get_scheduler")
    def test_list_tasks_missing_keys(self, mock_get_scheduler):
        """Test listing tasks when some keys are missing from task info."""
        mock_scheduler = MagicMock()
        mock_task_info = {
            "registry": {
                "task1": {
                    "function": "test_func",
                    "cron": "0 * * * *",
                    # Missing enabled and description
                }
            }
            # Missing scheduled_jobs key
        }
        mock_scheduler.list_tasks.return_value = mock_task_info
        mock_get_scheduler.return_value = mock_scheduler

        # Should handle missing keys gracefully
        self.cron_manager.list_tasks()

        output = self.stdout.getvalue()
        self.assertIn("Task Registry (1 tasks)", output)
        self.assertIn("No jobs currently scheduled", output)
