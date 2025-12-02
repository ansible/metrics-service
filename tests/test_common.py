"""
Common test utilities and base classes to reduce duplication across test files.
"""

import unittest
from unittest.mock import patch

# Mock Django before importing any Django modules
from django.conf import settings


class BaseTaskFunctionsTest(unittest.TestCase):
    """Base test case for task functions with common test methods."""

    def test_cleanup_old_data(self):
        """Test cleanup_old_data function."""
        from apps.tasks.tasks import cleanup_old_data

        result = cleanup_old_data(days_old=30)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["days_old"], 30)
        self.assertIn("cleaned_count", result)

    def test_send_notification_email(self):
        """Test send_notification_email function."""
        from apps.tasks.tasks import send_notification_email

        result = send_notification_email(recipient="test@example.com", subject="Test Subject", message="Test message")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["recipient"], "test@example.com")
        self.assertEqual(result["subject"], "Test Subject")

    def test_task_functions_registry(self):
        """Test TASK_FUNCTIONS registry."""
        from apps.tasks.tasks import TASK_FUNCTIONS

        expected_functions = [
            "cleanup_old_data",
            "send_notification_email",
            "process_user_data",
            "execute_db_task",
            "hello_world",
            "sleep",
        ]

        for func_name in expected_functions:
            self.assertIn(func_name, TASK_FUNCTIONS)
            self.assertTrue(callable(TASK_FUNCTIONS[func_name]))


class BaseTaskSchedulerTest(unittest.TestCase):
    """Base test case for TaskScheduler with common test methods."""

    def test_task_scheduler_init(self):
        """Test UnifiedTaskScheduler initialization."""
        from apps.tasks.cron_scheduler import UnifiedTaskScheduler

        with patch("apps.tasks.cron_scheduler.get_all_enabled_tasks", return_value={}):
            scheduler = UnifiedTaskScheduler(check_interval=30)
        self.assertEqual(scheduler.check_interval, 30)
        self.assertFalse(scheduler.running)

    def test_task_scheduler_stop(self):
        """Test UnifiedTaskScheduler stop method."""
        from unittest.mock import patch

        from apps.tasks.cron_scheduler import UnifiedTaskScheduler

        with patch("apps.tasks.cron_scheduler.get_all_enabled_tasks", return_value={}):
            scheduler = UnifiedTaskScheduler()
        scheduler.running = True
        with patch.object(scheduler.scheduler, "shutdown"):
            scheduler.stop()
        self.assertFalse(scheduler.running)


class BaseUtilitiesTest(unittest.TestCase):
    """Base test case for utility functions with common test methods."""

    def test_settings_validation(self):
        """Test that critical settings exist."""

        self.assertTrue(hasattr(settings, "SECRET_KEY"))
        self.assertTrue(hasattr(settings, "DATABASES"))
