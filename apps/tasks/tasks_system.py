"""
System and maintenance background tasks for metrics_service.

This module provides system-level tasks including cleanup, maintenance,
communication, and testing tasks with proper error handling and status tracking.
"""

import logging
import os
from typing import Any

from .utils import (
    create_task_result,
    ensure_django_setup,
    get_task_and_execution,
    handle_task_error,
    log_task_execution,
    update_task_status,
)

logger = logging.getLogger(__name__)

ERROR_DJANGO_NOT_READY = "ERROR_DJANGO_NOT_READY"

try:
    from dispatcherd.publish import task
except ImportError:

    def task():
        def decorator(func):
            return func

        return decorator


# FIXME: is this really a task, or more like a task runner .. used by submit_task_to_dispatcher
# ... doesn't that mean that this is the ONLY task? apart from periodic sync? .. or what other submit_task bare


@task(queue="metrics_tasks", decorate=False)
def execute_db_task(**kwargs) -> dict[str, Any]:
    """
    Execute a database-defined task with comprehensive error handling and tracking.

    This function is the main entry point for executing tasks that are defined
    in the database. It handles the complete lifecycle of task execution including
    validation, execution, status tracking, and post-execution processing.

    Args:
        **kwargs: Task data containing:
            - task_id (int): ID of the task to execute (required)
            - execution_id (int): ID of the execution record (optional)

    Returns:
        dict: Task result dictionary with execution status and results
    """
    ensure_django_setup()
    log_task_execution("execute_db_task", "start", "Starting database task execution")

    task_id = kwargs.get("task_id")
    if not task_id:
        return create_task_result("error", error="task_id is required")

    execution_id = kwargs.get("execution_id")

    try:
        # Get task and execution objects
        task, execution = get_task_and_execution(task_id, execution_id)

        # Import TASK_FUNCTIONS here to avoid circular import
        # This import happens at runtime, not module load time
        from .tasks import TASK_FUNCTIONS

        # Validate task function exists
        if task.function_name not in TASK_FUNCTIONS:
            error_msg = f"Task function '{task.function_name}' not found in TASK_FUNCTIONS"
            return handle_task_error(task, execution, error_msg)

        # Start task execution
        update_task_status(task, execution, status="running")
        log_task_execution(task.name, "running", f"Executing function: {task.function_name}")

        # Execute the actual task function
        task_function = TASK_FUNCTIONS[task.function_name]
        result = task_function(**task.task_data)

        # Complete task execution
        status = "completed" if result.get("status") == "success" else "failed"
        error_message = result.get("error", "") if status == "failed" else ""

        update_task_status(task, execution, status=status, result_data=result, error_message=error_message)

        log_task_execution(task.name, "completed", f"Task execution finished with status: {status}")

        # Auto-retry if the task failed and has attempts remaining
        if status == "failed":
            task.refresh_from_db()
            if task.can_retry():
                logger.info(f"Auto-retrying task {task.name} (attempt {task.attempts}/{task.max_attempts})")
                task.retry()

        return result

    except Exception as e:
        return handle_task_error(None, None, task_id=task_id, execution_id=execution_id, exception=e)


def submit_task_to_dispatcher(task: Any) -> None:
    """
    Submit a task to the dispatcher for execution.

    Args:
        task: The task to submit
    """
    from .models import TaskExecution

    try:
        # Create execution record
        TaskExecution.objects.create(task=task, status="pending", worker_id=f"dispatcher-{os.getpid()}")

        # Ensure dispatcherd is configured before attempting to submit tasks
        from .dispatcherd_config import ensure_dispatcherd_configured

        ensure_dispatcherd_configured()

        # Import dispatcherd submit function
        from dispatcherd.publish import submit_task

        # Determine the appropriate queue based on task type
        from .dispatcherd_config import get_queue_for_function

        queue = get_queue_for_function(task.function_name)

        # Submit to dispatcherd using execute_db_task as the entry point
        submit_task(execute_db_task, kwargs={"task_id": task.id}, queue=queue)

        # Update task status to indicate it's been submitted
        task.status = "pending"
        task.save()

        logger.info(f"Submitted task {task.name} (ID: {task.id}) to dispatcher queue {queue}")

    except Exception as e:
        logger.error(f"Error submitting task to dispatcher: {str(e)}")
        task.status = "failed"
        task.error_message = f"Failed to submit to dispatcher: {str(e)}"
        task.save()


# runs during `manage.py metrics_service init-system-tasks`
def create_system_tasks() -> dict[str, Any]:
    """
    Create system-defined tasks from task groups in the database.

    This function is intended to be called only from the init container
    (entrypoint-init.sh), before the application and scheduler start. At that
    point no tasks can be running, so unconditional deletion is safe.

    Removes all existing system tasks and recreates them from task group
    definitions, ensuring the database always matches the code.

    Returns:
        dict: Summary of tasks created and removed.
    """
    try:
        from .models import Task
        from .task_groups import get_all_enabled_tasks
    except ImportError:
        # Handle case where Django isn't fully set up yet
        return {"error": "ERROR_DJANGO_NOT_READY", "created": 0, "removed": 0}

    results = {"created": 0, "removed": 0, "tasks": []}

    # Remove all existing system tasks
    _, deletion_info = Task.objects.filter(is_system_task=True).delete()
    removed_count = deletion_info.get("tasks.Task", 0)
    results["removed"] = removed_count
    if removed_count > 0:
        results["tasks"].append(f"Removed {removed_count} existing system tasks")
        logger.info(f"Removed {removed_count} existing system tasks")

    # Get all task group definitions
    task_groups = get_all_enabled_tasks()

    # Create fresh tasks from task groups
    for task_id, config in task_groups.items():
        try:
            _create_task_from_group(task_id, config, results, Task)
        except Exception as e:
            results["tasks"].append(f"Error with {task_id}: {str(e)}")
            logger.error(f"Failed to create task {task_id}: {e}")

    return results


def _create_task_from_group(task_id: str, config: dict[str, Any], results: dict[str, Any], task_model) -> None:
    """
    Create a system task from task group definition.

    Args:
        task_id: Unique identifier for the task
        config: Task configuration from task groups
        results: Results dict to update
        task_model: Task model class
    """
    # FIXME: feature_flag .. update
    # Prepare task data including feature flag for runtime checking
    task_data = config.get("args", {}).copy()
    if config.get("feature_flag"):
        # FIXME: no, unless users can edit feature flags by posting args .. separate field from task_data? or the task just looks itself up?
        task_data["_feature_flag"] = config["feature_flag"]

    new_task = task_model.objects.create(
        name=task_id,
        description=config.get("description", ""),
        function_name=config["function"],
        task_data=task_data,
        cron_expression=config.get("cron"),
        is_system_task=True,
        status="pending",
    )
    results["created"] += 1
    results["tasks"].append(f"Created: {new_task.name}")


def get_system_task_info() -> dict[str, Any]:
    """
    Get information about system tasks for display purposes.

    Returns:
        dict: Information about system tasks including their status and schedules
    """
    try:
        from .models import Task
    except ImportError:
        return {"error": "ERROR_DJANGO_NOT_READY", "system_tasks": []}

    system_tasks = Task.objects.filter(is_system_task=True).order_by("name")

    task_info = []
    for task in system_tasks:
        info = {
            "id": task.id,
            "name": task.name,
            "function_name": task.function_name,
            "description": task.description,
            "status": task.status,
            "cron_expression": task.cron_expression,
            "created": task.created.isoformat() if task.created else None,
            "last_run": task.completed_at.isoformat() if task.completed_at else None,
            "category": "unknown",  # FIXME .. from task_groups?
        }
        task_info.append(info)

    return {
        "system_tasks": task_info,
        "total_count": len(task_info),
        "categories": list({task["category"] for task in task_info}),
    }
