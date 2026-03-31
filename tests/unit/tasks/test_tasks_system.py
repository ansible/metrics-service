"""
Comprehensive tests for task system functionality.

This module tests the complete task system including task functions, registry,
system task creation, execution, and helper functions.

Organized into clear test classes:
- TestExecuteDbTask: Database task execution and error handling
- TestTaskRegistry: TASK_FUNCTIONS and TASK_METADATA configuration
- TestSystemTaskCreation: System task initialization and management
- TestTaskDispatcher: Task submission and dispatcher integration
- TestEdgeCasesAndErrorHandling: Edge cases, error conditions, and resilience
"""

from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tasks import tasks, tasks_system
from apps.tasks.models import Task, TaskExecution
from apps.tasks.tasks import (
    TASK_FUNCTIONS,
    submit_task_to_dispatcher,
)
from apps.tasks.tasks_system import execute_db_task
from tests.test_utils import get_test_password

User = get_user_model()


# =============================================================================
# Execute DB Task Tests
# =============================================================================


@pytest.mark.unit
class TestExecuteDbTask(TestCase):
    """Test execute_db_task function and database task execution."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="taskuser")
        self.task = self._create_task_safely(name="Test Task", function_name="hello_world", task_data={})

    def _create_task_safely(self, **kwargs):
        """Create a task without triggering signals."""
        task = Task(**kwargs)
        task.save()
        return task

    @pytest.mark.django_db(transaction=True)
    def test_execute_db_task_success(self):
        """Test successful task execution."""
        result = execute_db_task(task_id=self.task.id)

        assert result["status"] == "success"

        # Verify task state was updated
        self.task.refresh_from_db()
        assert self.task.status == "completed"
        assert self.task.attempts == 1
        assert self.task.started_at is not None
        assert self.task.completed_at is not None

    @pytest.mark.django_db(transaction=True)
    def test_execute_db_task_already_claimed(self):
        """Test that a task already claimed by another worker is skipped."""
        self.task.status = "running"
        self.task.save()

        result = execute_db_task(task_id=self.task.id)

        assert result["status"] == "error"
        assert "already claimed" in result["error"]

        # Task status should remain running (not overwritten)
        self.task.refresh_from_db()
        assert self.task.status == "running"

    @pytest.mark.django_db(transaction=True)
    def test_losing_claim_creates_no_execution(self):
        """Test that a failed claim leaves no orphaned TaskExecution records.

        Before the fix, submit_task_to_dispatcher created a TaskExecution eagerly,
        and a losing claimer would leave it stuck as pending forever. Now _claim_task
        only creates the execution on success, so a loser must produce zero records.
        """
        # Simulate another worker already claimed the task
        self.task.status = "running"
        self.task.save()

        result = execute_db_task(task_id=self.task.id)

        assert result["status"] == "error"
        # No TaskExecution should have been created
        assert TaskExecution.objects.filter(task=self.task).count() == 0

    @pytest.mark.django_db(transaction=True)
    def test_execute_db_task_creates_execution_record(self):
        """Test that execute_db_task creates a TaskExecution record via _claim_task."""
        result = execute_db_task(task_id=self.task.id)

        assert result["status"] == "success"

        # _claim_task should have created an execution record
        execution = TaskExecution.objects.filter(task=self.task).first()
        assert execution is not None
        assert execution.status == "completed"

    def test_execute_db_task_no_task_id(self):
        """Test execute_db_task without task_id parameter."""
        result = execute_db_task()

        assert result["status"] == "error"
        assert "task_id is required" in result["error"]

    def test_execute_db_task_task_not_found(self):
        """Test execute_db_task with non-existent task ID."""
        result = execute_db_task(task_id=99999)

        assert result["status"] == "error"
        assert "Task matching query does not exist" in result["error"]

    def test_execute_db_task_function_not_found(self):
        """Test execute_db_task with unknown function name."""
        self.task.function_name = "unknown_function"
        self.task.save()

        result = execute_db_task(task_id=self.task.id)

        assert result["status"] == "error"
        assert "not found in TASK_FUNCTIONS" in result["error"]

        # Task should be marked as failed
        self.task.refresh_from_db()
        assert self.task.status == "failed"

    @patch("apps.tasks.tasks.TASK_FUNCTIONS")
    def test_execute_db_task_function_exception(self, mock_task_functions):
        """Test execute_db_task when task function raises exception."""
        mock_function = Mock(side_effect=Exception("Test exception"))
        mock_task_functions.__getitem__.return_value = mock_function
        mock_task_functions.__contains__.return_value = True

        result = execute_db_task(task_id=self.task.id)

        assert result["status"] == "error"
        assert "Test exception" in result["error"]

    @pytest.mark.django_db(transaction=True)
    def test_execute_db_task_auto_retry_with_delay(self):
        """Test auto-retry sets delay from task_data retry_delay_seconds."""
        from django.utils import timezone

        self.task.function_name = "hello_world"
        self.task.max_attempts = 3
        self.task.task_data = {"retry_delay_seconds": 120}
        self.task.save()

        before = timezone.now()

        with patch("apps.tasks.tasks.TASK_FUNCTIONS") as mock_fns:
            mock_fns.__contains__.return_value = True
            mock_fns.__getitem__.return_value = Mock(return_value={"status": "error", "error": "fail"})
            result = execute_db_task(task_id=self.task.id)

        assert result["status"] == "error"
        self.task.refresh_from_db()
        # Task should have been retried with delay
        assert self.task.status == "pending"
        assert self.task.scheduled_time is not None
        # scheduled_time should be ~120s after the retry call
        delta = (self.task.scheduled_time - before).total_seconds()
        assert 118 <= delta <= 125, f"Expected scheduled_time ~120s in the future, got {delta:.1f}s"


# =============================================================================
# Task Registry Tests
# =============================================================================


@pytest.mark.unit
class TestTaskRegistry(TestCase):
    """Test TASK_FUNCTIONS registry and task configuration."""

    def test_task_functions_registry_exists(self):
        """Test that TASK_FUNCTIONS registry exists and is properly configured."""
        assert hasattr(tasks, "TASK_FUNCTIONS")
        assert isinstance(tasks.TASK_FUNCTIONS, dict)

    def test_task_functions_contains_expected_functions(self):
        """Test TASK_FUNCTIONS contains all expected task functions."""
        expected_functions = [
            "hello_world",
            "cleanup_old_tasks",
        ]

        for func_name in expected_functions:
            assert func_name in TASK_FUNCTIONS, f"{func_name} not in TASK_FUNCTIONS"
            assert callable(TASK_FUNCTIONS[func_name]), f"{func_name} is not callable"

    def test_task_function_signatures(self):
        """Test task functions accept keyword arguments."""
        import inspect

        for func_name, func in TASK_FUNCTIONS.items():
            sig = inspect.signature(func)
            # Every task function must accept **kwargs
            has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            assert has_var_keyword, f"{func_name} does not accept **kwargs"


# =============================================================================
# System Task Creation Tests
# =============================================================================


@pytest.mark.unit
class TestSystemTaskCreation(TestCase):
    """Test system task initialization and management."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_create_system_tasks_with_disabled_tasks(self):
        """Test handling of disabled system tasks."""
        with patch("apps.tasks.task_groups.get_all_tasks_for_init", return_value={}):
            result = tasks_system.create_system_tasks()

            # All tasks filtered out
            assert result["created"] == 0
            assert result["removed"] == 0

    def test_all_system_tasks_deleted_on_reinit(self):
        """All existing system tasks are unconditionally removed on reinit.

        create_system_tasks() is only called from the init container, before
        the app starts, so no tasks can be running at that point.
        """
        for name in ("task_a", "task_b"):
            Task.objects.create(name=name, function_name="hello_world", is_system_task=True)
        with patch("apps.tasks.task_groups.get_all_tasks_for_init", return_value={}):
            result = tasks_system.create_system_tasks()

        assert result["removed"] == 2
        assert Task.objects.filter(is_system_task=True).count() == 0


# =============================================================================
# System Task Helper Functions Tests
# =============================================================================


# =============================================================================
# Task Dispatcher Tests
# =============================================================================


@pytest.mark.unit
class TestTaskDispatcher(TestCase):
    """Test task submission and dispatcher integration."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="submituser")
        # Create task without triggering signals
        self.task = Task(name="Submit Task", function_name="hello_world", created_by=self.user)
        self.task.save()

    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    def test_submit_task_to_dispatcher_handles_exception(self, mock_ensure_config):
        """Test submit_task_to_dispatcher handles exceptions gracefully."""
        mock_ensure_config.side_effect = Exception("Connection error")

        submit_task_to_dispatcher(self.task)

        # Task should be marked as failed
        self.task.refresh_from_db()
        assert self.task.status == "failed"
        assert "Failed to submit to dispatcher" in self.task.error_message

    @patch("dispatcherd.publish.submit_task")
    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    @patch("apps.tasks.dispatcherd_config.get_queue_for_function")
    def test_submit_skips_when_active_execution_exists(self, mock_get_queue, mock_ensure_config, mock_submit):
        """Test that submit_task_to_dispatcher is a no-op when a pending/running execution exists."""
        # Create an existing pending execution
        from apps.tasks.models import TaskExecution

        TaskExecution.objects.create(task=self.task, status="pending", worker_id="other-worker")

        submit_task_to_dispatcher(self.task)

        # Should not have submitted anything
        mock_submit.assert_not_called()

        # Should still have only the one execution
        assert TaskExecution.objects.filter(task=self.task).count() == 1

    def test_dispatcherd_decorator_functionality(self):
        """Test dispatcherd decorator is properly configured."""
        assert callable(tasks_system.task)

    def test_fallback_decorator(self):
        """Test fallback decorator when dispatcherd is not available."""

        @tasks_system.task()
        def test_function():
            return "test"

        # Decorator should not interfere with function
        result = test_function()
        assert result == "test"


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


@pytest.mark.unit
class TestEdgeCasesAndErrorHandling:
    """Test edge cases, error conditions, and system resilience."""


# =============================================================================
# Task Retry and Error Handling Tests
# =============================================================================


@pytest.mark.unit
class TestTaskRetryBehavior(TestCase):
    """
    Test task retry behavior and error handling.

    This test class consolidates all retry-related tests, including:
    - Retry with existing TaskExecution records
    - max_attempts enforcement during retry
    - Error handling and attempts counter incrementation
    - Prevention of infinite retry loops
    """

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    # Tests from test_task_retry_bug.py
    @patch("apps.tasks.tasks_system.submit_task_to_dispatcher")
    def test_retry_with_existing_executions_should_submit_task(self, mock_submit):
        """
        Test that retry() actually submits the task even when TaskExecution records exist.

        IMPORTANT: The attempts counter should NOT be reset to 0 on retry.
        This ensures max_attempts is properly enforced across all retries.
        """
        # Create a failed task with execution history
        task = Task(
            name="Failed Task",
            function_name="hello_world",
            status="failed",
            attempts=1,
            max_attempts=3,
            error_message="Something went wrong",
        )
        task.save()

        # Create a TaskExecution record to simulate previous failed attempt
        TaskExecution.objects.create(task=task, status="failed", error_message="Something went wrong")

        # Call retry() - this should submit the task despite existing executions
        result = task.retry()

        # Verify retry returned success
        assert result is True

        # Verify task status was updated to pending
        task.refresh_from_db()
        assert task.status == "pending"

        # CRITICAL: Verify attempts was NOT reset to 0
        # This is essential for max_attempts enforcement
        assert task.attempts == 1

        # CRITICAL: Verify task was actually submitted to dispatcher
        # This is the bug fix - tasks with existing executions should still be submitted
        mock_submit.assert_called_once()

    @patch("apps.tasks.tasks_system.submit_task_to_dispatcher")
    def test_retry_updates_error_message(self, mock_submit):
        """Test that retry() clears the error message."""
        task = Task(
            name="Failed Task",
            function_name="hello_world",
            status="failed",
            attempts=1,
            max_attempts=3,
            error_message="Something went wrong",
        )
        task.save()

        result = task.retry()
        assert result is True

        task.refresh_from_db()
        assert task.error_message == ""

    # Tests from test_retry_max_attempts_bypass.py
    @patch("apps.tasks.tasks_system.submit_task_to_dispatcher")
    def test_retry_does_not_bypass_max_attempts(self, mock_submit):
        """
        Test that repeated retry() calls respect max_attempts limit.

        This verifies that the attempts counter is NOT reset to 0 on retry,
        preventing indefinite retries that would bypass max_attempts.
        """
        # Create a task with max_attempts=3
        task = Task(
            name="Test Task",
            function_name="hello_world",
            status="failed",
            attempts=1,
            max_attempts=3,
        )
        task.save()

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
        # Create a task that has already failed twice
        task = Task(
            name="Test Task",
            function_name="hello_world",
            status="failed",
            attempts=2,  # Already tried twice
            max_attempts=3,
        )
        task.save()

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

    # Tests from test_handle_task_error_attempts.py
    def test_handle_task_error_increments_attempts_for_pending_task(self):
        """
        Test that handle_task_error increments attempts for a task that fails
        before reaching "running" status (early failure scenario).
        """
        from apps.tasks.utils import handle_task_error

        # Create a task in pending status (never started running)
        task = Task(
            name="Test Task",
            function_name="test_func",
            status="pending",
            attempts=0,
            max_attempts=3,
            created_by=self.user,
        )
        task.save()

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
        from apps.tasks.utils import handle_task_error, update_task_status

        # Create a task in pending status
        task = Task(
            name="Test Task",
            function_name="test_func",
            status="pending",
            attempts=0,
            max_attempts=3,
            created_by=self.user,
        )
        task.save()

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
        from apps.tasks.utils import handle_task_error

        # Create a task that will fail before reaching "running" status
        task = Task(
            name="Test Task",
            function_name="test_func",
            status="pending",
            attempts=0,
            max_attempts=3,
            created_by=self.user,
        )
        task.save()

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

    def test_handle_task_error_with_task_id_and_execution_id(self):
        """
        Test that handle_task_error works correctly when called with
        task_id and execution_id instead of instances.
        """
        from apps.tasks.utils import handle_task_error

        task = Task(
            name="Test Task",
            function_name="test_func",
            status="pending",
            attempts=0,
            max_attempts=3,
            created_by=self.user,
        )
        task.save()

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


# =============================================================================
# Additional Coverage Tests - Merged from Enhanced Test File
# =============================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestImportErrorFallback(TestCase):
    """Test ImportError fallback for dispatcherd decorator."""

    def test_fallback_decorator_when_dispatcherd_not_available(self):
        """Test task decorator fallback when dispatcherd.publish is not available."""
        # The fallback decorator is defined in lines 28-34 of tasks_system.py
        # It should just return the function unchanged

        # Import with dispatcherd available would use the real decorator
        # But when ImportError occurs, it uses the fallback
        # The fallback is already imported in tasks_system module

        # Test that the fallback decorator works
        @tasks_system.task()
        def dummy_task():
            return "executed"

        result = dummy_task()
        assert result == "executed"


@pytest.mark.unit
@pytest.mark.django_db
class TestSubmitTaskToDispatcherSuccess(TestCase):
    """Test submit_task_to_dispatcher success path."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser_submit", email="test@example.com", password=get_test_password()
        )

    @patch("dispatcherd.publish.submit_task")
    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    @patch("apps.tasks.dispatcherd_config.get_queue_for_function")
    def test_submit_task_success_path(self, mock_get_queue, mock_ensure_config, mock_submit):
        """Test successful task submission to dispatcher."""
        # Arrange
        task = Task.objects.create(
            name="Test Task",
            function_name="hello_world",
            task_data={},
            created_by=self.user,
        )
        mock_get_queue.return_value = "metrics_tasks"

        # Act
        submit_task_to_dispatcher(task)

        # Assert
        # Verify dispatcherd was configured
        mock_ensure_config.assert_called_once()

        # Verify queue was determined
        mock_get_queue.assert_called_once_with("hello_world")

        # Verify task was submitted to dispatcherd
        mock_submit.assert_called_once()
        call_kwargs = mock_submit.call_args.kwargs
        assert call_kwargs["kwargs"]["task_id"] == task.id
        assert "execution_id" not in call_kwargs["kwargs"]
        assert call_kwargs["queue"] == "metrics_tasks"

        # TaskExecution is no longer created here — _claim_task creates it
        assert TaskExecution.objects.filter(task=task).count() == 0

        # Verify task status updated
        task.refresh_from_db()
        assert task.status == "pending"

    @patch("dispatcherd.publish.submit_task")
    @patch("apps.tasks.dispatcherd_config.ensure_dispatcherd_configured")
    @patch("apps.tasks.dispatcherd_config.get_queue_for_function")
    def test_submit_task_handles_submission_error(self, mock_get_queue, mock_ensure_config, mock_submit):
        """Test submit_task_to_dispatcher handles submission errors."""
        # Arrange
        task = Task.objects.create(
            name="Test Task",
            function_name="hello_world",
            created_by=self.user,
        )
        mock_get_queue.return_value = "metrics_tasks"
        mock_submit.side_effect = Exception("Submission failed")

        # Act
        submit_task_to_dispatcher(task)

        # Assert
        task.refresh_from_db()
        assert task.status == "failed"
        assert "Failed to submit to dispatcher" in task.error_message
        assert "Submission failed" in task.error_message


@pytest.mark.unit
@pytest.mark.django_db
class TestCreateSystemTasksExceptionHandling(TestCase):
    """Test create_system_tasks exception handling per task."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(
            username="testuser_exception", email="test@example.com", password=get_test_password()
        )

    @patch("apps.tasks.tasks_system._create_task_from_group")
    @patch("apps.tasks.task_groups.get_all_tasks_for_init")
    def test_handles_exception_creating_individual_task(self, mock_get_tasks, mock_create_task):
        """Test create_system_tasks handles exceptions per task."""
        # Arrange
        mock_get_tasks.return_value = {
            "task1": {"function": "hello_world", "cron": "0 * * * *"},
            "task2": {"function": "cleanup_old_tasks", "cron": "0 2 * * *"},
        }

        # First task fails, second succeeds
        mock_create_task.side_effect = [
            Exception("Creation failed for task1"),
            None,  # Second task succeeds
        ]

        # Act
        result = tasks_system.create_system_tasks()

        # Assert
        # Should have attempted both tasks
        assert mock_create_task.call_count == 2

        # Result should contain error for failed task
        assert any("Error with task1" in msg for msg in result["tasks"])
        assert any("Creation failed" in msg for msg in result["tasks"])


@pytest.mark.unit
@pytest.mark.django_db
class TestGetSystemTaskInfo(TestCase):
    """Test get_system_task_info function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser_sysinfo", email="test@example.com", password=get_test_password()
        )

    def test_returns_system_task_info(self):
        """Test get_system_task_info returns information about system tasks."""
        from django.utils import timezone

        from apps.tasks.tasks_system import get_system_task_info

        # Create system tasks
        Task.objects.create(
            name="System Task 1",
            function_name="cleanup_old_tasks",
            description="Clean up old tasks",
            status="pending",
            cron_expression="0 2 * * *",
            is_system_task=True,
            created_by=self.user,
        )

        Task.objects.create(
            name="System Task 2",
            function_name="hello_world",
            description="Test task",
            status="completed",
            cron_expression="0 * * * *",
            is_system_task=True,
            created_by=self.user,
            completed_at=timezone.now(),
        )

        # Create non-system task (should be excluded)
        Task.objects.create(
            name="Regular Task",
            function_name="hello_world",
            is_system_task=False,
            created_by=self.user,
        )

        # Act
        result = get_system_task_info()

        # Assert
        assert "system_tasks" in result
        assert "total_count" in result
        assert "categories" in result

        assert result["total_count"] == 2
        assert len(result["system_tasks"]) == 2

        # Verify task info structure
        task_info = result["system_tasks"][0]
        assert "id" in task_info
        assert "name" in task_info
        assert "function_name" in task_info
        assert "description" in task_info
        assert "status" in task_info
        assert "cron_expression" in task_info
        assert "created" in task_info
        assert "last_run" in task_info
        assert "category" in task_info

    def test_returns_empty_when_no_system_tasks(self):
        """Test get_system_task_info returns empty list when no system tasks."""
        from apps.tasks.tasks_system import get_system_task_info

        # Act
        result = get_system_task_info()

        # Assert
        assert result["total_count"] == 0
        assert len(result["system_tasks"]) == 0

    def test_formats_datetime_fields_correctly(self):
        """Test get_system_task_info formats datetime fields as ISO strings."""
        from django.utils import timezone

        from apps.tasks.tasks_system import get_system_task_info

        completed_time = timezone.now()
        Task.objects.create(
            name="System Task",
            function_name="hello_world",
            is_system_task=True,
            created_by=self.user,
            completed_at=completed_time,
        )

        # Act
        result = get_system_task_info()

        # Assert
        task_info = result["system_tasks"][0]
        assert task_info["created"] is not None
        assert isinstance(task_info["created"], str)  # ISO format string
        assert task_info["last_run"] is not None
        assert isinstance(task_info["last_run"], str)  # ISO format string

    def test_orders_tasks_by_name(self):
        """Test get_system_task_info orders tasks alphabetically by name."""
        from apps.tasks.tasks_system import get_system_task_info

        Task.objects.create(
            name="Zebra Task",
            function_name="hello_world",
            is_system_task=True,
            created_by=self.user,
        )
        Task.objects.create(
            name="Alpha Task",
            function_name="hello_world",
            is_system_task=True,
            created_by=self.user,
        )

        # Act
        result = get_system_task_info()

        # Assert
        assert result["system_tasks"][0]["name"] == "Alpha Task"
        assert result["system_tasks"][1]["name"] == "Zebra Task"
