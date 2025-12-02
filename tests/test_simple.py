"""
Simple tests that actually work without complex Django setup.
"""

from .test_common import (
    BaseTaskFunctionsTest,
    BaseTaskSchedulerTest,
    BaseUtilitiesTest,
)


class TestTaskFunctions(BaseTaskFunctionsTest):
    """Test task functions directly."""

    def test_send_notification_email_default_subject(self):
        """Test send_notification_email with default subject."""
        from apps.tasks.tasks import send_notification_email

        result = send_notification_email(recipient="test@example.com")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["subject"], "Notification")


class TestTaskScheduler(BaseTaskSchedulerTest):
    """Test TaskScheduler class."""


class TestUtilities(BaseUtilitiesTest):
    """Test utility functions."""
