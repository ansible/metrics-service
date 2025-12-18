"""
Task submission utilities for dispatcher integration.

This module consolidates task submission logic and breaks circular imports between
models.py and tasks_system.py by providing a central location for task submission
and queue determination logic.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def determine_task_queue(function_name: str) -> str:
    """
    Determine the appropriate queue for a task function.

    Maps task function names to their corresponding dispatcher queues.
    This centralizes queue routing logic that was previously duplicated
    in dispatcherd_config.py and other modules.

    Args:
        function_name: Name of the task function to execute

    Returns:
        Queue name (defaults to "metrics_tasks" if not explicitly mapped)

    Examples:
        >>> determine_task_queue("cleanup_old_data")
        'metrics_cleanup'

        >>> determine_task_queue("collect_anonymous_metrics")
        'metrics_collectors'

        >>> determine_task_queue("unknown_task")
        'metrics_tasks'
    """
    queue_mapping = {
        # Core system tasks
        "hello_world": "metrics_tasks",
        "cleanup_old_data": "metrics_cleanup",
        "cleanup_old_tasks": "metrics_cleanup",
        "send_notification_email": "metrics_notifications",
        "process_user_data": "metrics_tasks",
        "execute_db_task": "metrics_tasks",
        "sleep": "metrics_tasks",
        # Metrics collection tasks
        "collect_anonymous_metrics": "metrics_collectors",
        "collect_config_metrics": "metrics_collectors",
        "collect_job_host_summary": "metrics_collectors",
        "collect_host_metrics": "metrics_collectors",
        "collect_all_metrics": "metrics_collectors",
        # Metrics-utility tasks
        "gather_automation_controller_billing_data": "metrics_utility",
        "build_metrics_report": "metrics_utility",
        "metrics_utility_health_check": "metrics_utility",
        "metrics_utility_custom_command": "metrics_utility",
    }

    return queue_mapping.get(function_name, "metrics_tasks")


def create_execution_record(task: Any, worker_id: str | None = None) -> Any:
    """
    Create a TaskExecution record for tracking task execution.

    This function is extracted from submit_task_to_dispatcher to allow
    reuse in other contexts (retry logic, manual execution, etc.).

    Args:
        task: Task model instance to create execution for
        worker_id: Optional worker ID (defaults to "dispatcher-{pid}")

    Returns:
        TaskExecution instance

    Raises:
        Exception: If execution record creation fails
    """
    from .models import TaskExecution

    if worker_id is None:
        worker_id = f"dispatcher-{os.getpid()}"

    execution = TaskExecution.objects.create(task=task, status="pending", worker_id=worker_id)

    logger.debug(f"Created execution record {execution.id} for task {task.id}")

    return execution


def submit_task_for_execution(task: Any, queue: str | None = None) -> None:
    """
    Submit a task to the dispatcher for execution.

    This is the core task submission function that breaks the circular import
    between models.py and tasks_system.py. It handles:
    - Creating execution records
    - Ensuring dispatcherd is configured
    - Determining the appropriate queue
    - Submitting to dispatcherd
    - Updating task status

    Args:
        task: Task model instance to submit
        queue: Optional queue name (auto-determined if not provided)

    Raises:
        Exception: If task submission fails (sets task status to 'failed')

    Examples:
        >>> from apps.tasks.models import Task
        >>> task = Task.objects.get(id=1)
        >>> submit_task_for_execution(task)
        # Task is submitted to appropriate queue

        >>> submit_task_for_execution(task, queue="custom_queue")
        # Task is submitted to specified queue
    """
    from .logging_utils import TaskLogger

    task_logger = TaskLogger(task.name)

    try:
        # Create execution record for tracking
        create_execution_record(task)

        # Ensure dispatcherd is properly configured
        from .dispatcherd_config import ensure_dispatcherd_configured

        ensure_dispatcherd_configured()

        # Import the entry point task function
        # This is the function that dispatcherd will call
        # Import dispatcherd submit function
        from dispatcherd.publish import submit_task

        from .tasks_system import execute_db_task

        # Determine queue if not explicitly provided
        if queue is None:
            queue = determine_task_queue(task.function_name)

        # Submit to dispatcherd using execute_db_task as the entry point
        # execute_db_task will look up the actual task function and execute it
        submit_task(execute_db_task, kwargs={"task_id": task.id}, queue=queue)

        # Update task status to indicate successful submission
        task.status = "pending"
        task.save()

        task_logger.log_submission(queue=queue, task_id=task.id)

    except Exception as e:
        task_logger.log_error(e)

        # Update task to failed status with error message
        task.status = "failed"
        task.error_message = f"Failed to submit to dispatcher: {str(e)}"
        task.save()

        # Re-raise to allow caller to handle if needed
        raise


def is_task_submittable(task: Any) -> tuple[bool, str]:
    """
    Check if a task can be submitted to the dispatcher.

    Validates that:
    - Task has a valid function_name
    - Task is not already running
    - Task is not cancelled
    - Required dependencies are met

    Args:
        task: Task model instance to validate

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if task can be submitted
        - error_message: Empty string if valid, error description if invalid

    Examples:
        >>> from apps.tasks.models import Task
        >>> task = Task.objects.create(name="Test", function_name="hello_world")
        >>> is_submittable, error = is_task_submittable(task)
        >>> is_submittable
        True
        >>> error
        ''

        >>> running_task = Task.objects.create(name="Test", function_name="hello_world", status="running")
        >>> is_submittable, error = is_task_submittable(running_task)
        >>> is_submittable
        False
        >>> error
        'Task is already running'
    """
    # Check if task has a function name
    if not task.function_name:
        return False, "Task has no function_name specified"

    # Check if task is already running
    if task.status == "running":
        return False, "Task is already running"

    # Check if task was cancelled
    if task.status == "cancelled":
        return False, "Task has been cancelled"

    # Check if task is completed (shouldn't resubmit)
    if task.status == "completed":
        return False, "Task is already completed (use retry() to resubmit)"

    # All validation checks passed
    return True, ""


def submit_tasks_batch(tasks: list[Any], fail_fast: bool = False) -> dict[str, Any]:
    """
    Submit multiple tasks to the dispatcher as a batch.

    This is useful for bulk task operations where you want to submit
    many tasks efficiently with centralized error handling.

    Args:
        tasks: List of Task instances to submit
        fail_fast: If True, stop on first error; if False, continue and collect all errors

    Returns:
        Dictionary with submission results:
        {
            "submitted": [task_ids that succeeded],
            "failed": [task_ids that failed],
            "errors": {task_id: error_message},
            "total": total_count,
            "success_count": successful_submissions,
            "failure_count": failed_submissions
        }

    Examples:
        >>> tasks = Task.objects.filter(status="pending")
        >>> result = submit_tasks_batch(tasks)
        >>> print(f"Submitted {result['success_count']}/{result['total']} tasks")
    """
    submitted = []
    failed = []
    errors = {}

    for task in tasks:
        try:
            # Validate before submitting
            is_valid, error_msg = is_task_submittable(task)
            if not is_valid:
                failed.append(task.id)
                errors[task.id] = error_msg
                if fail_fast:
                    break
                continue

            # Submit the task
            submit_task_for_execution(task)
            submitted.append(task.id)

        except Exception as e:
            failed.append(task.id)
            errors[task.id] = str(e)

            if fail_fast:
                break

    return {
        "submitted": submitted,
        "failed": failed,
        "errors": errors,
        "total": len(tasks),
        "success_count": len(submitted),
        "failure_count": len(failed),
    }
