"""
Comprehensive tests for task system functionality.

This module tests the complete task system including task functions, registry,
system task creation, execution, and helper functions.

Organized into clear test classes:
- TestSystemTaskFunctions: Individual task functions (cleanup_old_data, etc.)
- TestExecuteDbTask: Database task execution and error handling
- TestTaskRegistry: TASK_FUNCTIONS and TASK_METADATA configuration
- TestSystemTaskCreation: System task initialization and management
- TestSystemTaskHelpers: Internal helper functions
- TestTaskDispatcher: Task submission and dispatcher integration
- TestEdgeCasesAndErrorHandling: Edge cases, error conditions, and resilience
"""

from unittest.mock import ANY, MagicMock, Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tasks import tasks, tasks_system
from apps.tasks.models import Task, TaskExecution
from apps.tasks.tasks import (
    TASK_FUNCTIONS,
    cleanup_old_data,
    execute_db_task,
    submit_task_to_dispatcher,
)
from tests.test_utils import get_test_password

User = get_user_model()


# =============================================================================
# System Task Functions Tests
# =============================================================================


@pytest.mark.unit
class TestSystemTaskFunctions(TestCase):
    """Test individual system task functions."""

    def test_cleanup_old_data_success(self):
        """Test cleanup_old_data function with valid parameters."""
        result = cleanup_old_data(days_old=30)

        assert result["status"] == "success"
        assert result["days_old"] == 30
        assert "cleaned_count" in result

    def test_cleanup_old_data_with_exception(self):
        """Test cleanup_old_data handles exceptions gracefully."""
        with patch("apps.tasks.tasks.logger"):
            # Test with invalid data
            result = cleanup_old_data(days_old="invalid")

            # Should still return success (handles exception internally)
            assert result["status"] == "success"

    def test_cleanup_old_data_with_none_values(self):
        """Test cleanup_old_data with None values."""
        result = cleanup_old_data(days_old=None)
        assert result["status"] == "success"

    def test_cleanup_old_data_with_invalid_params(self):
        """Test cleanup_old_data with unexpected parameters."""
        result = cleanup_old_data(invalid_param="value")
        # Should handle gracefully without crashing
        assert isinstance(result, dict)


# =============================================================================
# Execute DB Task Tests
# =============================================================================


@pytest.mark.unit
class TestExecuteDbTask(TestCase):
    """Test execute_db_task function and database task execution."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="taskuser")
        self.task = self._create_task_safely(
            name="Test Task", function_name="cleanup_old_data", task_data={"days_old": 7}
        )

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
    def test_execute_db_task_with_execution_record(self):
        """Test task execution with TaskExecution record."""
        execution = TaskExecution.objects.create(task=self.task, status="pending")

        result = execute_db_task(task_id=self.task.id, execution_id=execution.id)

        assert result["status"] == "success"

        # Check execution record was updated
        execution.refresh_from_db()
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
        assert "Task execution failed: Task matching query does not exist" in result["error"]

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
            "cleanup_old_data",
            "execute_db_task",
            "hello_world",
            "collect_single_collector",
            "collect_metrics",
        ]

        for func_name in expected_functions:
            assert func_name in TASK_FUNCTIONS, f"{func_name} not in TASK_FUNCTIONS"
            assert callable(TASK_FUNCTIONS[func_name]), f"{func_name} is not callable"

    def test_task_function_signatures(self):
        """Test task functions accept keyword arguments and return dicts."""
        for _func_name, func in TASK_FUNCTIONS.items():
            try:
                result = func()
                assert isinstance(result, dict), f"{func.__name__} didn't return a dict"
                assert "status" in result, f"{func.__name__} result missing 'status' key"
            except Exception as e:
                pytest.fail(f"Function {func.__name__} raised exception: {e}")

    def test_metrics_utility_available_flag(self):
        """Test that METRICS_UTILITY_AVAILABLE flag is properly set."""
        assert hasattr(tasks, "METRICS_UTILITY_AVAILABLE")
        assert isinstance(tasks.METRICS_UTILITY_AVAILABLE, bool)

    @patch("apps.tasks.tasks_collector.logger")
    def test_metrics_utility_import_error_handling(self, mock_logger):
        """Test handling of metrics utility import errors."""
        # Should not have warnings in successful import
        mock_logger.warning.assert_not_called()


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
        # Disabled tasks are filtered by get_all_enabled_tasks()
        with patch("apps.tasks.task_groups.get_all_enabled_tasks", return_value={}):
            result = tasks_system.create_system_tasks()

            # All tasks filtered out
            assert result["created"] == 0
            assert result["removed"] == 0


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
        self.task = Task(name="Submit Task", function_name="cleanup_old_data", created_by=self.user)
        self.task.save()

    @patch("apps.tasks.models.TaskExecution.objects.create")
    def test_submit_task_to_dispatcher_handles_exception(self, mock_create):
        """Test submit_task_to_dispatcher handles exceptions gracefully."""
        mock_create.side_effect = Exception("Database error")

        submit_task_to_dispatcher(self.task)

        # Task should be marked as failed
        self.task.refresh_from_db()
        assert self.task.status == "failed"
        assert "Failed to submit to dispatcher" in self.task.error_message

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

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.anonymized_rollups_processor")
    @patch("apps.tasks.tasks_collector.csv_to_json")
    @patch("django.db.connections")
    def test_metrics_collection_with_django_connections(self, mock_connections, mock_csv_to_json, mock_collector):
        """Test metrics collection works with Django database connections."""
        # Setup mock database connection with .connection attribute
        mock_raw_connection = object()
        mock_db_connection = MagicMock()
        mock_db_connection.connection = mock_raw_connection
        mock_connections.__getitem__.return_value = mock_db_connection

        # Setup mock collector return value
        mock_collector.return_value = {"anonymized": "data"}

        # Call collector
        result = tasks.collect_single_collector(collector_type="anonymized_rollups")

        # Verify success
        assert result["status"] == "success"
        assert result["collector_type"] == "anonymized_rollups"

        # Verify Django connections were used
        mock_connections.__getitem__.assert_called_once_with("awx")
        mock_collector.assert_called_once_with(
            db=mock_raw_connection, salt=ANY, since=ANY, until=ANY, ship_path=None, save_rollups=False
        )

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.anonymized_rollups_processor")
    @patch("apps.tasks.tasks_collector.csv_to_json")
    @patch("django.db.connections")
    def test_metrics_collection_error_handling(self, mock_connections, mock_csv_to_json, mock_collector):
        """Test that metrics collection errors are handled gracefully."""
        # Setup mocks
        mock_raw_connection = object()
        mock_db_connection = MagicMock()
        mock_db_connection.connection = mock_raw_connection
        mock_connections.__getitem__.return_value = mock_db_connection

        # Make collector raise error
        mock_collector.side_effect = Exception("Test error")

        # Call should handle error gracefully
        result = tasks.collect_single_collector(collector_type="anonymized_rollups")
        assert result["status"] == "error"


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
            function_name="cleanup_old_data",
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
            function_name="cleanup_old_data",
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
            function_name="cleanup_old_data",
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
            function_name="cleanup_old_data",
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
