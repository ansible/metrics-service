"""
Common test utilities and base classes to reduce duplication across test files.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# Mock Django before importing any Django modules
import django
from django.conf import settings


def setup_django_for_tests():
    """Configure minimal Django settings for testing."""
    # Add the project root to path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)

    # Configure minimal Django settings
    if not settings.configured:
        settings.configure(
            USE_TZ=True,
            SECRET_KEY="test-key",
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "HOST": "127.0.0.1",
                    "PORT": "55432",
                    "USER": "metrics_service",
                    "PASSWORD": "metrics_service",
                    "NAME": "test_metrics_service",
                    "OPTIONS": {
                        "sslmode": "prefer",
                    },
                }
            },
            INSTALLED_APPS=[
                "django.contrib.auth",
                "django.contrib.contenttypes",
            ],
            USE_I18N=False,
            USE_L10N=False,
        )

    django.setup()


class BaseTaskFunctionsTest(unittest.TestCase):
    """Base test case for task functions with common test methods."""

    def test_cleanup_old_data(self):
        """Test cleanup_old_data function."""
        from apps.tasks import cleanup_old_data

        data = {"days_old": 30}
        result = cleanup_old_data(data)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["days_old"], 30)
        self.assertIn("cleaned_count", result)

    def test_send_notification_email(self):
        """Test send_notification_email function."""
        from apps.tasks import send_notification_email

        data = {"recipient": "test@example.com", "subject": "Test Subject", "message": "Test message"}
        result = send_notification_email(data)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["recipient"], "test@example.com")
        self.assertEqual(result["subject"], "Test Subject")

    def test_task_functions_registry(self):
        """Test TASK_FUNCTIONS registry."""
        from apps.tasks import TASK_FUNCTIONS

        expected_functions = ["cleanup_old_data", "send_notification_email", "process_user_data", "execute_db_task"]

        for func_name in expected_functions:
            self.assertIn(func_name, TASK_FUNCTIONS)
            self.assertTrue(callable(TASK_FUNCTIONS[func_name]))


class BaseHealthChecksTest(unittest.TestCase):
    """Base test case for health checks with common test methods."""

    @patch("django.db.connection.cursor")
    def test_database_check_success(self, mock_cursor):
        """Test successful database check."""
        from apps.health.checks import check_database

        mock_cursor_instance = Mock()
        mock_cursor.return_value.__enter__ = Mock(return_value=mock_cursor_instance)
        mock_cursor.return_value.__exit__ = Mock(return_value=None)

        result = check_database()

        self.assertIsInstance(result, dict)
        self.assertIn("status", result)
        self.assertEqual(result["status"], "healthy")

    @patch("django.db.connection.cursor")
    def test_database_check_failure(self, mock_cursor):
        """Test database check failure."""
        from apps.health.checks import check_database

        mock_cursor.side_effect = Exception("Database error")

        result = check_database()

        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "unhealthy")
        self.assertIn("error", result)

    @patch("django.core.cache.cache.get")
    @patch("django.core.cache.cache.set")
    def test_cache_check_success(self, mock_set, mock_get):
        """Test successful cache check."""
        from apps.health.checks import check_cache

        mock_get.return_value = "test_value"

        result = check_cache()

        self.assertIsInstance(result, dict)
        self.assertIn("status", result)
        mock_set.assert_called()
        mock_get.assert_called()


class BaseTaskSchedulerTest(unittest.TestCase):
    """Base test case for TaskScheduler with common test methods."""

    def test_task_scheduler_init(self):
        """Test TaskScheduler initialization."""
        from apps.tasks import TaskScheduler

        scheduler = TaskScheduler(poll_interval=60)
        self.assertEqual(scheduler.poll_interval, 60)
        self.assertFalse(scheduler.running)

    def test_task_scheduler_stop(self):
        """Test TaskScheduler stop method."""
        from apps.tasks import TaskScheduler

        scheduler = TaskScheduler()
        scheduler.running = True
        scheduler.stop()
        self.assertFalse(scheduler.running)


class BaseUtilitiesTest(unittest.TestCase):
    """Base test case for utility functions with common test methods."""

    def test_settings_validation(self):
        """Test that critical settings exist."""
        from django.conf import settings

        self.assertTrue(hasattr(settings, "SECRET_KEY"))
        self.assertTrue(hasattr(settings, "DATABASES"))
