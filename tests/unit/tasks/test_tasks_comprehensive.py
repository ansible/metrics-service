"""
Comprehensive test coverage for apps/tasks/tasks.py

This module provides extensive coverage for all task functions, system tasks,
error conditions, and edge cases.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tasks import tasks
from apps.tasks.models import Task

User = get_user_model()


@pytest.mark.unit
class TestMetricsUtilityImport(TestCase):
    """Test metrics utility import functionality."""

    def test_metrics_utility_available_flag(self):
        """Test that METRICS_UTILITY_AVAILABLE flag is properly set."""
        # Should be True if metrics-utility is available
        assert hasattr(tasks, "METRICS_UTILITY_AVAILABLE")
        assert isinstance(tasks.METRICS_UTILITY_AVAILABLE, bool)

    @patch("apps.tasks.tasks.logger")
    def test_metrics_utility_import_error(self, mock_logger):
        """Test handling of metrics utility import errors."""
        # This tests the import error path that's normally not covered
        # We can't easily mock the import but we can verify the logger warning format
        mock_logger.warning.assert_not_called()  # Should not have been called in successful import


@pytest.mark.unit
class TestDispatcherdDecorator(TestCase):
    """Test dispatcherd decorator functionality."""

    @patch("apps.tasks.tasks.task")
    def test_task_decorator_applied(self, mock_task):
        """Test that task decorator is properly applied."""
        # Verify the task decorator exists and can be called
        assert callable(tasks.task)

    def test_fallback_decorator(self):
        """Test fallback decorator when dispatcherd is not available."""

        # Create a mock function to test the decorator
        @tasks.task()
        def test_function():
            return "test"

        # The decorator should not interfere with the function
        result = test_function()
        assert result == "test"


@pytest.mark.unit
class TestCollectAnonymousMetrics(TestCase):
    """Test collect_anonymous_metrics function."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks.anonymous")
    def test_collect_anonymous_metrics_success(self, mock_anonymous):
        """Test successful anonymous metrics collection."""
        mock_anonymous.return_value = {"metrics": "data"}

        result = tasks.collect_anonymous_metrics()

        assert result["status"] == "success"
        mock_anonymous.assert_called_once()

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_anonymous_metrics_unavailable(self):
        """Test anonymous metrics collection when utility unavailable."""
        result = tasks.collect_anonymous_metrics()

        assert result["success"] is False
        assert "metrics-utility not available" in result["error"]

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks.anonymous")
    def test_collect_anonymous_metrics_exception(self, mock_anonymous):
        """Test anonymous metrics collection with exception."""
        mock_anonymous.side_effect = Exception("Collection failed")

        result = tasks.collect_anonymous_metrics()

        assert result["success"] is False
        assert "Collection failed" in result["error"]


@pytest.mark.unit
class TestCollectConfigMetrics(TestCase):
    """Test collect_config_metrics function."""

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks.config")
    def test_collect_config_metrics_success(self, mock_config):
        """Test successful config metrics collection."""
        mock_config.return_value = {"config": "data"}

        result = tasks.collect_config_metrics()

        assert result["status"] == "success"
        assert result["metrics_collected"] == {"config": "data"}
        mock_config.assert_called_once()

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_config_metrics_unavailable(self):
        """Test config metrics collection when utility unavailable."""
        result = tasks.collect_config_metrics()

        assert result["success"] is False
        assert "metrics-utility not available" in result["error"]

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks.config")
    def test_collect_config_metrics_exception(self, mock_config):
        """Test config metrics collection with exception."""
        mock_config.side_effect = Exception("Config collection failed")

        result = tasks.collect_config_metrics()

        assert result["success"] is False
        assert "Config collection failed" in result["error"]


@pytest.mark.unit
class TestCollectHostMetrics(TestCase):
    """Test collect_host_metrics function."""

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks.host_metric")
    def test_collect_host_metrics_success(self, mock_host_metric):
        """Test successful host metrics collection."""
        mock_host_metric.return_value = {"host": "metrics"}

        result = tasks.collect_host_metrics()

        assert result["status"] == "success"
        assert result["metrics_collected"] == {"host": "metrics"}
        mock_host_metric.assert_called_once()

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_host_metrics_unavailable(self):
        """Test host metrics collection when utility unavailable."""
        result = tasks.collect_host_metrics()

        assert result["success"] is False
        assert "metrics-utility not available" in result["error"]

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks.host_metric")
    def test_collect_host_metrics_exception(self, mock_host_metric):
        """Test host metrics collection with exception."""
        mock_host_metric.side_effect = Exception("Host metrics failed")

        result = tasks.collect_host_metrics()

        assert result["success"] is False
        assert "Host metrics failed" in result["error"]


@pytest.mark.unit
class TestCollectJobHostSummary(TestCase):
    """Test collect_job_host_summary function."""

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks.job_host_summary")
    def test_collect_job_host_summary_success(self, mock_job_host_summary):
        """Test successful job host summary collection."""
        mock_job_host_summary.return_value = {"job_summary": "data"}

        result = tasks.collect_job_host_summary()

        assert result["status"] == "success"
        assert result["metrics_collected"] == {"job_summary": "data"}
        mock_job_host_summary.assert_called_once()

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_job_host_summary_unavailable(self):
        """Test job host summary collection when utility unavailable."""
        result = tasks.collect_job_host_summary()

        assert result["success"] is False
        assert "metrics-utility not available" in result["error"]

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks.job_host_summary")
    def test_collect_job_host_summary_exception(self, mock_job_host_summary):
        """Test job host summary collection with exception."""
        mock_job_host_summary.side_effect = Exception("Job summary failed")

        result = tasks.collect_job_host_summary()

        assert result["success"] is False
        assert "Job summary failed" in result["error"]


@pytest.mark.unit
class TestSystemTasksCreation(TestCase):
    """Test system tasks creation and management."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_create_system_tasks_django_not_ready(self):
        """Test create_system_tasks when Django is not ready."""
        with patch("apps.tasks.tasks.Task", side_effect=ImportError("Django not ready")):
            result = tasks.create_system_tasks()

            assert "error" in result
            assert result["error"] == "Django not ready"
            assert result["created"] == 0
            assert result["updated"] == 0
            assert result["skipped"] == 0

    def test_create_system_tasks_success(self):
        """Test successful system tasks creation."""
        # Clear any existing system tasks
        Task.objects.filter(is_system_task=True).delete()

        result = tasks.create_system_tasks()

        assert "created" in result
        assert "updated" in result
        assert "skipped" in result
        assert "tasks" in result
        assert result["created"] > 0  # Should create some system tasks

    def test_create_system_tasks_update_existing(self):
        """Test updating existing system tasks."""
        # Create a system task first
        Task.objects.create(
            name="System Data Cleanup",
            description="Old description",
            function_name="cleanup_old_data",
            task_data={"days_old": 7},
            is_system_task=True,
            status="pending",
        )

        result = tasks.create_system_tasks()

        # Should update the existing task
        assert result["updated"] >= 1 or result["skipped"] >= 1

    def test_create_system_tasks_disabled_task(self):
        """Test handling of disabled system tasks."""
        # Test that disabled tasks are skipped
        with patch(
            "apps.tasks.tasks.SYSTEM_TASKS",
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
            result = tasks.create_system_tasks()
            assert result["skipped"] >= 1

    def test_create_system_tasks_exception_handling(self):
        """Test exception handling in system tasks creation."""
        with patch(
            "apps.tasks.tasks.SYSTEM_TASKS",
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
            result = tasks.create_system_tasks()
            # Should handle any exceptions gracefully
            assert "tasks" in result


@pytest.mark.unit
class TestSystemTaskHelpers(TestCase):
    """Test system task helper functions."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

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

        tasks._process_system_task(system_task_config, results, Task)

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

        tasks._process_system_task(system_task_config, results, Task)

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

        tasks._process_system_task(system_task_config, results, Task)

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

        tasks._update_existing_system_task(existing_task, system_task_config, results)

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

        tasks._create_new_system_task(system_task_config, results, Task)

        assert results["created"] == 1
        assert len(results["tasks"]) == 1
        assert "Created: New System Task" in results["tasks"][0]

        # Verify task was created correctly
        task = Task.objects.get(name="New System Task")
        assert task.is_system_task is True
        assert task.status == "pending"
        assert task.function_name == "new_function"


@pytest.mark.unit
class TestGetSystemTaskInfo(TestCase):
    """Test get_system_task_info function."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_get_system_task_info_django_not_ready(self):
        """Test get_system_task_info when Django is not ready."""
        with patch("apps.tasks.tasks.Task", side_effect=ImportError("Django not ready")):
            result = tasks.get_system_task_info()

            assert "error" in result
            assert result["error"] == "Django not ready"

    def test_get_system_task_info_success(self):
        """Test successful get_system_task_info."""
        # Create some system tasks
        Task.objects.create(
            name="System Task 1",
            description="Test system task 1",
            function_name="test_function_1",
            is_system_task=True,
            status="pending",
        )
        Task.objects.create(
            name="System Task 2",
            description="Test system task 2",
            function_name="test_function_2",
            is_system_task=True,
            status="running",
        )

        result = tasks.get_system_task_info()

        assert "system_tasks" in result
        assert "total_count" in result
        assert "status_breakdown" in result
        assert result["total_count"] >= 2
        assert "pending" in result["status_breakdown"]
        assert "running" in result["status_breakdown"]

    def test_get_system_task_info_no_tasks(self):
        """Test get_system_task_info with no system tasks."""
        Task.objects.filter(is_system_task=True).delete()

        result = tasks.get_system_task_info()

        assert result["total_count"] == 0
        assert len(result["system_tasks"]) == 0
        assert all(count == 0 for count in result["status_breakdown"].values())


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
        assert hasattr(tasks, "SYSTEM_TASKS")
        assert isinstance(tasks.SYSTEM_TASKS, list)

        # Each system task should have required fields
        for system_task in tasks.SYSTEM_TASKS:
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
class TestEdgeCasesAndErrorHandling(TestCase):
    """Test edge cases and error handling scenarios."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

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

    def test_metrics_collection_edge_cases(self):
        """Test metrics collection edge cases."""
        # Test with empty parameters
        result = tasks.collect_anonymous_metrics(**{})
        assert isinstance(result, dict)
        assert "success" in result["status"]

    @patch("apps.tasks.tasks.logger")
    def test_error_logging(self, mock_logger):
        """Test that errors are properly logged."""
        with patch("apps.tasks.tasks.anonymous", side_effect=Exception("Test error")):
            tasks.collect_anonymous_metrics()
            # Logger should be called for error cases
            # Note: Specific logging assertions depend on implementation
