"""
Pytest fixtures for task-related tests.

This module provides reusable pytest fixtures for creating tasks in various
states and configurations. These fixtures can be used across the test suite
to eliminate duplication and ensure consistent test data.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.tasks.models import Task, TaskChain, TaskChainMembership, TaskDependency, TaskExecution
from tests.test_utils import get_test_password

User = get_user_model()


@pytest.fixture
def test_user(db):
    """
    Create a test user for task-related tests.

    This fixture provides a standard test user that can be used as the
    creator of tasks across multiple test scenarios.

    Returns:
        User: A test user instance

    Example:
        >>> def test_task_creation(test_user):
        ...     task = Task.objects.create(
        ...         name="Test",
        ...         function_name="cleanup_old_data",
        ...         created_by=test_user
        ...     )
    """
    return User.objects.create_user(username="testuser", email="test@example.com", password=get_test_password())


@pytest.fixture
def sample_task(test_user):
    """
    Create a basic sample task in pending status.

    This is the most common fixture for testing task functionality.
    It creates a task with minimal configuration in pending status.

    Returns:
        Task: A pending task instance

    Example:
        >>> def test_task_execution(sample_task):
        ...     assert sample_task.status == "pending"
        ...     assert sample_task.is_ready_to_run() is True
    """
    return Task.objects.create(
        name="Sample Task",
        description="A sample task for testing",
        function_name="cleanup_old_data",
        task_data={"days_old": 30},
        status="pending",
        priority=2,
        created_by=test_user,
    )


@pytest.fixture
def pending_task(test_user):
    """
    Create a task in pending status.

    Returns:
        Task: A task in pending status

    Example:
        >>> def test_task_ready_to_run(pending_task):
        ...     assert pending_task.is_ready_to_run() is True
    """
    return Task.objects.create(
        name="Pending Task",
        function_name="send_notification_email",
        task_data={"recipient": "test@example.com"},
        status="pending",
        created_by=test_user,
    )


@pytest.fixture
def running_task(test_user):
    """
    Create a task in running status.

    This fixture creates a task that is currently executing,
    with a started_at timestamp.

    Returns:
        Task: A task in running status

    Example:
        >>> def test_running_task_behavior(running_task):
        ...     assert running_task.status == "running"
        ...     assert running_task.started_at is not None
    """
    return Task.objects.create(
        name="Running Task",
        function_name="process_user_data",
        task_data={"user_id": 1},
        status="running",
        started_at=timezone.now(),
        created_by=test_user,
    )


@pytest.fixture
def completed_task(test_user):
    """
    Create a task in completed status.

    This fixture creates a task that has finished successfully,
    with both started_at and completed_at timestamps.

    Returns:
        Task: A task in completed status

    Example:
        >>> def test_completed_task_cleanup(completed_task):
        ...     assert completed_task.status == "completed"
        ...     assert completed_task.completed_at is not None
    """
    return Task.objects.create(
        name="Completed Task",
        function_name="cleanup_old_data",
        task_data={},
        status="completed",
        started_at=timezone.now() - timedelta(minutes=5),
        completed_at=timezone.now(),
        result_data={"status": "success", "cleaned_count": 10},
        created_by=test_user,
    )


@pytest.fixture
def failed_task(test_user):
    """
    Create a task in failed status.

    This fixture creates a task that has failed with an error,
    including error message and timestamps.

    Returns:
        Task: A task in failed status

    Example:
        >>> def test_task_retry(failed_task):
        ...     assert failed_task.status == "failed"
        ...     assert failed_task.can_retry() is True
        ...     failed_task.retry()
        ...     assert failed_task.status == "pending"
    """
    return Task.objects.create(
        name="Failed Task",
        function_name="send_notification_email",
        task_data={"recipient": "test@example.com"},
        status="failed",
        started_at=timezone.now() - timedelta(minutes=5),
        completed_at=timezone.now(),
        error_message="Connection timeout",
        attempts=1,
        max_attempts=3,
        created_by=test_user,
    )


@pytest.fixture
def cancelled_task(test_user):
    """
    Create a task in cancelled status.

    Returns:
        Task: A task in cancelled status

    Example:
        >>> def test_cancelled_task_behavior(cancelled_task):
        ...     assert cancelled_task.status == "cancelled"
        ...     assert cancelled_task.is_ready_to_run() is False
    """
    return Task.objects.create(
        name="Cancelled Task",
        function_name="process_user_data",
        task_data={},
        status="cancelled",
        created_by=test_user,
    )


@pytest.fixture
def scheduled_task(test_user):
    """
    Create a task scheduled for future execution.

    This fixture creates a task with a scheduled_time in the future,
    useful for testing task scheduling functionality.

    Returns:
        Task: A task scheduled for future execution

    Example:
        >>> def test_scheduled_task_not_ready(scheduled_task):
        ...     assert scheduled_task.is_ready_to_run() is False
        ...     assert scheduled_task.scheduled_time > timezone.now()
    """
    return Task.objects.create(
        name="Scheduled Task",
        function_name="cleanup_old_data",
        task_data={"days_old": 7},
        status="pending",
        scheduled_time=timezone.now() + timedelta(hours=1),
        created_by=test_user,
    )


@pytest.fixture
def recurring_task(test_user):
    """
    Create a recurring task with cron expression.

    This fixture creates a task that should repeat based on its
    cron expression, useful for testing recurring task functionality.

    Returns:
        Task: A recurring task with cron expression

    Example:
        >>> def test_recurring_task_schedule(recurring_task):
        ...     assert recurring_task.is_recurring is True
        ...     assert recurring_task.cron_expression == "0 2 * * *"
        ...     next_run = recurring_task.get_next_run_time()
        ...     assert next_run is not None
    """
    return Task.objects.create(
        name="Daily Cleanup",
        function_name="cleanup_old_data",
        task_data={"days_old": 30},
        status="pending",
        is_recurring=True,
        cron_expression="0 2 * * *",  # Daily at 2 AM
        priority=2,
        created_by=test_user,
    )


@pytest.fixture
def system_task(test_user):
    """
    Create a system-defined task.

    This fixture creates a task marked as is_system_task=True,
    useful for testing system task protection and management.

    Returns:
        Task: A system task

    Example:
        >>> def test_system_task_protection(system_task):
        ...     assert system_task.is_system_task is True
        ...     assert system_task.can_delete() is False
        ...     assert system_task.can_modify() is False
    """
    return Task.objects.create(
        name="System Cleanup Task",
        function_name="cleanup_old_tasks",
        task_data={"days_old": 5},
        status="pending",
        is_recurring=True,
        cron_expression="0 3 * * *",
        is_system_task=True,
        priority=3,
        created_by=test_user,
    )


@pytest.fixture
def sample_execution(sample_task):
    """
    Create a sample task execution.

    This fixture creates a TaskExecution record for the sample_task,
    useful for testing task execution tracking and history.

    Returns:
        TaskExecution: A task execution record

    Example:
        >>> def test_task_execution_tracking(sample_execution):
        ...     assert sample_execution.task is not None
        ...     assert sample_execution.status == "pending"
        ...     assert sample_execution.started_at is not None
    """
    return TaskExecution.objects.create(task=sample_task, status="pending", started_at=timezone.now())


@pytest.fixture
def task_chain(test_user):
    """
    Create a task chain with multiple tasks.

    This fixture creates a TaskChain with tasks in ordered sequence,
    useful for testing task chain workflow functionality.

    Returns:
        tuple: (TaskChain, list of Tasks in order)

    Example:
        >>> def test_task_chain_execution(task_chain):
        ...     chain, tasks = task_chain
        ...     assert chain.is_active is True
        ...     assert len(tasks) == 3
        ...     # Verify tasks are in correct order
        ...     memberships = chain.taskchainmembership_set.order_by("order")
        ...     assert list(memberships.values_list("task_id", flat=True)) == [t.id for t in tasks]
    """
    # Create the chain
    chain = TaskChain.objects.create(
        name="Test Task Chain", description="A chain of tasks for testing", is_active=True, created_by=test_user
    )

    # Create tasks for the chain
    task1 = Task.objects.create(
        name="Chain Task 1", function_name="cleanup_old_data", task_data={}, status="pending", created_by=test_user
    )

    task2 = Task.objects.create(
        name="Chain Task 2",
        function_name="send_notification_email",
        task_data={"recipient": "test@example.com"},
        status="pending",
        created_by=test_user,
    )

    task3 = Task.objects.create(
        name="Chain Task 3", function_name="process_user_data", task_data={}, status="pending", created_by=test_user
    )

    # Add tasks to chain with ordering
    TaskChainMembership.objects.create(chain=chain, task=task1, order=1)
    TaskChainMembership.objects.create(chain=chain, task=task2, order=2)
    TaskChainMembership.objects.create(chain=chain, task=task3, order=3)

    return chain, [task1, task2, task3]


@pytest.fixture
def task_dependency(test_user):
    """
    Create a task dependency relationship.

    This fixture creates two tasks with a dependency relationship,
    useful for testing task dependency and prerequisite functionality.

    Returns:
        tuple: (dependent_task, prerequisite_task, dependency)

    Example:
        >>> def test_task_dependency_blocking(task_dependency):
        ...     dependent, prerequisite, dep = task_dependency
        ...     # Dependent task should not be ready while prerequisite is pending
        ...     assert dependent.is_ready_to_run() is False
        ...
        ...     # Complete the prerequisite
        ...     prerequisite.status = "completed"
        ...     prerequisite.save()
        ...
        ...     # Now dependent should be ready
        ...     assert dependent.is_ready_to_run() is True
    """
    # Create prerequisite task
    prerequisite = Task.objects.create(
        name="Prerequisite Task",
        function_name="cleanup_old_data",
        task_data={},
        status="pending",
        created_by=test_user,
    )

    # Create dependent task
    dependent = Task.objects.create(
        name="Dependent Task",
        function_name="send_notification_email",
        task_data={"recipient": "test@example.com"},
        status="pending",
        created_by=test_user,
    )

    # Create dependency relationship
    dependency = TaskDependency.objects.create(
        dependent_task=dependent, prerequisite_task=prerequisite, required_status="completed"
    )

    return dependent, prerequisite, dependency
