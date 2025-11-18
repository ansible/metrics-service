"""
Comprehensive unit tests for tasks utils module.
"""

import os
from unittest.mock import Mock, patch

from django.test import TestCase

from apps.tasks import utils
from apps.tasks.models import Task, TaskDependency, TaskExecution


class TaskUtilsTestCase(TestCase):
    """Test cases for task utility functions."""

    def setUp(self):
        """Set up test data."""
        self.user = self._create_test_user()
        self.task = Task.objects.create(
            name="Test Task", function_name="test_function", task_data={"param": "value"}, created_by=self.user
        )

    def _create_test_user(self):
        """Create a test user."""
        from apps.core.models import User

        return User.objects.create_user(username="testuser", email="test@example.com")

    @patch("django.setup")
    @patch("django.conf.settings")
    def test_ensure_django_setup_not_configured(self, mock_settings, mock_setup):
        """Test ensure_django_setup when Django is not configured."""
        mock_settings.configured = False

        with patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": ""}):
            utils.ensure_django_setup()

        mock_setup.assert_called_once()
        self.assertEqual(os.environ.get("DJANGO_SETTINGS_MODULE"), "metrics_service.settings.test")

    @patch("django.setup")
    @patch("django.conf.settings")
    def test_ensure_django_setup_already_configured(self, mock_settings, mock_setup):
        """Test ensure_django_setup when Django is already configured."""
        mock_settings.configured = True

        utils.ensure_django_setup()

        mock_setup.assert_not_called()

    @patch("apps.tasks.utils.log_task_execution")
    @patch("apps.tasks.utils.ensure_django_setup")
    def test_task_execution_wrapper_success(self, mock_ensure, mock_log):
        """Test task execution wrapper with successful task."""

        @utils.task_execution_wrapper("test_task")
        def test_function(**kwargs):
            return {"status": "success", "data": kwargs}

        result = test_function(param1="value1", param2="value2")

        mock_ensure.assert_called_once()
        self.assertEqual(mock_log.call_count, 2)  # start and complete
        mock_log.assert_any_call("test_task", "start", "Starting test_task task")
        mock_log.assert_any_call("test_task", "complete", "Task test_task completed successfully")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["param1"], "value1")

    @patch("apps.tasks.utils.log_task_execution")
    @patch("apps.tasks.utils.ensure_django_setup")
    @patch("apps.tasks.utils.create_task_result")
    def test_task_execution_wrapper_error(self, mock_create_result, mock_ensure, mock_log):
        """Test task execution wrapper with task error."""
        mock_create_result.return_value = {"status": "error", "error": "Test error"}

        @utils.task_execution_wrapper("test_task")
        def test_function(**kwargs):
            raise ValueError("Test error")

        result = test_function(param1="value1")

        mock_ensure.assert_called_once()
        self.assertEqual(mock_log.call_count, 2)  # start and error
        mock_log.assert_any_call("test_task", "start", "Starting test_task task")
        mock_log.assert_any_call("test_task", "error", "Test_Task task failed: Test error", level="error")

        mock_create_result.assert_called_once_with("error", error="Test_Task task failed: Test error")
        self.assertEqual(result["status"], "error")

    def test_get_task_and_execution_with_execution(self):
        """Test getting task and execution with execution ID."""
        execution = TaskExecution.objects.create(task=self.task, status="pending", worker_id="test-worker")

        task, exec_result = utils.get_task_and_execution(self.task.id, execution.id)

        self.assertEqual(task.id, self.task.id)
        self.assertEqual(exec_result.id, execution.id)

    def test_get_task_and_execution_without_execution(self):
        """Test getting task without execution ID."""
        task, exec_result = utils.get_task_and_execution(self.task.id, None)

        self.assertEqual(task.id, self.task.id)
        self.assertIsNone(exec_result)

    def test_trigger_dependent_tasks_task_not_found(self):
        """Test triggering dependent tasks when dependent task is deleted."""
        dependent_task = Task.objects.create(
            name="Dependent Task", function_name="dependent_function", task_data={}, created_by=self.user
        )

        TaskDependency.objects.create(
            dependent_task=dependent_task, prerequisite_task=self.task, required_status="completed"
        )

        self.task.status = "completed"
        self.task.save()

        # Delete the dependent task to simulate not found
        dependent_task.delete()

        # Should not raise exception
        utils.trigger_dependent_tasks(self.task)

    def test_schedule_next_occurrence_success(self):
        """Test scheduling next occurrence of recurring task."""
        self.task.cron_expression = "0 0 * * *"
        self.task.is_recurring = True
        self.task.save()

        initial_count = Task.objects.count()
        utils.schedule_next_occurrence(self.task)

        # Should create a new task
        self.assertEqual(Task.objects.count(), initial_count + 1)

        new_task = Task.objects.exclude(id=self.task.id).first()
        self.assertTrue(new_task.name.startswith("Test Task (recurring)"))
        self.assertEqual(new_task.function_name, self.task.function_name)
        self.assertEqual(new_task.cron_expression, self.task.cron_expression)
        self.assertTrue(new_task.is_recurring)

    def test_schedule_next_occurrence_no_cron(self):
        """Test scheduling next occurrence without cron expression."""
        self.task.cron_expression = ""
        self.task.is_recurring = True
        self.task.save()

        initial_count = Task.objects.count()
        utils.schedule_next_occurrence(self.task)

        # Should not create a new task
        self.assertEqual(Task.objects.count(), initial_count)

    @patch("apps.tasks.utils.trigger_dependent_tasks")
    def test_handle_post_execution_completed(self, mock_trigger):
        """Test post-execution handling for completed task."""
        self.task.status = "completed"

        utils.handle_post_execution(self.task)

        mock_trigger.assert_called_once_with(self.task)

    @patch("apps.tasks.utils.schedule_next_occurrence")
    @patch("apps.tasks.utils.trigger_dependent_tasks")
    def test_handle_post_execution_recurring_no_cron(self, mock_trigger, mock_schedule):
        """Test post-execution handling for recurring task without cron."""
        self.task.status = "completed"
        self.task.is_recurring = True
        self.task.cron_expression = ""

        utils.handle_post_execution(self.task)

        mock_trigger.assert_called_once_with(self.task)
        mock_schedule.assert_called_once_with(self.task)

    @patch("apps.tasks.utils.schedule_next_occurrence")
    @patch("apps.tasks.utils.trigger_dependent_tasks")
    def test_handle_post_execution_recurring_with_cron(self, mock_trigger, mock_schedule):
        """Test post-execution handling for recurring task with cron."""
        self.task.status = "completed"
        self.task.is_recurring = True
        self.task.cron_expression = "0 0 * * *"

        utils.handle_post_execution(self.task)

        mock_trigger.assert_called_once_with(self.task)
        mock_schedule.assert_not_called()  # Should not schedule when cron is present

    def test_handle_task_error_with_instances(self):
        """Test error handling with task and execution instances."""
        execution = TaskExecution.objects.create(task=self.task, status="running", worker_id="test-worker")

        result = utils.handle_task_error(
            task_instance=self.task, execution_instance=execution, error_message="Test error"
        )

        self.task.refresh_from_db()
        execution.refresh_from_db()

        self.assertEqual(self.task.status, "failed")
        self.assertEqual(self.task.error_message, "Test error")
        self.assertIsNotNone(self.task.completed_at)

        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.error_message, "Test error")
        self.assertIsNotNone(execution.completed_at)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Test error")

    def test_handle_task_error_with_exception(self):
        """Test error handling with exception."""
        utils.handle_task_error(task_instance=self.task, exception=ValueError("Test exception"))

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "failed")
        self.assertIn("Test exception", self.task.error_message)

    def test_handle_task_error_with_ids(self):
        """Test error handling with task and execution IDs."""
        execution = TaskExecution.objects.create(task=self.task, status="running", worker_id="test-worker")

        utils.handle_task_error(task_id=self.task.id, execution_id=execution.id, error_message="Test error")

        self.task.refresh_from_db()
        execution.refresh_from_db()

        self.assertEqual(self.task.status, "failed")
        self.assertEqual(execution.status, "failed")

    def test_handle_task_error_invalid_ids(self):
        """Test error handling with invalid IDs."""
        result = utils.handle_task_error(task_id=99999, execution_id=99999, error_message="Test error")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Test error")

    def test_update_task_status_completed(self):
        """Test updating task status to completed."""
        execution = TaskExecution.objects.create(task=self.task, status="running", worker_id="test-worker")

        result_data = {"result": "success"}
        utils.update_task_status(self.task, execution, "completed", result_data)

        self.task.refresh_from_db()
        execution.refresh_from_db()

        self.assertEqual(self.task.status, "completed")
        self.assertEqual(self.task.result_data, result_data)
        self.assertEqual(self.task.error_message, "")
        self.assertIsNotNone(self.task.completed_at)

        self.assertEqual(execution.status, "completed")
        self.assertEqual(execution.result_data, result_data)

    def test_update_task_status_running(self):
        """Test updating task status to running."""
        utils.update_task_status(self.task, None, "running")

        self.task.refresh_from_db()

        self.assertEqual(self.task.status, "running")
        self.assertIsNotNone(self.task.started_at)
        self.assertEqual(self.task.attempts, 1)

    def test_update_task_status_failed(self):
        """Test updating task status to failed."""
        utils.update_task_status(self.task, None, "failed", error_message="Test error")

        self.task.refresh_from_db()

        self.assertEqual(self.task.status, "failed")
        self.assertEqual(self.task.error_message, "Test error")
        self.assertIsNotNone(self.task.completed_at)

    @patch("os.getpid")
    def test_get_or_create_execution_record_default_worker(self, mock_getpid):
        """Test creating execution record with default worker ID."""
        mock_getpid.return_value = 12345

        execution = utils.get_or_create_execution_record(self.task)

        self.assertEqual(execution.task, self.task)
        self.assertEqual(execution.status, "pending")
        self.assertEqual(execution.worker_id, "worker-12345")

    def test_get_or_create_execution_record_custom_worker(self):
        """Test creating execution record with custom worker ID."""
        execution = utils.get_or_create_execution_record(self.task, "custom-worker")

        self.assertEqual(execution.task, self.task)
        self.assertEqual(execution.status, "pending")
        self.assertEqual(execution.worker_id, "custom-worker")

    def test_validate_task_data_valid(self):
        """Test validating valid task data."""
        data = {"field1": "value1", "field2": "value2"}
        required_fields = ["field1", "field2"]

        result = utils.validate_task_data(data, required_fields)

        self.assertIsNone(result)

    def test_validate_task_data_missing_fields(self):
        """Test validating task data with missing fields."""
        data = {"field1": "value1"}
        required_fields = ["field1", "field2", "field3"]

        result = utils.validate_task_data(data, required_fields)

        self.assertIn("Missing required fields: field2, field3", result)

    def test_validate_task_data_special_case_task_id(self):
        """Test validating task data with missing task_id (special case)."""
        data = {}
        required_fields = ["task_id"]

        result = utils.validate_task_data(data, required_fields)

        self.assertEqual(result, "No task_id provided")

    def test_validate_task_data_not_dict(self):
        """Test validating non-dictionary task data."""
        result = utils.validate_task_data("not a dict", ["field1"])

        self.assertEqual(result, "Task data must be a dictionary")

    def test_validate_task_data_no_required_fields(self):
        """Test validating task data with no required fields."""
        data = {"field1": "value1"}

        result = utils.validate_task_data(data)

        self.assertIsNone(result)

    def test_create_task_result_success(self):
        """Test creating successful task result."""
        data = {"key": "value"}
        result = utils.create_task_result("success", data)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["key"], "value")
        self.assertIn("timestamp", result)

    def test_create_task_result_error(self):
        """Test creating error task result."""
        result = utils.create_task_result("error", error="Test error")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Test error")
        self.assertIn("timestamp", result)

    def test_create_task_result_minimal(self):
        """Test creating minimal task result."""
        result = utils.create_task_result("pending")

        self.assertEqual(result["status"], "pending")
        self.assertIn("timestamp", result)
        self.assertNotIn("error", result)

    @patch("apps.tasks.utils.logger")
    def test_log_task_execution_info(self, mock_logger):
        """Test logging task execution with info level."""
        utils.log_task_execution("test_task", "start", "Starting task", "info")

        mock_logger.info.assert_called_once_with(
            "Task 'test_task' start: Starting task",
        )

    @patch("apps.tasks.utils.logger")
    def test_log_task_execution_error(self, mock_logger):
        """Test logging task execution with error level."""
        utils.log_task_execution("test_task", "error", "Task failed", "error")

        mock_logger.error.assert_called_once_with("Task 'test_task' error: Task failed")

    @patch("apps.tasks.utils.logger")
    def test_log_task_execution_no_details(self, mock_logger):
        """Test logging task execution without details."""
        utils.log_task_execution("test_task", "complete")

        mock_logger.info.assert_called_once_with("Task 'test_task' complete")

    def test_get_related_object_safely_success(self):
        """Test safely getting related object successfully."""
        # Create a mock object with a related field
        mock_instance = Mock()
        mock_instance.related_field = "related_value"

        result = utils.get_related_object_safely(mock_instance, "related_field")

        self.assertEqual(result, "related_value")

    def test_get_related_object_safely_attribute_error(self):
        """Test safely getting related object with AttributeError."""
        mock_instance = Mock()
        del mock_instance.related_field  # Simulate missing attribute

        result = utils.get_related_object_safely(mock_instance, "related_field", "default")

        self.assertEqual(result, "default")

    def test_get_related_object_safely_does_not_exist(self):
        """Test safely getting related object with DoesNotExist."""
        mock_instance = Mock()
        mock_instance.DoesNotExist = Exception  # Mock exception class

        # Make getattr raise DoesNotExist
        def mock_getattr(obj, attr):
            raise mock_instance.DoesNotExist()

        with patch("builtins.getattr", side_effect=mock_getattr):
            result = utils.get_related_object_safely(mock_instance, "related_field", "default")

        self.assertEqual(result, "default")

    def test_get_count_safely_success(self):
        """Test safely getting count successfully."""
        mock_queryset = Mock()
        mock_queryset.count.return_value = 5

        result = utils.get_count_safely(mock_queryset)

        self.assertEqual(result, 5)

    def test_get_count_safely_error(self):
        """Test safely getting count with error."""
        mock_queryset = Mock()
        mock_queryset.count.side_effect = Exception("Database error")

        with patch("apps.tasks.utils.logger") as mock_logger:
            result = utils.get_count_safely(mock_queryset)

        self.assertEqual(result, 0)
        mock_logger.warning.assert_called_once()

    def test_build_error_response_basic(self):
        """Test building basic error response."""
        result = utils.build_error_response("Test error")

        self.assertEqual(result["error"], "Test error")
        self.assertEqual(result["status_code"], 400)
        self.assertIn("timestamp", result)

    def test_build_error_response_with_details(self):
        """Test building error response with details."""
        details = {"field": "value"}
        result = utils.build_error_response("Test error", details, 500)

        self.assertEqual(result["error"], "Test error")
        self.assertEqual(result["status_code"], 500)
        self.assertEqual(result["details"], details)
        self.assertIn("timestamp", result)
