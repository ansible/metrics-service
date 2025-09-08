"""
Simple tests that actually work without complex Django setup.
"""

from .test_common import (
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
        from apps.core.tasks import send_notification_email

        data = {"recipient": "test@example.com"}
        result = send_notification_email(data)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["subject"], "Notification")


class TestTaskScheduler(BaseTaskSchedulerTest):
    """Test TaskScheduler class."""


class TestUtilities(BaseUtilitiesTest):
    """Test utility functions."""


if __name__ == "__main__":
    import unittest

    unittest.main()
