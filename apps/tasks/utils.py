"""
Utility functions for task management and execution.
"""

import logging
from datetime import UTC
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
        task = Task.objects.get(id=task_id)
        execution = None

        if execution_id:
            execution = TaskExecution.objects.get(id=execution_id)

    return task, execution


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
                if previous_status in ["pending"]:
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


# =============================================================================
# Dispatcherd Task Decorator
# =============================================================================

try:
    from dispatcherd.publish import task
except ImportError:

    def task():
        """Fallback task decorator when dispatcherd is not available."""

        def decorator(func):
            return func

        return decorator


# =============================================================================
# Database and Data Utilities
# =============================================================================


def parse_datetime_string(date_str: str | None) -> Any:
    """
    Parse an ISO datetime string, return None if invalid.

    Naive datetimes (without timezone info) are assumed to be UTC.

    Args:
        date_str: ISO format datetime string (supports 'Z' suffix)

    Returns:
        timezone-aware datetime object or None if invalid/empty
    """
    from datetime import datetime

    if not date_str:
        return None
    try:
        # Replace 'Z' with '+00:00' for ISO parsing
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

        # If naive datetime, make it timezone-aware (assume UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        return dt
    except (ValueError, AttributeError):
        return None


def get_db_connection(db_name: str = "awx"):
    """
    Get a raw database connection that supports PostgreSQL COPY commands.

    Django's CursorDebugWrapper doesn't support the COPY command, so we need
    to use the raw connection for metrics-utility collectors that use COPY
    for efficient data extraction.

    Args:
        db_name: Database name from Django settings (default: 'awx')

    Returns:
        Raw database connection object (psycopg2 connection)
    """
    from django.db import connections

    # Get the raw connection to bypass Django's cursor wrapper
    # This is necessary for PostgreSQL COPY commands used by metrics-utility
    django_connection = connections[db_name]

    # Ensure the connection is open
    django_connection.ensure_connection()

    # Return the raw psycopg2 connection
    return django_connection.connection


def generate_salt() -> str:
    """
    Generate a unique UUID4 salt for anonymization.

    Returns:
        str: UUID4 string
    """
    import uuid

    return str(uuid.uuid4())


# =============================================================================
# Segment.com Integration
# =============================================================================


def send_to_segment(user_id: str, event_name: str, segment_data: dict) -> str:
    """
    Send data to Segment.com using metrics-utility StorageSegment.

    Args:
        user_id: User ID for Segment tracking
        event_name: Event name for tracking
        segment_data: Dictionary of data to send

    Returns:
        str: "success" if sent, "segment_not_available" if Segment is not configured,
             or "error: <message>" if sending failed.
    """
    try:
        from metrics_utility.library.storage.segment import SEGMENT_AVAILABLE, StorageSegment
    except ImportError:
        logger.warning("metrics-utility segment integration not available")
        return "segment_not_available"

    if not SEGMENT_AVAILABLE or StorageSegment is None:
        return "segment_not_available"

    try:
        import json

        from django.conf import settings

        # Get Segment write key from settings
        write_key = getattr(settings, "SEGMENT_WRITE_KEY", None)
        if not write_key:
            logger.warning("SEGMENT_WRITE_KEY not configured in settings")
            return "segment_not_available"

        # Calculate data size for logging
        data_size = len(json.dumps(segment_data).encode("utf-8"))

        log_task_execution(
            "segment_send",
            "processing",
            f"Sending data to Segment.com using StorageSegment (Size: {data_size} bytes)",
        )

        # Initialize StorageSegment with configuration
        storage = StorageSegment(
            write_key=write_key,
            user_id=user_id,
            debug=getattr(settings, "DEBUG", False),
            use_bulk=data_size > 24 * 1024,  # Use bulk mode for large payloads
        )

        # Send data using StorageSegment.put()
        artifact_name = f"metrics_collection_{user_id}"
        chunks = storage.put(artifact_name=artifact_name, dict=segment_data, event_name=event_name)

        # Log success with chunk information
        chunk_count = len(chunks) if chunks else 1
        logger.info(f"Successfully sent metrics to Segment.com (Size: {data_size} bytes, Chunks: {chunk_count})")
        return "success"

    except Exception as e:
        logger.error(f"Error sending data to Segment.com: {str(e)}")
        return f"error: {str(e)}"


def _serialize_args(kwargs):
    if not kwargs:
        return {}

    params = {}

    for key, value in kwargs.items():
        # Convert datetime objects to ISO strings for database storage
        if hasattr(value, "isoformat"):
            params[key] = value.isoformat()
        else:
            params[key] = value

    return params


def generic_collect_metrics(
    collector_type: str,
    collector_registry: dict[str, dict[str, Any]],
    collection_mode: str,
    timestamp: Any,
    db_connection: Any,
    collector_kwargs: dict[str, Any] | None = None,
    task_execution_id: int | None = None,
) -> dict[str, Any]:
    """Generic metrics collection for hourly/snapshot collectors with optional rollup processing."""
    from apps.tasks.models import HourlyMetricsCollection

    if collector_type not in collector_registry:
        valid = ", ".join(sorted(collector_registry.keys()))
        raise ValueError(f"Unknown collector_type: {collector_type}. Valid types: {valid}")

    config = collector_registry[collector_type]
    log_task_execution(f"collect_{collector_type}", "processing", f"Collecting {collector_type} ({collection_mode})")

    # Build collection_params for audit trail from collector_kwargs
    collection_params = _serialize_args(collector_kwargs)

    # Get TaskExecution instance for linking if ID provided
    task_execution_instance = None
    if task_execution_id:
        try:
            from apps.tasks.models import TaskExecution

            task_execution_instance = TaskExecution.objects.get(id=task_execution_id)
        except Exception:
            # Task execution not found or deleted, continue without it
            logger.debug(f"TaskExecution {task_execution_id} not found, proceeding without link")

    try:
        # For snapshot collectors, filter out collection_time (audit-only param, not used by collector)
        actual_collector_kwargs = collector_kwargs.copy() if collector_kwargs else {}
        if collection_mode == "snapshot" and "collection_time" in actual_collector_kwargs:
            actual_collector_kwargs.pop("collection_time")

        collector = config["collector_func"](db=db_connection, **actual_collector_kwargs)
        raw_data = collector.gather()

        # Process rollup if processor provided, otherwise use raw data
        rollup_data = config["rollup_processor"]().prepare(raw_data) if config["rollup_processor"] else raw_data

        collection, created = HourlyMetricsCollection.objects.update_or_create(
            collector_type=collector_type,
            collection_timestamp=timestamp,
            defaults={
                "raw_data": rollup_data,
                "status": "collected",
                "error_message": "",
                "collection_parameters": collection_params,
                "task_execution": task_execution_instance,
            },
        )

        action = "Created" if created else "Updated"
        log_task_execution(f"collect_{collector_type}", "completed", f"{action} {collection_mode} ID: {collection.id}")

        return create_task_result(
            "success",
            {
                "message": f"{action} {collection_mode} collection for {collector_type}",
                "task_type": f"collect_{collector_type}",
                "collection_id": collection.id,
                "collector_type": collector_type,
                "timestamp": timestamp.isoformat(),
            },
        )

    except Exception as e:
        logger.exception(f"Failed to collect {collector_type} {collection_mode} metrics: {str(e)}")

        # Store failed collection for audit trail (critical for diagnosing missing rollup data)
        # Use contextlib.suppress to avoid secondary exception if database write fails
        import contextlib

        with contextlib.suppress(Exception):
            HourlyMetricsCollection.objects.update_or_create(
                collector_type=collector_type,
                collection_timestamp=timestamp,
                defaults={
                    "raw_data": {},
                    "status": "failed",
                    "error_message": str(e),
                    "collection_parameters": collection_params,
                    "task_execution": task_execution_instance,
                },
            )

        return create_task_result(
            "error",
            {"task_type": f"collect_{collector_type}", "collector_type": collector_type},
            error=f"Collection failed: {str(e)}",
        )
