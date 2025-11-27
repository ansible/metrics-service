"""
Utility functions for task management and execution.
"""

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def ensure_django_setup():
    """
    Ensure Django is properly configured for dispatcherd workers.

    This function must be called at the beginning of any task function
    that needs to access Django models or ORM functionality, since
    dispatcherd workers run in separate processes without Django initialized.
    """
    import django
    from django.conf import settings

    if not settings.configured:
        import os

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metrics_service.settings")
        django.setup()


def task_execution_wrapper(task_name: str):
    """
    Decorator to handle common task execution patterns.

    This decorator:
    - Ensures Django setup
    - Logs task start and completion
    - Handles exceptions with proper error responses
    - Returns standardized task results

    Args:
        task_name: Name of the task for logging
    """

    def decorator(func):
        def wrapper(**kwargs):
            ensure_django_setup()
            log_task_execution(task_name, "start", f"Starting {task_name} task")

            try:
                result = func(**kwargs)
                log_task_execution(task_name, "complete", f"Task {task_name} completed successfully")
                return result
            except Exception as e:
                error_msg = f"{task_name.title()} task failed: {str(e)}"
                log_task_execution(task_name, "error", error_msg, level="error")
                return create_task_result("error", error=error_msg)

        return wrapper

    return decorator


def get_task_and_execution(task_id: int, execution_id: int | None) -> tuple[Any, Any]:
    """Get task and execution objects with proper locking."""
    from .models import Task, TaskExecution

    with transaction.atomic():
        task = Task.objects.select_for_update().get(id=task_id)
        execution = None

        if execution_id:
            execution = TaskExecution.objects.get(id=execution_id)

    return task, execution


def trigger_dependent_tasks(completed_task: Any) -> None:
    """
    Trigger tasks that depend on the completed task.

    Args:
        completed_task: The task that just completed
    """
    from .models import Task, TaskDependency

    try:
        # Find tasks that depend on this completed task
        dependent_task_ids = TaskDependency.objects.filter(
            prerequisite_task=completed_task, required_status=completed_task.status
        ).values_list("dependent_task_id", flat=True)

        # Check each dependent task to see if all its dependencies are satisfied
        for task_id in dependent_task_ids:
            try:
                task = Task.objects.get(id=task_id)
                if task.is_ready_to_run():
                    # Import here to avoid circular import
                    from .tasks import submit_task_to_dispatcher

                    submit_task_to_dispatcher(task)
                    logger.info(f"Triggered dependent task: {task.name} (ID: {task.id})")

            except Task.DoesNotExist:
                logger.warning(f"Dependent task {task_id} not found")
                continue

    except Exception as e:
        logger.error(f"Error triggering dependent tasks: {str(e)}")


def schedule_next_occurrence(task: Any) -> None:
    """
    Schedule the next occurrence of a recurring task.

    Args:
        task: The recurring task to schedule
    """
    from .models import Task

    try:
        if not task.cron_expression:
            logger.warning(f"Task {task.name} has no cron expression for recurring schedule")
            return

        # Create a new task instance for the next occurrence
        next_task = Task.objects.create(
            name=f"{task.name} (recurring)",
            function_name=task.function_name,
            task_data=task.task_data,
            cron_expression=task.cron_expression,
            is_recurring=True,
            priority=task.priority,
            max_attempts=task.max_attempts,
            timeout_seconds=task.timeout_seconds,
            created_by=task.created_by,
        )

        logger.info(f"Scheduled next occurrence: {next_task.name} (ID: {next_task.id})")

    except Exception as e:
        logger.error(f"Error scheduling next occurrence for task {task.name}: {str(e)}")


def handle_post_execution(task: Any) -> None:
    """Handle post-execution tasks like dependencies and recurring tasks."""
    if task.status == "completed":
        trigger_dependent_tasks(task)

    # For recurring tasks managed via cron scheduler, we don't need to create new instances
    # The cron scheduler will handle the recurring executions automatically
    # Only create next occurrences for one-time scheduled recurring tasks
    if task.is_recurring and task.status == "completed" and not task.cron_expression:
        schedule_next_occurrence(task)


def handle_task_error(
    task_instance: Any = None,
    execution_instance: Any = None,
    error_message: str = "",
    exception: Exception | None = None,
    task_id: int | None = None,
    execution_id: int | None = None,
) -> dict[str, Any]:
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
                # Refresh from database to get latest state
                task_instance.refresh_from_db()

                # Store previous status to determine if we need to increment attempts
                previous_status = task_instance.status

                task_instance.status = "failed"
                task_instance.error_message = error_message
                task_instance.completed_at = timezone.now()

                # Increment attempts if the task failed before reaching "running" status
                # This handles errors that occur during task initialization/validation
                # If the task reached "running" status, attempts was already incremented
                if previous_status in ["pending", "waiting_for_dependencies"]:
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


def update_task_status(
    task_instance: Any,
    execution_instance: Any = None,
    status: str = "",
    result_data: dict[str, Any] | None = None,
    error_message: str = "",
) -> None:
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

        # Store previous status before updating
        previous_status = task_instance.status

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
        elif status == "running" and previous_status != "running":
            # Only set started_at if this is the first time running (not a status update)
            task_instance.started_at = timezone.now()
            # Only increment attempts if this is a new execution attempt
            # (either first run or retry after failure)
            if previous_status in ["pending", "failed"]:
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


def get_or_create_execution_record(task_instance: Any, worker_id: str | None = None) -> Any:
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


def validate_task_data(data: dict[str, Any], required_fields: list[str] | None = None) -> str | None:
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


def create_task_result(status: str, data: dict[str, Any] | None = None, error: str = "") -> dict[str, Any]:
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


def get_related_object_safely(instance: Any, field_name: str, default: Any = None) -> Any:
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


def get_count_safely(queryset_or_manager: Any) -> int:
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
        count_result = queryset_or_manager.count()
        return int(count_result)
    except Exception as e:
        logger.warning(f"Error getting count: {e}")
        return 0


def build_error_response(message: str, details: dict[str, Any] | None = None, status_code: int = 400) -> dict[str, Any]:
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
