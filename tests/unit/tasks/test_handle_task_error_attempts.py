"""
Test that handle_task_error correctly increments attempts counter.

This test verifies the fix for the issue where tasks that failed before
reaching "running" status would never have their attempts counter incremented,
leading to potential infinite retry loops.
"""

import pytest
from django.test import TestCase

from apps.core.models import User
from apps.tasks.models import Task, TaskExecution
from apps.tasks.utils import handle_task_error, update_task_status


@pytest.mark.unit
class TestHandleTaskErrorAttempts(TestCase):
    """Test handle_task_error correctly increments attempts."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_handle_task_error_increments_attempts_for_pending_task(self):
        """
        Test that handle_task_error increments attempts for a task that fails
        before reaching "running" status (early failure scenario).
        """
        # Create a task in pending status (never started running)
        task = Task.objects.create(
            name="Test Task",
            function_name="test_func",
            status="pending",
            attempts=0,
            max_attempts=3,
            created_by=self.user,
        )

        # Create an execution record
        execution = TaskExecution.objects.create(task=task, status="pending", worker_id="test-worker")

        # Simulate an error that occurs before the task reaches "running" status
        # (e.g., function not found, invalid parameters, etc.)
        result = handle_task_error(
            task_instance=task,
            execution_instance=execution,
            error_message="Function not found",
        )

        # Refresh from database
        task.refresh_from_db()

        # Verify attempts was incremented
        assert task.attempts == 1, "Attempts should be incremented for early failure"
        assert task.status == "failed"
        assert task.error_message == "Function not found"
        assert task.completed_at is not None
        assert result["status"] == "error"

    def test_handle_task_error_does_not_double_increment_for_running_task(self):
        """
        Test that handle_task_error does NOT double-increment attempts for a task
        that already reached "running" status (late failure scenario).
        """
        # Create a task in pending status
        task = Task.objects.create(
            name="Test Task",
            function_name="test_func",
            status="pending",
            attempts=0,
            max_attempts=3,
            created_by=self.user,
        )

        execution = TaskExecution.objects.create(task=task, status="pending", worker_id="test-worker")

        # First, transition to "running" status (this should increment attempts to 1)
        update_task_status(task, execution, status="running")
        task.refresh_from_db()
        assert task.attempts == 1, "Attempts should be 1 after transitioning to running"
        assert task.status == "running"

        # Now simulate an error that occurs during task execution
        result = handle_task_error(
            task_instance=task,
            execution_instance=execution,
            error_message="Task execution failed",
        )

        # Refresh from database
        task.refresh_from_db()

        # Verify attempts was NOT incremented again (should still be 1)
        assert task.attempts == 1, "Attempts should not be double-incremented for late failure"
        assert task.status == "failed"
        assert task.error_message == "Task execution failed"
        assert task.completed_at is not None
        assert result["status"] == "error"

    def test_handle_task_error_allows_correct_retry_behavior(self):
        """
        Test that the fix prevents infinite retry loops by correctly
        incrementing attempts for early failures.
        """
        # Create a task that will fail before reaching "running" status
        task = Task.objects.create(
            name="Test Task",
            function_name="test_func",
            status="pending",
            attempts=0,
            max_attempts=3,
            created_by=self.user,
        )

        execution = TaskExecution.objects.create(task=task, status="pending", worker_id="test-worker")

        # Simulate multiple early failures (e.g., function not found each time)
        for expected_attempts in range(1, 4):
            # Simulate failure before reaching "running" status
            handle_task_error(
                task_instance=task,
                execution_instance=execution,
                error_message="Function not found",
            )

            task.refresh_from_db()
            assert task.attempts == expected_attempts, f"Attempts should be {expected_attempts}"
            assert task.status == "failed"

            # After each failure, check if task can be retried
            # Task should be retryable before max_attempts is reached
            if expected_attempts < 3:
                assert task.can_retry() is True, f"Task should be retryable at attempt {expected_attempts}"
                # Reset task to pending to simulate retry (this is what would happen in practice)
                task.status = "pending"
                task.error_message = ""
                task.save()
            else:
                assert task.can_retry() is False, "Task should not be retryable after max_attempts reached"

        # Final verification: After 3 attempts, task should NOT be retryable
        task.refresh_from_db()
        assert task.attempts == 3
        assert task.can_retry() is False, "Task should not be retryable after max_attempts reached"

    def test_handle_task_error_with_waiting_for_dependencies_status(self):
        """
        Test that handle_task_error increments attempts for a task in
        "waiting_for_dependencies" status that fails.
        """
        task = Task.objects.create(
            name="Test Task",
            function_name="test_func",
            status="waiting_for_dependencies",
            attempts=0,
            max_attempts=3,
            created_by=self.user,
        )

        execution = TaskExecution.objects.create(task=task, status="pending", worker_id="test-worker")

        # Simulate an error
        handle_task_error(
            task_instance=task,
            execution_instance=execution,
            error_message="Dependency check failed",
        )

        task.refresh_from_db()

        # Verify attempts was incremented
        assert task.attempts == 1, "Attempts should be incremented for waiting_for_dependencies status"
        assert task.status == "failed"

    def test_handle_task_error_with_task_id_and_execution_id(self):
        """
        Test that handle_task_error works correctly when called with
        task_id and execution_id instead of instances.
        """
        task = Task.objects.create(
            name="Test Task",
            function_name="test_func",
            status="pending",
            attempts=0,
            max_attempts=3,
            created_by=self.user,
        )

        execution = TaskExecution.objects.create(task=task, status="pending", worker_id="test-worker")

        # Call with IDs instead of instances (as done in execute_db_task line 404)
        result = handle_task_error(
            task_id=task.id,
            execution_id=execution.id,
            error_message="Task failed with exception",
        )

        task.refresh_from_db()

        # Verify attempts was incremented
        assert task.attempts == 1, "Attempts should be incremented when called with task_id"
        assert task.status == "failed"
        assert task.error_message == "Task failed with exception"
        assert result["status"] == "error"
