"""
Simple tests that actually work without complex Django setup.
"""

from unittest.mock import patch

from .test_common import (
    BaseHealthChecksTest,
    BaseTaskFunctionsTest,
    BaseTaskSchedulerTest,
    BaseUtilitiesTest,
    setup_django_for_tests,
)

# Setup Django for testing
setup_django_for_tests()


class TestTaskFunctions(BaseTaskFunctionsTest):
    """Test task functions directly."""

    def test_send_notification_email_default_subject(self):
        """Test send_notification_email with default subject."""
        from apps.tasks.tasks import send_notification_email

        data = {"recipient": "test@example.com"}
        result = send_notification_email(data)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["subject"], "Notification")


class TestHealthChecks(BaseHealthChecksTest):
    """Test health check functions with correct names."""

    # Override the base cache test to include the delete mock
    @patch("django.core.cache.cache.get")
    @patch("django.core.cache.cache.set")
    @patch("django.core.cache.cache.delete")
    def test_cache_check_success(self, mock_delete, mock_set, mock_get):
        """Test successful cache check."""
        from apps.health.checks import check_cache

        mock_get.return_value = "test_value"

        result = check_cache()

        self.assertIsInstance(result, dict)
        self.assertIn("status", result)
        mock_set.assert_called()
        mock_get.assert_called()


class TestTaskScheduler(BaseTaskSchedulerTest):
    """Test TaskScheduler class."""


class TestUtilities(BaseUtilitiesTest):
    """Test utility functions."""


if __name__ == "__main__":
    import unittest

    unittest.main()
