"""
Common test utilities and base classes to reduce duplication across test files.
"""

import unittest
from unittest.mock import patch

# Mock Django before importing any Django modules
from django.conf import settings


class BaseTaskFunctionsTest(unittest.TestCase):
    """Base test case for task functions with common test methods."""

    def test_task_functions_registry(self):
        """Test TASK_FUNCTIONS registry."""
        from apps.tasks.tasks import TASK_FUNCTIONS

        expected_functions = [
            "hello_world",
            "cleanup_old_tasks",
        ]

        for func_name in expected_functions:
            self.assertIn(func_name, TASK_FUNCTIONS)
            self.assertTrue(callable(TASK_FUNCTIONS[func_name]))


class BaseTaskSchedulerTest(unittest.TestCase):
    """Base test case for TaskScheduler with common test methods."""

    def test_task_scheduler_init(self):
        """Test UnifiedTaskScheduler initialization."""
        from apps.tasks.cron_scheduler import UnifiedTaskScheduler

        scheduler = UnifiedTaskScheduler(check_interval=30)
        self.assertEqual(scheduler.check_interval, 30)
        self.assertFalse(scheduler.running)

    def test_task_scheduler_stop(self):
        """Test UnifiedTaskScheduler stop method."""

        from apps.tasks.cron_scheduler import UnifiedTaskScheduler

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
