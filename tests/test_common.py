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
