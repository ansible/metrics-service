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
    process_user_data,
    send_notification_email,
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

    def test_send_notification_email_success(self):
        """Test send_notification_email function success."""
        result = send_notification_email(recipient="test@example.com", subject="Test Subject", message="Test message")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["recipient"], "test@example.com")
        self.assertEqual(result["subject"], "Test Subject")

    def test_send_notification_email_default_subject(self):
        """Test send_notification_email with default subject."""
        result = send_notification_email(recipient="test@example.com")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["subject"], "Notification")

    def test_process_user_data_success(self):
        """Test process_user_data function success."""
        user = User.objects.create_user(username="testuser")

        result = process_user_data(user_id=user.id, operation="sync")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["user_id"], user.id)
        self.assertEqual(result["username"], "testuser")
        self.assertEqual(result["operation"], "sync")

    def test_process_user_data_validation_operation(self):
        """Test process_user_data with validation operation."""
        user = User.objects.create_user(username="testuser")

        result = process_user_data(user_id=user.id, operation="validate")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["operation"], "validate")

    def test_process_user_data_user_not_found(self):
        """Test process_user_data with non-existent user."""
        result = process_user_data(user_id=99999, operation="sync")

        self.assertEqual(result["status"], "error")
        self.assertIn("error", result)

    def test_process_user_data_default_operation(self):
        """Test process_user_data with default operation."""
        user = User.objects.create_user(username="testuser")

        result = process_user_data(user_id=user.id)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["operation"], "sync")


@pytest.mark.unit
class ExecuteDbTaskTestCase(TestCase):
    """Test cases for execute_db_task function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="taskuser")
        self.task = Task.objects.create(name="Test Task", function_name="cleanup_old_data", task_data={"days_old": 7})

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
        self.task._skip_signals = True
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


# NOTE: TaskSchedulerTestCase has been disabled because SimpleTaskScheduler
# has been replaced by UnifiedTaskScheduler in cron_scheduler.py
# See tests/unit/tasks/test_unified_scheduler.py for updated tests

# @pytest.mark.unit
# class TaskSchedulerTestCase(TestCase):
#     """Test cases for SimpleTaskScheduler class."""
#
#     def setUp(self):
#         """Set up test data."""
#         self.scheduler = SimpleTaskScheduler()
#         self.user = User.objects.create_user(username="scheduleuser")
#
#     def test_task_scheduler_init(self):
#         """Test SimpleTaskScheduler initialization."""
#         self.assertEqual(self.scheduler.check_interval, 30)
#         self.assertFalse(self.scheduler.running)
#
#     @patch.object(SimpleTaskScheduler, "_submit_task_to_dispatcherd")
#     def test_process_pending_tasks_not_ready(self, mock_submit):
#         """Test SimpleTaskScheduler with tasks not ready to run."""
#         # Create a task with future scheduled time
#         future_time = timezone.now() + timedelta(hours=1)
#         Task.objects.create(
#             name="Future Task",
#             function_name="cleanup_old_data",
#             status="pending",
#             scheduled_time=future_time,
#             created_by=self.user,
#         )
#
#         self.scheduler._check_and_submit_tasks()
#
#         mock_submit.assert_not_called()
#
#     def test_stop_method(self):
#         """Test SimpleTaskScheduler stop method."""
#         self.scheduler.running = True
#         self.scheduler.stop()
#         self.assertFalse(self.scheduler.running)


@pytest.mark.unit
class TaskFunctionRegistryTestCase(TestCase):
    """Test cases for TASK_FUNCTIONS registry."""

    def test_task_functions_registry(self):
        """Test TASK_FUNCTIONS contains expected functions."""
        expected_functions = ["cleanup_old_data", "send_notification_email", "process_user_data", "execute_db_task"]

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
