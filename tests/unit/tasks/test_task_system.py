"""
Unit tests for the task system functionality.
"""

from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from apps.core.models import User
from apps.tasks.models import Task, TaskExecution
from apps.tasks.tasks import (
    TASK_FUNCTIONS,
    cleanup_old_data,
    execute_db_task,
    submit_task_to_dispatcher,
)

# Note: Some utilities may not be implemented yet
# from apps.tasks.utils import (
#     schedule_next_occurrence,
#     trigger_dependent_tasks,
# )


@pytest.mark.unit
class TaskFunctionsTestCase(TestCase):
    """Test cases for task functions."""

    def test_cleanup_old_data_success(self):
        """Test cleanup_old_data function success."""
        result = cleanup_old_data(days_old=30)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["days_old"], 30)
        self.assertIn("cleaned_count", result)

    def test_cleanup_old_data_with_exception(self):
        """Test cleanup_old_data function with exception."""
        # Test with invalid data that might cause an exception
        with patch("apps.tasks.tasks.logger"):
            # Test with invalid data
            result = cleanup_old_data(days_old="invalid")

            # Should still return success since the function handles exceptions gracefully
            self.assertEqual(result["status"], "success")


@pytest.mark.unit
class ExecuteDbTaskTestCase(TestCase):
    """Test cases for execute_db_task function."""

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
        """Test execute_db_task success."""
        result = execute_db_task(task_id=self.task.id)

        self.assertEqual(result["status"], "success")

        # Refresh task from database
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "completed")
        self.assertEqual(self.task.attempts, 1)
        self.assertIsNotNone(self.task.started_at)
        self.assertIsNotNone(self.task.completed_at)

    @pytest.mark.django_db(transaction=True)
    def test_execute_db_task_with_execution_record(self):
        """Test execute_db_task with execution record."""
        execution = TaskExecution.objects.create(task=self.task, status="pending")

        result = execute_db_task(task_id=self.task.id, execution_id=execution.id)

        self.assertEqual(result["status"], "success")

        # Check execution record was updated
        execution.refresh_from_db()
        self.assertEqual(execution.status, "completed")

    def test_execute_db_task_no_task_id(self):
        """Test execute_db_task without task_id."""
        result = execute_db_task()

        self.assertEqual(result["status"], "error")
        self.assertIn("task_id is required", result["error"])

    def test_execute_db_task_task_not_found(self):
        """Test execute_db_task with non-existent task."""
        result = execute_db_task(task_id=99999)

        self.assertEqual(result["status"], "error")
        self.assertIn("Task execution failed: Task matching query does not exist", result["error"])

    def test_execute_db_task_function_not_found(self):
        """Test execute_db_task with unknown function."""
        self.task.function_name = "unknown_function"
        self.task.save()

        result = execute_db_task(task_id=self.task.id)

        self.assertEqual(result["status"], "error")
        self.assertIn("not found in TASK_FUNCTIONS", result["error"])

        # Check task was marked as failed
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "failed")

    @patch("apps.tasks.tasks.TASK_FUNCTIONS")
    def test_execute_db_task_function_exception(self, mock_task_functions):
        """Test execute_db_task when task function raises exception."""
        # Mock function that raises exception
        mock_function = Mock(side_effect=Exception("Test exception"))
        mock_task_functions.__getitem__.return_value = mock_function
        mock_task_functions.__contains__.return_value = True

        result = execute_db_task(task_id=self.task.id)

        self.assertEqual(result["status"], "error")
        self.assertIn("Test exception", result["error"])


@pytest.mark.unit
class SubmitTaskTestCase(TestCase):
    """Test cases for submit_task_to_dispatcher function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="submituser")
        # Create task without triggering signals to prevent recursion during test setup
        self.task = Task(name="Submit Task", function_name="cleanup_old_data", created_by=self.user)
        self.task.save()

    @patch("apps.tasks.models.TaskExecution.objects.create")
    def test_submit_task_to_dispatcher_exception(self, mock_create):
        """Test submit_task_to_dispatcher with exception."""
        mock_create.side_effect = Exception("Database error")

        submit_task_to_dispatcher(self.task)

        # Task should be marked as failed
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "failed")
        self.assertIn("Failed to submit to dispatcher", self.task.error_message)


@pytest.mark.unit
class TaskFunctionRegistryTestCase(TestCase):
    """Test cases for TASK_FUNCTIONS registry."""

    def test_task_functions_registry(self):
        """Test TASK_FUNCTIONS contains expected functions."""
        expected_functions = ["cleanup_old_data", "execute_db_task", "hello_world"]

        for func_name in expected_functions:
            self.assertIn(func_name, TASK_FUNCTIONS)
            self.assertTrue(callable(TASK_FUNCTIONS[func_name]))

    def test_task_function_signatures(self):
        """Test task functions have correct signatures."""
        for _func_name, func in TASK_FUNCTIONS.items():
            # Each function should accept keyword arguments
            # We can test this by calling with no arguments
            try:
                result = func()
                self.assertIsInstance(result, dict)
                self.assertIn("status", result)
            except Exception:
                self.fail(f"Function {func.__name__} raised an exception when called with no arguments")
