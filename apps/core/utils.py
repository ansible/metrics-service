"""
Utility functions to reduce code duplication across the application.
"""

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def handle_task_error(
    task_instance, execution_instance=None, error_message="", exception=None, task_id=None, execution_id=None
):
    """
    Standardized error handling for task execution.

    This function provides a common way to handle task execution errors,
    reducing duplication across task execution functions.

    Args:
        task_instance: The task model instance (can be None if task_id provided)
        execution_instance: Optional task execution instance
        error_message (str): Custom error message
        exception (Exception): Optional exception that caused the error
        task_id (int): Optional task ID if task_instance is None
        execution_id (int): Optional execution ID if execution_instance is None

    Returns:
        dict: Error result dictionary
    """
    if exception:
        error_message = error_message or f"Task execution failed: {str(exception)}"

    logger.error(error_message)

    # If we don't have instances but have IDs, try to get them
    if not task_instance and task_id:
        try:
            from .models import Task

            task_instance = Task.objects.get(id=task_id)
        except Exception:
            logger.error(f"Failed to get task instance for task_id: {task_id}")

    if not execution_instance and execution_id:
        try:
            from .models import TaskExecution

            execution_instance = TaskExecution.objects.get(id=execution_id)
        except Exception:
            logger.error(f"Failed to get execution instance for execution_id: {execution_id}")

    try:
        with transaction.atomic():
            # Update task status if we have a task instance
            if task_instance:
                task_instance.status = "failed"
                task_instance.error_message = error_message
                task_instance.completed_at = timezone.now()
                task_instance.attempts = getattr(task_instance, "attempts", 0) + 1
                task_instance.save()

            # Update execution status if provided
            if execution_instance:
                execution_instance.status = "failed"
                execution_instance.error_message = error_message
                execution_instance.completed_at = timezone.now()
                execution_instance.save()

    except Exception as save_error:
        logger.error(f"Failed to update task status after error: {save_error}")

    return {"status": "error", "error": error_message}


def update_task_status(task_instance, execution_instance=None, status="", result_data=None, error_message=""):
    """
    Standardized task status updating.

    This function provides a common way to update task and execution status,
    reducing duplication across task execution functions.

    Args:
        task_instance: The task model instance
        execution_instance: Optional task execution instance
        status (str): New status for the task
        result_data (dict): Optional result data
        error_message (str): Optional error message

    Returns:
        None
    """
    with transaction.atomic():
        # Refresh from database to get latest state
        task_instance.refresh_from_db()

        # Update task fields
        task_instance.status = status
        if result_data is not None:
            task_instance.result_data = result_data
        if error_message:
            task_instance.error_message = error_message
        elif status == "completed":
            task_instance.error_message = ""

        if status in ["completed", "failed"]:
            task_instance.completed_at = timezone.now()
        elif status == "running":
            task_instance.started_at = timezone.now()
            task_instance.attempts = getattr(task_instance, "attempts", 0) + 1

        task_instance.save()

        # Update execution instance if provided
        if execution_instance:
            execution_instance.refresh_from_db()
            execution_instance.status = status
            if result_data is not None:
                execution_instance.result_data = result_data
            if error_message:
                execution_instance.error_message = error_message
            if status in ["completed", "failed"]:
                execution_instance.completed_at = timezone.now()
            execution_instance.save()


def get_or_create_execution_record(task_instance, worker_id=None):
    """
    Get or create a task execution record.

    This function provides a standardized way to create execution records
    for tasks, reducing duplication in task execution functions.

    Args:
        task_instance: The task model instance
        worker_id (str): Optional worker identifier

    Returns:
        TaskExecution: The execution record instance
    """
    import os

    from .models import TaskExecution

    if worker_id is None:
        worker_id = f"worker-{os.getpid()}"

    execution = TaskExecution.objects.create(task=task_instance, status="pending", worker_id=worker_id)

    logger.info(f"Created execution record {execution.id} for task {task_instance.id}")
    return execution


def validate_task_data(data: dict[str, Any], required_fields: list = None) -> str | None:
    """
    Validate task data against required fields.

    This function provides a standardized way to validate task data,
    reducing duplication across task functions.

    Args:
        data (dict): The task data to validate
        required_fields (list): List of required field names

    Returns:
        str or None: Error message if validation fails, None if valid
    """
    if required_fields is None:
        required_fields = []

    if not isinstance(data, dict):
        return "Task data must be a dictionary"

    missing_fields = []
    for field in required_fields:
        if field not in data or data[field] is None:
            missing_fields.append(field)

    if missing_fields:
        # For backwards compatibility, handle special case of task_id
        if len(missing_fields) == 1 and missing_fields[0] == "task_id":
            return "No task_id provided"
        return f"Missing required fields: {', '.join(missing_fields)}"

    return None


def create_task_result(status: str, data: dict[str, Any] = None, error: str = "") -> dict[str, Any]:
    """
    Create a standardized task result dictionary.

    This function provides a consistent format for task results,
    reducing duplication across task functions.

    Args:
        status (str): Task status (success, error, etc.)
        data (dict): Optional result data
        error (str): Optional error message

    Returns:
        dict: Standardized result dictionary
    """
    result = {
        "status": status,
        "timestamp": timezone.now().isoformat(),
    }

    if data:
        result.update(data)

    if error:
        result["error"] = error

    return result


def log_task_execution(task_name: str, operation: str, details: str = "", level: str = "info"):
    """
    Standardized logging for task execution.

    This function provides consistent logging format across all task operations,
    reducing duplication in logging statements.

    Args:
        task_name (str): Name of the task
        operation (str): Operation being performed (start, complete, error, etc.)
        details (str): Additional details to log
        level (str): Log level (info, warning, error, debug)

    Returns:
        None
    """
    message = f"Task '{task_name}' {operation}"
    if details:
        message += f": {details}"

    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message)


def get_related_object_safely(instance, field_name: str, default=None):
    """
    Safely get a related object from an instance.

    This function provides a safe way to access related objects that might
    not exist, reducing try/except duplication across the codebase.

    Args:
        instance: The model instance
        field_name (str): Name of the related field
        default: Default value to return if the relation doesn't exist

    Returns:
        The related object or the default value
    """
    try:
        return getattr(instance, field_name)
    except AttributeError:
        return default
    except instance.DoesNotExist:
        return default


def get_count_safely(queryset_or_manager) -> int:
    """
    Safely get count from a queryset or manager.

    This function provides a safe way to get counts that handles
    potential errors, reducing duplication in count operations.

    Args:
        queryset_or_manager: QuerySet or Manager to count

    Returns:
        int: Count of objects, 0 if error
    """
    try:
        return queryset_or_manager.count()
    except Exception as e:
        logger.warning(f"Error getting count: {e}")
        return 0


def build_error_response(message: str, details: dict[str, Any] = None, status_code: int = 400) -> dict[str, Any]:
    """
    Build a standardized error response dictionary.

    This function provides a consistent format for error responses,
    reducing duplication across view error handling.

    Args:
        message (str): Main error message
        details (dict): Optional additional error details
        status_code (int): HTTP status code for the error

    Returns:
        dict: Standardized error response
    """
    error_response = {
        "error": message,
        "status_code": status_code,
        "timestamp": timezone.now().isoformat(),
    }

    if details:
        error_response["details"] = details

    return error_response
