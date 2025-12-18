"""
Base test classes for task-related tests.

This module provides reusable test base classes that eliminate code duplication
across task test files. All task tests should inherit from these base classes
instead of directly from TestCase.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.tasks.models import Task, TaskExecution
from tests.test_utils import get_test_password

User = get_user_model()


class TaskTestBase(TestCase):
    """
    Base class for task tests with common utilities.

    This class provides:
    - Automatic test user creation
    - Task creation without triggering signals
    - Task execution creation utilities
    - Task status assertion helpers

    Example:
        >>> class MyTaskTest(TaskTestBase):
        ...     def test_my_task(self):
        ...         task = self.create_task(
        ...             name="Test Task",
        ...             function_name="cleanup_old_data"
        ...         )
        ...         self.assert_task_status(task, "pending")
    """

    def setUp(self):
        """Set up test environment with a test user."""
        super().setUp()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def create_task(self, **kwargs: Any) -> Task:
        """
        Create a task without triggering signals.

        This method replaces the duplicated _create_task_safely() method
        found in multiple test files. It creates a Task instance directly
        without triggering Django signals, which is useful for testing
        task behavior in isolation.

        Args:
            **kwargs: Task fields to set. Common fields include:
                - name (str): Task name
                - description (str): Task description
                - function_name (str): Name of the function to execute
                - task_data (dict): JSON data to pass to the task
                - status (str): Task status (default: "pending")
                - priority (int): Task priority (default: 2)
                - created_by (User): User who created the task (default: self.user)

        Returns:
            Task: The created task instance

        Examples:
            >>> task = self.create_task(name="Test", function_name="cleanup_old_data")
            >>> task = self.create_task(
            ...     name="Custom Task",
            ...     function_name="process_user_data",
            ...     task_data={"user_id": 123},
            ...     status="running",
            ...     priority=3
            ... )
        """
        # Set default values for common fields
        defaults = {
            "name": "Test Task",
            "function_name": "cleanup_old_data",
            "task_data": {},
            "status": "pending",
            "priority": 2,
        }

        # If created_by not specified, use the test user
        if "created_by" not in kwargs and hasattr(self, "user"):
            kwargs["created_by"] = self.user

        # Merge defaults with provided kwargs
        task_kwargs = {**defaults, **kwargs}

        # Create and save the task directly without triggering signals
        task = Task(**task_kwargs)
        task.save()
        return task

    def create_execution(self, task: Task | None = None, **kwargs: Any) -> TaskExecution:
        """
        Create a task execution for testing.

        Args:
            task (Task, optional): The task to create execution for.
                If not provided, creates a new task automatically.
            **kwargs: TaskExecution fields to set. Common fields include:
                - status (str): Execution status (default: "pending")
                - worker_id (str): ID of the worker executing the task
                - result_data (dict): JSON result data
                - error_message (str): Error message if execution failed

        Returns:
            TaskExecution: The created execution instance

        Examples:
            >>> execution = self.create_execution()  # Creates with new task
            >>> task = self.create_task(name="My Task")
            >>> execution = self.create_execution(
            ...     task=task,
            ...     status="completed",
            ...     result_data={"result": "success"}
            ... )
        """
        # Create a task if not provided
        if task is None:
            task = self.create_task()

        # Set default values
        defaults = {"task": task, "status": "pending", "started_at": timezone.now()}

        # Merge defaults with provided kwargs
        execution_kwargs = {**defaults, **kwargs}

        # Create and save the execution
        execution = TaskExecution(**execution_kwargs)
        execution.save()
        return execution

    def assert_task_status(self, task: Task, expected_status: str) -> None:
        """
        Assert that a task has the expected status.

        This is a convenience method that refreshes the task from the database
        and asserts its status, providing a clear error message if the assertion fails.

        Args:
            task (Task): The task to check
            expected_status (str): The expected status value

        Raises:
            AssertionError: If the task status doesn't match expected_status

        Examples:
            >>> task = self.create_task()
            >>> self.assert_task_status(task, "pending")
            >>> task.status = "running"
            >>> task.save()
            >>> self.assert_task_status(task, "running")
        """
        # Refresh from database to get latest status
        task.refresh_from_db()
        self.assertEqual(
            task.status,
            expected_status,
            f"Task {task.id} ({task.name}) status is '{task.status}', expected '{expected_status}'",
        )

    def assert_task_completed_successfully(self, task: Task) -> None:
        """
        Assert that a task completed successfully.

        Checks that:
        - Task status is "completed"
        - No error message is set
        - completed_at timestamp is set

        Args:
            task (Task): The task to check

        Raises:
            AssertionError: If the task didn't complete successfully

        Examples:
            >>> task = self.create_task(status="completed")
            >>> self.assert_task_completed_successfully(task)
        """
        task.refresh_from_db()
        self.assertEqual(task.status, "completed", f"Task {task.id} should be completed but is {task.status}")
        self.assertEqual(task.error_message, "", f"Task {task.id} should have no error message")
        self.assertIsNotNone(task.completed_at, f"Task {task.id} should have completed_at timestamp")

    def assert_task_failed_with_error(self, task: Task, expected_error_substring: str | None = None) -> None:
        """
        Assert that a task failed with an error.

        Checks that:
        - Task status is "failed"
        - An error message is set
        - Optionally, the error message contains expected text

        Args:
            task (Task): The task to check
            expected_error_substring (str, optional): If provided, checks that the
                error message contains this substring

        Raises:
            AssertionError: If the task didn't fail as expected

        Examples:
            >>> task = self.create_task(status="failed", error_message="Connection timeout")
            >>> self.assert_task_failed_with_error(task)
            >>> self.assert_task_failed_with_error(task, "timeout")
        """
        task.refresh_from_db()
        self.assertEqual(task.status, "failed", f"Task {task.id} should be failed but is {task.status}")
        self.assertNotEqual(task.error_message, "", f"Task {task.id} should have an error message")

        if expected_error_substring:
            self.assertIn(
                expected_error_substring,
                task.error_message,
                f"Task error message '{task.error_message}' should contain '{expected_error_substring}'",
            )


class CollectorTestBase(TaskTestBase):
    """
    Base class for collector task tests.

    Extends TaskTestBase with utilities specific to testing metrics collectors,
    including database connection mocking and collector-specific helpers.

    Example:
        >>> class MyCollectorTest(CollectorTestBase):
        ...     def test_collector(self):
        ...         with self.mock_db_connection() as mock_db:
        ...             mock_db.cursor.return_value.fetchall.return_value = []
        ...             result = my_collector_function()
    """

    def mock_db_connection(self) -> MagicMock:
        """
        Create a mock database connection for collector tests.

        This method provides a properly configured mock Django database connection
        that can be used to test collectors without requiring an actual AWX database.

        Returns:
            MagicMock: A mock database connection with cursor support

        Examples:
            >>> with self.mock_db_connection() as mock_db:
            ...     # Configure the mock to return test data
            ...     mock_cursor = mock_db.cursor.return_value
            ...     mock_cursor.fetchall.return_value = [
            ...         ("value1", "value2"),
            ...         ("value3", "value4"),
            ...     ]
            ...
            ...     # Run collector function
            ...     result = collect_host_metrics(database="awx")
            ...
            ...     # Verify SQL was executed
            ...     mock_cursor.execute.assert_called()
        """
        # Create a mock connection
        mock_connection = MagicMock()

        # Create a mock cursor
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        # Set up cursor methods
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = None
        mock_cursor.execute.return_value = None

        return mock_connection

    def mock_metrics_utility_available(self, available: bool = True) -> Any:
        """
        Create a patch context for metrics_utility_available flag.

        Args:
            available (bool): Whether metrics-utility should be available

        Returns:
            Context manager for the patch

        Examples:
            >>> with self.mock_metrics_utility_available(True):
            ...     result = collect_anonymous_metrics()
            ...     self.assertEqual(result["status"], "success")
            >>>
            >>> with self.mock_metrics_utility_available(False):
            ...     result = collect_anonymous_metrics()
            ...     self.assertEqual(result["status"], "error")
        """
        return patch("apps.tasks.tasks_collector.metrics_utility_available", available)

    def mock_segment_available(self, available: bool = True) -> Any:
        """
        Create a patch context for segment_available flag.

        Args:
            available (bool): Whether Segment integration should be available

        Returns:
            Context manager for the patch

        Examples:
            >>> with self.mock_segment_available(True):
            ...     result = send_to_segment(data={"test": "data"})
            >>>
            >>> with self.mock_segment_available(False):
            ...     result = send_to_segment(data={"test": "data"})
            ...     self.assertEqual(result["segment_status"], "segment_not_available")
        """
        return patch("apps.tasks.tasks_collector.segment_available", available)

    def create_collector_task(self, function_name: str = "collect_anonymous_metrics", **kwargs: Any) -> Task:
        """
        Create a task for a collector function.

        Convenience method that sets appropriate defaults for collector tasks.

        Args:
            function_name (str): Name of the collector function
            **kwargs: Additional task fields to set

        Returns:
            Task: The created collector task

        Examples:
            >>> task = self.create_collector_task()
            >>> task = self.create_collector_task(
            ...     function_name="collect_config_metrics",
            ...     task_data={"database": "awx"}
            ... )
        """
        defaults = {
            "name": f"Test {function_name}",
            "function_name": function_name,
            "task_data": {"database": "awx"},
        }
        return self.create_task(**{**defaults, **kwargs})

    def assert_collector_result_success(
        self, result: dict[str, Any], expected_data_keys: list[str] | None = None
    ) -> None:
        """
        Assert that a collector result indicates success.

        Checks that:
        - Result status is "success"
        - Result has expected data keys (if provided)

        Args:
            result (dict): The collector result dictionary
            expected_data_keys (list, optional): List of keys that should be in result

        Raises:
            AssertionError: If the result doesn't indicate success

        Examples:
            >>> result = collect_config_metrics(database="awx")
            >>> self.assert_collector_result_success(result, ["config_data"])
            >>> self.assertIn("config_data", result)
        """
        self.assertEqual(result.get("status"), "success", f"Collector should succeed, got: {result}")

        if expected_data_keys:
            for key in expected_data_keys:
                self.assertIn(key, result, f"Result should contain '{key}' key")

    def assert_collector_result_error(
        self, result: dict[str, Any], expected_error_substring: str | None = None
    ) -> None:
        """
        Assert that a collector result indicates an error.

        Checks that:
        - Result status is "error"
        - Result has error message
        - Optionally, error message contains expected text

        Args:
            result (dict): The collector result dictionary
            expected_error_substring (str, optional): If provided, checks that the
                error message contains this substring

        Raises:
            AssertionError: If the result doesn't indicate an error

        Examples:
            >>> result = collect_metrics(database="invalid")
            >>> self.assert_collector_result_error(result)
            >>> self.assert_collector_result_error(result, "not available")
        """
        self.assertEqual(result.get("status"), "error", f"Collector should error, got: {result}")
        self.assertIn("error", result, "Error result should contain 'error' key")

        if expected_error_substring:
            error_msg = result.get("error", "")
            self.assertIn(
                expected_error_substring,
                error_msg,
                f"Error message '{error_msg}' should contain '{expected_error_substring}'",
            )
