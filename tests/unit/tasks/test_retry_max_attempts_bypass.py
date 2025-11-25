"""
Test to verify that retry() does not bypass max_attempts limit.

This test demonstrates that resetting attempts to 0 in retry() allows
indefinite retries, effectively bypassing the max_attempts protection.
"""

from unittest.mock import patch

import pytest
from django.test import TestCase

from apps.tasks.models import Task


@pytest.mark.unit
class TestRetryMaxAttemptsBypass(TestCase):
    """Test that retry() properly respects max_attempts limit."""

    @patch("apps.tasks.tasks_system.submit_task_to_dispatcher")
    def test_retry_does_not_bypass_max_attempts(self, mock_submit):
        """
        Test that repeated retry() calls respect max_attempts limit.

        This verifies that the attempts counter is NOT reset to 0 on retry,
        preventing indefinite retries that would bypass max_attempts.
        """
        # Create a task with max_attempts=3
        task = Task.objects.create(
            name="Test Task",
            function_name="cleanup_old_data",
            status="failed",
            attempts=1,
            max_attempts=3,
        )

        # First retry should succeed (attempts=1 < max_attempts=3)
        assert task.can_retry() is True
        result = task.retry()
        assert result is True

        task.refresh_from_db()
        assert task.status == "pending"
        # CRITICAL: attempts should NOT be reset to 0
        # It should remain at 1 to track total execution attempts
        assert task.attempts == 1

        # Simulate task running and failing again (attempts increments to 2)
        task.status = "failed"
        task.attempts = 2
        task.save()

        # Second retry should succeed (attempts=2 < max_attempts=3)
        assert task.can_retry() is True
        result = task.retry()
        assert result is True

        task.refresh_from_db()
        assert task.status == "pending"
        # attempts should still be 2, not reset to 0
        assert task.attempts == 2

        # Simulate task running and failing again (attempts increments to 3)
        task.status = "failed"
        task.attempts = 3
        task.save()

        # Third retry should FAIL (attempts=3 >= max_attempts=3)
        assert task.can_retry() is False
        result = task.retry()
        assert result is False

        task.refresh_from_db()
        # Task should remain failed
        assert task.status == "failed"
        assert task.attempts == 3

    @patch("apps.tasks.tasks_system.submit_task_to_dispatcher")
    def test_retry_tracks_total_attempts_not_per_retry_attempts(self, mock_submit):
        """
        Test that attempts counter tracks total execution attempts, not per-retry attempts.

        The attempts counter should increment with each execution, regardless of whether
        it was an automatic retry or a manual retry() call.
        """
        # Create a task that has already failed once
        task = Task.objects.create(
            name="Test Task",
            function_name="cleanup_old_data",
            status="failed",
            attempts=2,  # Already tried twice
            max_attempts=3,
        )

        # Should be able to retry one more time (2 < 3)
        assert task.can_retry() is True
        result = task.retry()
        assert result is True

        task.refresh_from_db()
        assert task.status == "pending"
        # attempts should stay at 2, tracking total attempts
        assert task.attempts == 2

        # After this next execution (which would make it 3), no more retries
        task.status = "failed"
        task.attempts = 3
        task.save()

        # Now can_retry should return False
        assert task.can_retry() is False
        result = task.retry()
        assert result is False

