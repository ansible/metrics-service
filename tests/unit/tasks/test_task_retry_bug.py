"""
Test for task retry bug where retry is silently skipped due to existing TaskExecution records.

This test reproduces the bug where calling retry() on a failed task with existing
TaskExecution records causes the retry to be silently skipped because the signal
handler checks for existing executions and prevents duplicate submissions.
"""

from unittest.mock import patch

import pytest
from django.test import TestCase

from apps.tasks.models import Task, TaskExecution


@pytest.mark.unit
class TestTaskRetryBug(TestCase):
    """Test that verifies the task retry bug and its fix."""

    def setUp(self):
        """Set up test data."""
        # Create a failed task with execution history
        self.task = Task.objects.create(
            name="Failed Task",
            function_name="cleanup_old_data",
            status="failed",
            attempts=1,
            max_attempts=3,
            error_message="Something went wrong",
        )

        # Create a TaskExecution record to simulate previous failed attempt
        self.execution = TaskExecution.objects.create(
            task=self.task, status="failed", error_message="Something went wrong"
        )

    @patch("apps.tasks.tasks_system.submit_task_to_dispatcher")
    def test_retry_with_existing_executions_should_submit_task(self, mock_submit):
        """
        Test that retry() actually submits the task even when TaskExecution records exist.

        This test verifies that calling retry() on a failed task with existing
        TaskExecution records will properly submit the task to dispatcherd,
        rather than being silently skipped by the signal handler.
        """
        # Verify preconditions
        assert self.task.status == "failed"
        assert self.task.can_retry() is True
        assert TaskExecution.objects.filter(task=self.task).exists()

        # Call retry
        result = self.task.retry()

        # Verify retry was successful
        assert result is True

        # Refresh from database
        self.task.refresh_from_db()

        # Verify task was reset to pending
        assert self.task.status == "pending"
        assert self.task.error_message == ""
        assert self.task.attempts == 0
        assert self.task.started_at is None
        assert self.task.completed_at is None

        # CRITICAL: Verify task was actually submitted to dispatcher
        # This is the bug - without the fix, mock_submit.assert_called_once() will fail
        # because the signal handler skips submission when TaskExecution records exist
        mock_submit.assert_called_once()

        # Verify the task object passed to submit was our task
        call_args = mock_submit.call_args
        submitted_task = call_args[0][0]
        assert submitted_task.id == self.task.id

    @patch("apps.tasks.tasks_system.submit_task_to_dispatcher")
    def test_retry_without_existing_executions_should_submit_task(self, mock_submit):
        """
        Test baseline: retry() works when no TaskExecution records exist.

        This verifies that the issue is specifically related to existing
        TaskExecution records.
        """
        # Delete the execution record
        self.execution.delete()

        # Verify no execution records exist
        assert not TaskExecution.objects.filter(task=self.task).exists()

        # Call retry
        result = self.task.retry()

        # Verify retry was successful
        assert result is True

        # Refresh from database
        self.task.refresh_from_db()

        # Verify task was reset
        assert self.task.status == "pending"

        # This should work even in the buggy version
        mock_submit.assert_called_once()

    def test_retry_returns_false_when_cannot_retry(self):
        """Test that retry returns False when task cannot be retried."""
        # Set task to max attempts
        self.task.attempts = self.task.max_attempts
        self.task.save()

        # Call retry
        result = self.task.retry()

        # Should return False
        assert result is False

        # Task should remain failed
        self.task.refresh_from_db()
        assert self.task.status == "failed"
