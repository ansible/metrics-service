"""
Error handling decorators and context managers for task execution.

This module provides standardized error handling patterns that can be applied
to task functions via decorators, reducing code duplication and ensuring
consistent error responses across all tasks.
"""

import functools
import logging
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from .logging_utils import TaskLogger
from .utils import create_task_result, ensure_django_setup

logger = logging.getLogger(__name__)


def with_task_error_handling(task_name: str):
    """
    Decorator to wrap task functions with standardized error handling.

    This decorator:
    - Ensures Django is set up (for dispatcherd workers)
    - Logs task start, completion, and errors
    - Catches all exceptions and returns standardized error results
    - Maintains function signature and docstring

    Args:
        task_name: Name of the task for logging context

    Returns:
        Decorated function with error handling

    Examples:
        >>> @with_task_error_handling("my_task")
        >>> def my_task(**kwargs):
        ...     return {"status": "success", "data": "result"}

        >>> result = my_task(param="value")
        >>> result["status"]
        'success'

        >>> @with_task_error_handling("failing_task")
        >>> def failing_task(**kwargs):
        ...     raise ValueError("Task failed")

        >>> result = failing_task()
        >>> result["status"]
        'error'
        >>> "Task failed" in result["error"]
        True
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(**kwargs) -> dict[str, Any]:
            # Ensure Django is configured for dispatcherd workers
            ensure_django_setup()

            # Create task logger
            task_logger = TaskLogger(task_name)
            task_logger.log_start()

            try:
                # Execute the task function
                result = func(**kwargs)

                task_logger.log_complete()
                return result

            except Exception as e:
                # Log error with full traceback
                task_logger.log_error(e, exc_info=True)

                # Return standardized error result
                error_msg = f"{task_name} task failed: {str(e)}"
                return create_task_result("error", error=error_msg)

        return wrapper

    return decorator


def with_metrics_availability_check(func: Callable) -> Callable:
    """
    Decorator to check if metrics-utility is available before running task.

    This decorator should be applied to tasks that require metrics-utility.
    If metrics-utility is not available, the task returns an error immediately
    without executing.

    Args:
        func: Function to decorate

    Returns:
        Decorated function with metrics-utility availability check

    Examples:
        >>> @with_metrics_availability_check
        >>> def collect_metrics(**kwargs):
        ...     return {"status": "success"}

        >>> # If metrics-utility is not available:
        >>> result = collect_metrics()
        >>> result["status"]
        'error'
        >>> "metrics-utility is not available" in result["error"]
        True
    """

    @functools.wraps(func)
    def wrapper(**kwargs) -> dict[str, Any]:
        try:
            from apps.tasks.tasks_collector import metrics_utility_available
        except ImportError:
            metrics_utility_available = False

        if not metrics_utility_available:
            return create_task_result("error", error="metrics-utility is not available")

        return func(**kwargs)

    return wrapper


def with_segment_availability_check(func: Callable) -> Callable:
    """
    Decorator to check if Segment integration is available before running task.

    This decorator should be applied to tasks that require Segment.
    If Segment is not available, the task returns an error immediately.

    Args:
        func: Function to decorate

    Returns:
        Decorated function with Segment availability check

    Examples:
        >>> @with_segment_availability_check
        >>> def send_to_segment(**kwargs):
        ...     return {"status": "success"}

        >>> # If Segment is not available:
        >>> result = send_to_segment()
        >>> result["status"]
        'error'
        >>> "Segment integration is not available" in result["error"]
        True
    """

    @functools.wraps(func)
    def wrapper(**kwargs) -> dict[str, Any]:
        try:
            from metrics_utility.library.storage.segment import segment_available
        except ImportError:
            segment_available = False

        if not segment_available:
            return create_task_result("error", error="Segment integration is not available")

        return func(**kwargs)

    return wrapper


def with_database_connection(database_name: str = "default"):
    """
    Decorator to ensure database connection is available for task.

    This decorator checks that the specified database connection exists
    before running the task.

    Args:
        database_name: Name of the database connection to check

    Returns:
        Decorator function

    Examples:
        >>> @with_database_connection("awx")
        >>> def query_database(**kwargs):
        ...     return {"status": "success"}

        >>> # If 'awx' database is not configured:
        >>> result = query_database()
        >>> result["status"]
        'error'
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(**kwargs) -> dict[str, Any]:
            from django.db import connections

            if database_name not in connections:
                error_msg = f"Database '{database_name}' is not configured"
                return create_task_result("error", error=error_msg)

            # Try to ensure connection is valid
            try:
                connections[database_name].ensure_connection()
            except Exception as e:
                error_msg = f"Cannot connect to database '{database_name}': {str(e)}"
                return create_task_result("error", error=error_msg)

            return func(**kwargs)

        return wrapper

    return decorator


@contextmanager
def task_execution_context(task_id: int):
    """
    Context manager for task execution lifecycle.

    Handles:
    - Task status updates (pending -> running -> completed/failed)
    - Execution timing
    - Error capture
    - Cleanup

    Args:
        task_id: ID of the task being executed

    Yields:
        Tuple of (task, execution) objects

    Examples:
        >>> with task_execution_context(task_id=123) as (task, execution):
        ...     # Task status is now 'running'
        ...     result = do_work()
        ...     # On success, status becomes 'completed'
        ...     # On exception, status becomes 'failed'
    """
    from django.utils import timezone

    from .models import Task

    task = Task.objects.get(id=task_id)
    execution = None

    try:
        # Get or create execution record
        from .models import TaskExecution

        execution = TaskExecution.objects.filter(task=task).first()
        if not execution:
            execution = TaskExecution.objects.create(task=task, status="pending")

        # Update statuses to running
        task.status = "running"
        task.started_at = timezone.now()
        task.save()

        execution.status = "running"
        execution.started_at = timezone.now()
        execution.save()

        # Yield control to task execution
        yield task, execution

        # On successful completion
        task.status = "completed"
        task.completed_at = timezone.now()
        task.save()

        execution.status = "completed"
        execution.completed_at = timezone.now()
        execution.save()

    except Exception as e:
        # On error
        if task:
            task.status = "failed"
            task.error_message = str(e)
            task.completed_at = timezone.now()
            task.save()

        if execution:
            execution.status = "failed"
            execution.error_message = str(e)
            execution.completed_at = timezone.now()
            execution.save()

        # Re-raise exception to caller
        raise


def combine_decorators(*decorators):
    """
    Combine multiple decorators into a single decorator.

    This is useful when you want to apply multiple decorators to a function
    in a specific order.

    Args:
        *decorators: Variable number of decorator functions

    Returns:
        Combined decorator function

    Examples:
        >>> combined = combine_decorators(
        ...     with_task_error_handling("my_task"),
        ...     with_metrics_availability_check
        ... )
        >>> @combined
        >>> def my_task(**kwargs):
        ...     return {"status": "success"}
    """

    def decorator(func: Callable) -> Callable:
        for dec in reversed(decorators):
            func = dec(func)
        return func

    return decorator


# Common decorator combinations for convenience
def with_standard_task_decorators(task_name: str):
    """
    Apply standard task decorators (error handling + Django setup).

    This is the most common decorator combination for standard tasks.

    Args:
        task_name: Name of the task for logging

    Returns:
        Combined decorator

    Examples:
        >>> @with_standard_task_decorators("cleanup_task")
        >>> def cleanup_task(**kwargs):
        ...     return {"status": "success"}
    """
    return with_task_error_handling(task_name)


def with_metrics_task_decorators(task_name: str):
    """
    Apply decorators for metrics collection tasks.

    Combines error handling with metrics-utility availability check.

    Args:
        task_name: Name of the task for logging

    Returns:
        Combined decorator

    Examples:
        >>> @with_metrics_task_decorators("collect_metrics")
        >>> def collect_metrics(**kwargs):
        ...     return {"status": "success"}
    """
    return combine_decorators(with_task_error_handling(task_name), with_metrics_availability_check)
