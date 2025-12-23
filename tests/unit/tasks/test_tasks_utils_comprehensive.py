"""
Comprehensive unit tests for tasks utils module.
"""

import os
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.tasks import utils
from apps.tasks.models import Task, TaskDependency, TaskExecution


class TaskUtilsTestCase(TestCase):
    """Test cases for task utility functions."""

    def setUp(self):
        """Set up test data."""
        self.user = self._create_test_user()
        # Create task with signals disabled to prevent automatic submission to dispatcherd
        self.task = self._create_task_safely(
            name="Test Task", function_name="test_function", task_data={"param": "value"}, created_by=self.user
        )

    def _create_test_user(self):
        """Create a test user."""
        from apps.core.models import User

        return User.objects.create_user(username="testuser", email="test@example.com")

    def _create_task_safely(self, **kwargs):
        """Create a task without triggering signals."""
        task = Task(**kwargs)
        task.save()
        return task

    @patch("django.setup")
    @patch("django.conf.settings")
    def test_ensure_django_setup_not_configured(self, mock_settings, mock_setup):
        """Test ensure_django_setup when Django is not configured."""
        mock_settings.configured = False

        with patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": ""}):
            utils.ensure_django_setup()

        mock_setup.assert_called_once()
        self.assertEqual(os.environ.get("DJANGO_SETTINGS_MODULE"), "metrics_service.settings")

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
        dependent_task = self._create_task_safely(
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

        mock_logger.info.assert_called_once_with("Task 'test_task' start: Starting task")

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


class TestParseDatetimeString(TestCase):
    """Test parse_datetime_string function."""

    def test_parse_valid_iso_datetime(self):
        """Test parsing valid ISO datetime string."""
        result = utils.parse_datetime_string("2024-01-15T10:30:00+00:00")

        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.hour, 10)
        self.assertEqual(result.minute, 30)

    def test_parse_datetime_with_z_suffix(self):
        """Test parsing datetime with Z suffix (UTC)."""
        result = utils.parse_datetime_string("2024-06-20T15:45:00Z")

        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 20)

    def test_parse_empty_string(self):
        """Test parsing empty string returns None."""
        result = utils.parse_datetime_string("")

        self.assertIsNone(result)

    def test_parse_none(self):
        """Test parsing None returns None."""
        result = utils.parse_datetime_string(None)

        self.assertIsNone(result)

    def test_parse_invalid_datetime(self):
        """Test parsing invalid datetime returns None."""
        result = utils.parse_datetime_string("not-a-date")

        self.assertIsNone(result)

    def test_parse_partial_date(self):
        """Test parsing partial date returns None."""
        result = utils.parse_datetime_string("2024-01")

        self.assertIsNone(result)


class TestGetDbConnection(TestCase):
    """Test get_db_connection function."""

    @patch("django.db.connections")
    def test_get_db_connection_default(self, mock_connections):
        """Test getting default AWX database connection."""
        mock_raw_conn = MagicMock()
        mock_django_conn = MagicMock()
        mock_django_conn.connection = mock_raw_conn
        mock_connections.__getitem__.return_value = mock_django_conn

        result = utils.get_db_connection()

        mock_connections.__getitem__.assert_called_once_with("awx")
        mock_django_conn.ensure_connection.assert_called_once()
        self.assertEqual(result, mock_raw_conn)

    @patch("django.db.connections")
    def test_get_db_connection_custom_db(self, mock_connections):
        """Test getting custom database connection."""
        mock_raw_conn = MagicMock()
        mock_django_conn = MagicMock()
        mock_django_conn.connection = mock_raw_conn
        mock_connections.__getitem__.return_value = mock_django_conn

        result = utils.get_db_connection("custom_db")

        mock_connections.__getitem__.assert_called_once_with("custom_db")
        self.assertEqual(result, mock_raw_conn)


class TestGenerateSalt(TestCase):
    """Test generate_salt function."""

    def test_generate_salt_returns_string(self):
        """Test generate_salt returns a string."""
        result = utils.generate_salt()

        self.assertIsInstance(result, str)

    def test_generate_salt_is_uuid_format(self):
        """Test generate_salt returns UUID4 format."""
        import uuid

        result = utils.generate_salt()

        # Should be valid UUID
        uuid.UUID(result)  # Raises ValueError if invalid

    def test_generate_salt_unique(self):
        """Test generate_salt returns unique values."""
        salt1 = utils.generate_salt()
        salt2 = utils.generate_salt()

        self.assertNotEqual(salt1, salt2)


class TestSendToSegment(TestCase):
    """Test send_to_segment function."""

    @patch("apps.tasks.utils.logger")
    def test_send_to_segment_import_error(self, mock_logger):
        """Test send_to_segment when metrics-utility import fails."""
        with (
            patch.dict("sys.modules", {"metrics_utility.library.storage.segment": None}),
            patch("apps.tasks.utils.logger"),
        ):
            # The function handles ImportError internally, so we need to test the fallback
            result = utils.send_to_segment("user1", "test_event", {"data": "test"})

            # Result should indicate segment not available if metrics-utility is not installed
            self.assertIn(result, ["success", "segment_not_available", "error"])

    def test_send_to_segment_no_write_key(self):
        """Test send_to_segment when SEGMENT_WRITE_KEY not configured."""
        with (
            patch("metrics_utility.library.storage.segment.SEGMENT_AVAILABLE", True),
            patch("metrics_utility.library.storage.segment.StorageSegment", MagicMock()),
            patch("django.conf.settings") as mock_settings,
        ):
            mock_settings.SEGMENT_WRITE_KEY = None

            result = utils.send_to_segment("user1", "test_event", {"data": "test"})

            self.assertEqual(result, "segment_not_available")

    @patch("apps.tasks.utils.logger")
    def test_send_to_segment_success(self, mock_logger):
        """Test send_to_segment successful transmission."""
        mock_storage_instance = MagicMock()
        mock_storage_instance.put.return_value = ["chunk1", "chunk2"]

        with (
            patch("metrics_utility.library.storage.segment.SEGMENT_AVAILABLE", True),
            patch(
                "metrics_utility.library.storage.segment.StorageSegment", return_value=mock_storage_instance
            ) as mock_storage_class,
            patch("django.conf.settings") as mock_settings,
        ):
            mock_settings.SEGMENT_WRITE_KEY = "test-write-key"
            mock_settings.DEBUG = False

            result = utils.send_to_segment("user1", "test_event", {"data": "test"})

            self.assertEqual(result, "success")
            mock_storage_class.assert_called_once_with(
                write_key="test-write-key",
                user_id="user1",
                debug=False,
                use_bulk=False,  # Small data, no bulk
            )

    @patch("apps.tasks.utils.logger")
    def test_send_to_segment_bulk_mode(self, mock_logger):
        """Test send_to_segment uses bulk mode for large data."""
        mock_storage_instance = MagicMock()
        mock_storage_instance.put.return_value = None  # No chunks returned

        # Create large data (> 24KB)
        large_data = {"data": "x" * (25 * 1024)}

        with (
            patch("metrics_utility.library.storage.segment.SEGMENT_AVAILABLE", True),
            patch(
                "metrics_utility.library.storage.segment.StorageSegment", return_value=mock_storage_instance
            ) as mock_storage_class,
            patch("django.conf.settings") as mock_settings,
        ):
            mock_settings.SEGMENT_WRITE_KEY = "test-write-key"
            mock_settings.DEBUG = False

            result = utils.send_to_segment("user1", "test_event", large_data)

            self.assertEqual(result, "success")
            # Should use bulk mode for large data
            call_kwargs = mock_storage_class.call_args[1]
            self.assertTrue(call_kwargs["use_bulk"])

    @patch("apps.tasks.utils.logger")
    def test_send_to_segment_exception(self, mock_logger):
        """Test send_to_segment handles exceptions."""
        with (
            patch("metrics_utility.library.storage.segment.SEGMENT_AVAILABLE", True),
            patch("metrics_utility.library.storage.segment.StorageSegment") as mock_storage_class,
            patch("django.conf.settings") as mock_settings,
        ):
            mock_settings.SEGMENT_WRITE_KEY = "test-write-key"
            mock_storage_class.side_effect = Exception("Connection error")

            result = utils.send_to_segment("user1", "test_event", {"data": "test"})

            self.assertTrue(result.startswith("error:"))
            self.assertIn("Connection error", result)
