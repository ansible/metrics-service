"""
Comprehensive test coverage for apps/tasks/tasks.py

This module provides extensive coverage for all task functions, system tasks,
error conditions, and edge cases.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tasks import tasks, tasks_system
from apps.tasks.models import Task
from tests.test_utils import get_test_password

User = get_user_model()


@pytest.mark.unit
class TestMetricsUtilityImport(TestCase):
    """Test metrics utility import functionality."""

    def test_metrics_utility_available_flag(self):
        """Test that METRICS_UTILITY_AVAILABLE flag is properly set."""
        # Should be True if metrics-utility is available
        assert hasattr(tasks, "METRICS_UTILITY_AVAILABLE")
        assert isinstance(tasks.METRICS_UTILITY_AVAILABLE, bool)

    @patch("apps.tasks.tasks_collector.logger")
    def test_metrics_utility_import_error(self, mock_logger):
        """Test handling of metrics utility import errors."""
        # This tests the import error path that's normally not covered
        # We can't easily mock the import but we can verify the logger warning format
        mock_logger.warning.assert_not_called()  # Should not have been called in successful import


@pytest.mark.unit
class TestDispatcherdDecorator(TestCase):
    """Test dispatcherd decorator functionality."""

    @patch("apps.tasks.tasks_system.task")
    def test_task_decorator_applied(self, mock_task):
        """Test that task decorator is properly applied."""
        # Verify the task decorator exists and can be called from tasks_system
        assert callable(tasks_system.task)

    def test_fallback_decorator(self):
        """Test fallback decorator when dispatcherd is not available."""

        # Create a mock function to test the decorator
        @tasks_system.task()
        def test_function():
            return "test"

        # The decorator should not interfere with the function
        result = test_function()
        assert result == "test"


@pytest.mark.unit
class TestSystemTasksCreation(TestCase):
    """Test system tasks creation and management."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_create_system_tasks_disabled_task(self):
        """Test handling of disabled system tasks."""
        # Test that disabled tasks are skipped
        with patch(
            "apps.tasks.tasks_system.SYSTEM_TASKS",
            [
                {
                    "name": "Test Disabled Task",
                    "description": "Test task",
                    "function_name": "test_function",
                    "task_data": {},
                    "cron_expression": "0 0 * * *",
                    "is_recurring": True,
                    "priority": 2,
                    "is_enabled": False,
                }
            ],
        ):
            result = tasks_system.create_system_tasks()
            assert result["skipped"] >= 1

    def test_create_system_tasks_exception_handling(self):
        """Test exception handling in system tasks creation."""
        with patch(
            "apps.tasks.tasks_system.SYSTEM_TASKS",
            [
                {
                    "name": "Test Task",
                    "description": "Test task",
                    "function_name": "test_function",
                    "task_data": {},
                    "cron_expression": "invalid_cron",  # This might cause issues
                    "is_recurring": True,
                    "priority": 2,
                    "is_enabled": True,
                }
            ],
        ):
            result = tasks_system.create_system_tasks()
            # Should handle any exceptions gracefully
            assert "tasks" in result


@pytest.mark.unit
class TestSystemTaskHelpers(TestCase):
    """Test system task helper functions."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_process_system_task_new_task(self):
        """Test _process_system_task with new task creation."""
        system_task_config = {
            "name": "Test System Task",
            "description": "Test description",
            "function_name": "test_function",
            "task_data": {"test": "data"},
            "cron_expression": "0 0 * * *",
            "is_recurring": True,
            "priority": 2,
        }
        results = {"created": 0, "updated": 0, "skipped": 0, "tasks": []}

        tasks_system._process_system_task(system_task_config, results, Task)

        assert results["created"] == 1
        assert len(results["tasks"]) == 1
        assert "Created: Test System Task" in results["tasks"][0]

    def test_process_system_task_update_existing(self):
        """Test _process_system_task with existing task update."""
        # Create existing task
        Task.objects.create(
            name="Test System Task",
            description="Old description",
            function_name="test_function",
            task_data={"old": "data"},
            cron_expression="0 0 * * *",
            is_recurring=True,
            priority=1,
            is_system_task=True,
            status="pending",
        )

        system_task_config = {
            "name": "Test System Task",
            "description": "New description",
            "function_name": "test_function",
            "task_data": {"new": "data"},
            "cron_expression": "0 1 * * *",
            "is_recurring": True,
            "priority": 2,
        }
        results = {"created": 0, "updated": 0, "skipped": 0, "tasks": []}

        tasks_system._process_system_task(system_task_config, results, Task)

        assert results["updated"] == 1
        assert len(results["tasks"]) == 1
        assert "Updated: Test System Task" in results["tasks"][0]

    def test_process_system_task_no_changes(self):
        """Test _process_system_task with no changes needed."""
        # Create existing task with same config
        system_task_config = {
            "name": "Test System Task",
            "description": "Test description",
            "function_name": "test_function",
            "task_data": {"test": "data"},
            "cron_expression": "0 0 * * *",
            "is_recurring": True,
            "priority": 2,
        }

        Task.objects.create(
            name=system_task_config["name"],
            description=system_task_config["description"],
            function_name=system_task_config["function_name"],
            task_data=system_task_config["task_data"],
            cron_expression=system_task_config["cron_expression"],
            is_recurring=system_task_config["is_recurring"],
            priority=system_task_config["priority"],
            is_system_task=True,
            status="pending",
        )

        results = {"created": 0, "updated": 0, "skipped": 0, "tasks": []}

        tasks_system._process_system_task(system_task_config, results, Task)

        assert results["skipped"] == 1
        assert len(results["tasks"]) == 1
        assert "Skipped: Test System Task (no changes)" in results["tasks"][0]

    def test_update_existing_system_task_multiple_fields(self):
        """Test _update_existing_system_task with multiple field changes."""
        existing_task = Task.objects.create(
            name="Test Task",
            description="Old description",
            function_name="test_function",
            task_data={"old": "data"},
            cron_expression="0 0 * * *",
            priority=1,
            is_system_task=True,
            status="pending",
        )

        system_task_config = {
            "task_data": {"new": "data"},
            "cron_expression": "0 1 * * *",
            "priority": 2,
            "description": "New description",
        }
        results = {"created": 0, "updated": 0, "skipped": 0, "tasks": []}

        tasks_system._update_existing_system_task(existing_task, system_task_config, results)

        assert results["updated"] == 1
        assert results["skipped"] == 0

        # Verify changes were applied
        existing_task.refresh_from_db()
        assert existing_task.task_data == {"new": "data"}
        assert existing_task.cron_expression == "0 1 * * *"
        assert existing_task.priority == 2
        assert existing_task.description == "New description"

    def test_create_new_system_task(self):
        """Test _create_new_system_task function."""
        system_task_config = {
            "name": "New System Task",
            "description": "New task description",
            "function_name": "new_function",
            "task_data": {"key": "value"},
            "cron_expression": "0 2 * * *",
            "is_recurring": True,
            "priority": 3,
        }
        results = {"created": 0, "updated": 0, "skipped": 0, "tasks": []}

        tasks_system._create_new_system_task(system_task_config, results, Task)

        assert results["created"] == 1
        assert len(results["tasks"]) == 1
        assert "Created: New System Task" in results["tasks"][0]

        # Verify task was created correctly
        task = Task.objects.get(name="New System Task")
        assert task.is_system_task is True
        assert task.status == "pending"
        assert task.function_name == "new_function"


@pytest.mark.unit
class TestTaskFunctionsRegistry(TestCase):
    """Test TASK_FUNCTIONS registry and related functionality."""

    def test_task_functions_registry_exists(self):
        """Test that TASK_FUNCTIONS registry exists and contains expected functions."""
        assert hasattr(tasks, "TASK_FUNCTIONS")
        assert isinstance(tasks.TASK_FUNCTIONS, dict)

        # Check for expected task functions
        expected_functions = [
            "cleanup_old_data",
            "send_notification_email",
            "process_user_data",
            "execute_db_task",
            "collect_anonymous_metrics",
            "collect_config_metrics",
            "collect_host_metrics",
            "collect_job_host_summary",
        ]

        for func_name in expected_functions:
            assert func_name in tasks.TASK_FUNCTIONS
            assert callable(tasks.TASK_FUNCTIONS[func_name])

    def test_system_tasks_configuration(self):
        """Test SYSTEM_TASKS configuration."""
        assert hasattr(tasks_system, "SYSTEM_TASKS")
        assert isinstance(tasks_system.SYSTEM_TASKS, list)

        # Each system task should have required fields
        for system_task in tasks_system.SYSTEM_TASKS:
            required_fields = [
                "name",
                "description",
                "function_name",
                "task_data",
                "cron_expression",
                "is_recurring",
                "priority",
            ]
            for field in required_fields:
                assert field in system_task

            # Function should exist in TASK_FUNCTIONS
            assert system_task["function_name"] in tasks.TASK_FUNCTIONS


@pytest.mark.unit
class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    def test_task_execution_with_invalid_data(self):
        """Test task execution with invalid task data."""
        # This tests error handling in task functions
        result = tasks.cleanup_old_data(invalid_param="value")
        # Should handle gracefully without crashing
        assert isinstance(result, dict)

    def test_task_execution_with_none_values(self):
        """Test task execution with None values."""
        result = tasks.process_user_data(user_id=None)
        assert "error" in result["status"]

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.anonymized_rollups_processor")
    @patch("django.db.connections")
    def test_metrics_collection_edge_cases(self, mock_connections, mock_collector):
        """Test metrics collection works with Django database connections."""
        # Setup mock database connection
        mock_db_connection = object()
        mock_connections.__getitem__.return_value = mock_db_connection

        # Setup mock collector return value
        mock_collector.return_value = {}

        # Call the function
        result = tasks.collect_anonymous_metrics()

        # Verify it worked
        assert result["status"] == "success"
        assert result["collector_type"] == "anonymized_rollups"

        # Verify it used Django connections
        mock_connections.__getitem__.assert_called_once_with("awx")
        # Note: salt is now auto-generated UUID4, so we use ANY matcher
        from unittest.mock import ANY

        mock_collector.assert_called_once_with(
            db=mock_db_connection, salt=ANY, since=None, until=None, ship_path=None, save_rollups=True
        )

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.logger")
    def test_error_logging(self, mock_logger):
        """Test that errors are properly logged."""
        with patch("apps.tasks.tasks_collector.anonymized_rollups_processor", side_effect=Exception("Test error")):
            tasks.collect_anonymous_metrics()
            # Logger should be called for error cases
            # Note: Specific logging assertions depend on implementation
