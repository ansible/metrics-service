"""
System and maintenance background tasks for metrics_service.

This module provides system-level tasks including cleanup, maintenance,
communication, and testing tasks with proper error handling and status tracking.
"""

import logging
import os
import time
from typing import Any

from django.utils import timezone

from .utils import (
    create_task_result,
    ensure_django_setup,
    get_task_and_execution,
    handle_post_execution,
    handle_task_error,
    log_task_execution,
    task_execution_wrapper,
    update_task_status,
)

logger = logging.getLogger(__name__)

try:
    from dispatcherd.publish import task
except ImportError:

    def task():
        def decorator(func):
            return func

        return decorator


@task(queue="metrics_tasks", decorate=False)
@task_execution_wrapper("hello_world")
def hello_world(**kwargs) -> dict[str, Any]:
    """
    Simple hello world task for testing.

    This task prints "Hello World" and completes successfully.
    Used for testing the dispatcherd integration.

    Args:
        **kwargs: Any keyword arguments (ignored)

    Returns:
        dict: Task result dictionary with success status
    """
    # Simple task that just prints hello world
    message = "Hello World from dispatcherd!"
    logger.info(f"Task executing: {message}")

    return create_task_result(
        "success",
        {
            "message": message,
            "task_type": "hello_world",
            "completed": True,
        },
    )


@task(queue="metrics_tasks", decorate=False)
@task_execution_wrapper("sleep")
def sleep(duration: int = 10) -> dict[str, Any]:
    """
    Sleep for a given number of seconds.
    """
    time.sleep(duration)
    message = f"Slept for {duration} seconds"
    logger.info(f"Sleep task completed: {message}")

    return create_task_result(
        "success", {"message": message, "task_type": "sleep", "duration": duration, "completed": True}
    )


@task(queue="metrics_cleanup", decorate=False)
@task_execution_wrapper("cleanup_old_tasks")
def cleanup_old_tasks(**kwargs) -> dict[str, Any]:
    """
    Clean up old completed and failed tasks from the database.

    This task removes tasks that have been completed or failed for more than
    the specified number of days. This helps maintain database performance
    and prevents unlimited growth of task history.

    IMPORTANT: Recurring tasks are automatically preserved and will NOT be deleted,
    regardless of their age, to ensure scheduled tasks continue to function.

    Args:
        **kwargs: Task data containing cleanup parameters:
            - days_old (int): Number of days old tasks should be to qualify for cleanup (default: 5)
            - dry_run (bool): If True, only count tasks that would be deleted (default: False)
            - include_executions (bool): Also cleanup related TaskExecution records (default: True)
            - preserve_recurring (bool): If True, exclude recurring tasks from cleanup (default: True)

    Returns:
        dict: Task result dictionary with cleanup statistics
    """
    days_old = kwargs.get("days_old", 5)
    dry_run = kwargs.get("dry_run", False)
    include_executions = kwargs.get("include_executions", True)
    preserve_recurring = kwargs.get("preserve_recurring", True)

    log_task_execution("cleanup_old_tasks", "processing", f"Cleaning up tasks older than {days_old} days")

    from datetime import timedelta

    from .models import Task, TaskExecution

    # Calculate cutoff date
    cutoff_date = timezone.now() - timedelta(days=days_old)

    # Find tasks that are completed or failed and older than cutoff date
    # Use completed_at if available, otherwise fall back to modified date
    old_tasks_filter = {
        "status__in": ["completed", "failed"],
        "completed_at__lt": cutoff_date,
        "completed_at__isnull": False,
    }

    # Exclude recurring tasks if preserve_recurring is True (default)
    if preserve_recurring:
        old_tasks_filter["is_recurring"] = False

    old_tasks = Task.objects.filter(**old_tasks_filter)

    # Also include tasks that don't have completed_at but are old based on modified date
    old_tasks_fallback_filter = {
        "status__in": ["completed", "failed"],
        "completed_at__isnull": True,
        "modified__lt": cutoff_date,
    }

    # Exclude recurring tasks if preserve_recurring is True (default)
    if preserve_recurring:
        old_tasks_fallback_filter["is_recurring"] = False

    old_tasks_fallback = Task.objects.filter(**old_tasks_fallback_filter)

    # Combine querysets
    old_tasks = old_tasks | old_tasks_fallback

    task_count = old_tasks.count()
    execution_count = 0

    if include_executions:
        # Count related executions
        execution_count = TaskExecution.objects.filter(task__in=old_tasks).count()

    deleted_tasks = 0
    deleted_executions = 0

    if not dry_run and task_count > 0:
        log_task_execution("cleanup_old_tasks", "processing", f"Deleting {task_count} old tasks")

        if include_executions:
            # Delete executions first (foreign key constraint)
            deleted_executions, _ = TaskExecution.objects.filter(task__in=old_tasks).delete()
            deleted_executions = deleted_executions - task_count  # Subtract the task count to get just executions

        # Delete the tasks
        deleted_tasks, _ = old_tasks.delete()
        deleted_tasks = deleted_tasks - deleted_executions  # Get just the task count

        message = f"Deleted {deleted_tasks} tasks and {deleted_executions} executions"
        if preserve_recurring:
            message += " (recurring tasks preserved)"
        log_task_execution("cleanup_old_tasks", "completed", message)
    else:
        message = f"Found {task_count} tasks and {execution_count} executions that would be deleted"
        if preserve_recurring:
            message += " (recurring tasks preserved)"
        log_task_execution("cleanup_old_tasks", "completed", message)

    return create_task_result(
        "success",
        {
            "days_old": days_old,
            "cutoff_date": cutoff_date.isoformat(),
            "dry_run": dry_run,
            "include_executions": include_executions,
            "preserve_recurring": preserve_recurring,
            "tasks_found": task_count,
            "executions_found": execution_count,
            "tasks_deleted": deleted_tasks,
            "executions_deleted": deleted_executions,
        },
    )


@task(queue="metrics_cleanup", decorate=False)
@task_execution_wrapper("cleanup_old_data")
def cleanup_old_data(**kwargs) -> dict[str, Any]:
    """
    Clean up old data from the system.

    This task removes old data from the system based on specified age criteria.
    It supports cleanup of various data types including activity streams, logs,
    and other time-based data.

    Args:
        **kwargs: Task data containing cleanup parameters:
            - days_old (int): Number of days old data should be to qualify for cleanup (default: 30)
            - data_types (list): List of data types to clean up (optional)

    Returns:
        dict: Task result dictionary with cleanup statistics
    """
    days_old = kwargs.get("days_old", 30)
    data_types = kwargs.get("data_types", ["default"])
    cleaned_count = 0

    log_task_execution("cleanup_old_data", "processing", f"Cleaning up data older than {days_old} days")

    return create_task_result(
        "success",
        {
            "cleaned_count": cleaned_count,
            "days_old": days_old,
            "data_types": data_types,
        },
    )


@task(queue="metrics_notifications", decorate=False)
@task_execution_wrapper("send_notification_email")
def send_notification_email(**kwargs) -> dict[str, Any]:
    """
    Send notification email to users.

    This task sends notification emails to specified recipients using Django's
    email functionality. It supports various email parameters and handles
    email delivery errors gracefully.

    Args:
        **kwargs: Task data containing email parameters:
            - recipient (str): Email address of the recipient (required)
            - subject (str): Email subject line (default: "Notification")
            - message (str): Email message body
            - html_message (str): Optional HTML version of the message

    Returns:
        dict: Task result dictionary with email delivery status
    """
    recipient = kwargs.get("recipient")
    if not recipient:
        return create_task_result("error", error="Recipient is required")

    subject = kwargs.get("subject", "Notification")
    message = kwargs.get("message", "")

    log_task_execution("send_notification_email", "processing", f"Sending email to {recipient}")

    # Add your actual email sending logic here
    # For example: using Django's send_mail
    # from django.core.mail import send_mail
    # from django.conf import settings
    #
    # send_mail(
    #     subject=subject,
    #     message=message,
    #     from_email=settings.DEFAULT_FROM_EMAIL,
    #     recipient_list=[recipient],
    #     html_message=html_message,
    # )

    return create_task_result(
        "success",
        {
            "recipient": recipient,
            "subject": subject,
            "message_length": len(message),
        },
    )


@task(queue="metrics_tasks", decorate=False)
@task_execution_wrapper("process_user_data")
def process_user_data(**kwargs) -> dict[str, Any]:
    """
    Process user data in the background.

    Args:
        **kwargs: Task data containing user processing parameters

    Returns:
        Task result dictionary
    """
    user_id = kwargs.get("user_id")
    operation = kwargs.get("operation", "sync")

    from django.contrib.auth import get_user_model

    # Handle hello_world operation without requiring user_id
    if operation == "hello_world":
        message = kwargs.get("message", "Hello World from dispatcherd!")
        logger.info(f"Hello World Task: {message}")

        return {
            "status": "success",
            "message": message,
            "task_type": "hello_world",
            "completed": True,
            "timestamp": str(timezone.now()),
            "operation": operation,
        }

    # For other operations, require user_id
    if not user_id:
        return {
            "status": "error",
            "error": "user_id is required for this operation",
        }

    user_agent = get_user_model()
    user = user_agent.objects.get(id=user_id)
    logger.info(f"Processing user: {user.username}")

    if operation == "sync":
        # Example: Sync user data with external systems
        logger.info(f"Syncing user {user.username} with external systems")

    elif operation == "validate":
        # Example: Validate user data
        logger.info(f"Validating user {user.username} data")

    logger.info(f"User processing completed for {user.username}")

    return {
        "status": "success",
        "user_id": user_id,
        "username": user.username,
        "operation": operation,
    }


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

        # Handle post-execution tasks
        handle_post_execution(task)

        # For recurring tasks, reset status to pending for next execution
        if task.is_recurring:
            task.status = "pending"
            task.save()
            logger.info(f"Reset recurring task {task.name} (ID: {task.id}) status to pending for next execution")

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


# System-defined tasks are now sourced from task groups and stored in database
# Database is the source of truth for all tasks including recurring ones
SYSTEM_TASKS = []


def create_system_tasks() -> dict[str, Any]:
    """
    Create or update system-defined tasks from task groups in the database.

    This function syncs task group definitions to the tasks_task table,
    making the database the source of truth for all tasks.

    Returns:
        dict: Summary of tasks created, updated, and skipped
    """
    try:
        from .models import Task
        from .task_groups import get_all_enabled_tasks
    except ImportError:
        # Handle case where Django isn't fully set up yet
        return {"error": "Django not ready", "created": 0, "updated": 0, "skipped": 0}

    results = {"created": 0, "updated": 0, "skipped": 0, "tasks": []}

    # Get all task group definitions
    task_groups = get_all_enabled_tasks()

    for task_id, config in task_groups.items():
        try:
            _sync_task_group_to_database(task_id, config, results, Task)
        except Exception as e:
            results["tasks"].append(f"Error with {task_id}: {str(e)}")
            logger.error(f"Failed to sync task {task_id}: {e}")

    return results


def _sync_task_group_to_database(task_id: str, config: dict[str, Any], results: dict[str, Any], task_model) -> None:
    """
    Sync a single task group definition to the database.

    Args:
        task_id: Unique identifier for the task
        config: Task configuration from task groups
        results: Results dict to update
        task_model: Task model class
    """
    # Check if task already exists (by name and function)
    existing_task = task_model.objects.filter(
        name=task_id,
        function_name=config["function"],
        is_system_task=True
    ).first()

    # Prepare task data including feature flag for runtime checking
    task_data = config.get("args", {}).copy()
    if config.get("feature_flag"):
        task_data["_feature_flag"] = config["feature_flag"]

    if existing_task:
        _update_existing_task_from_group(existing_task, config, task_data, results)
    else:
        _create_new_task_from_group(task_id, config, task_data, results, task_model)


def _update_existing_task_from_group(existing_task, config: dict[str, Any], task_data: dict[str, Any], results: dict[str, Any]) -> None:
    """Update an existing system task from task group definition."""
    updated = False

    # Check each field for changes
    fields_to_check = [
        ("task_data", task_data),
        ("cron_expression", config.get("cron")),
        ("priority", config.get("priority", 5)),
        ("description", config.get("description", "")),
    ]

    for field, new_value in fields_to_check:
        if getattr(existing_task, field) != new_value:
            setattr(existing_task, field, new_value)
            updated = True

    if updated:
        existing_task.save()
        results["updated"] += 1
        results["tasks"].append(f"Updated: {existing_task.name}")
    else:
        results["skipped"] += 1
        results["tasks"].append(f"Skipped: {existing_task.name} (no changes)")


def _create_new_task_from_group(task_id: str, config: dict[str, Any], task_data: dict[str, Any], results: dict[str, Any], task_model) -> None:
    """Create a new system task from task group definition."""
    new_task = task_model.objects.create(
        name=task_id,
        description=config.get("description", ""),
        function_name=config["function"],
        task_data=task_data,
        cron_expression=config.get("cron"),
        is_recurring=True,  # All task group tasks are recurring
        priority=config.get("priority", 5),
        is_system_task=True,
        status="pending",
    )
    results["created"] += 1
    results["tasks"].append(f"Created: {new_task.name}")


def create_system_tasks_legacy() -> dict[str, Any]:
    """
    Create or update system-defined tasks on startup.

    This function ensures that essential system tasks like cleanup and metrics
    collection are always present and properly configured. It creates new tasks
    or updates existing ones based on the SYSTEM_TASKS configuration.

    Returns:
        dict: Summary of tasks created, updated, and skipped
    """
    try:
        from .models import Task
    except ImportError:
        # Handle case where Django isn't fully set up yet
        return {"error": "Django not ready", "created": 0, "updated": 0, "skipped": 0}

    results = {"created": 0, "updated": 0, "skipped": 0, "tasks": []}

    for system_task_config in SYSTEM_TASKS:
        if not system_task_config.get("is_enabled", True):
            results["skipped"] += 1
            continue

        try:
            _process_system_task(system_task_config, results, Task)
        except Exception as e:
            results["tasks"].append(f"Error with {system_task_config['name']}: {str(e)}")

    return results


def _process_system_task(system_task_config: dict[str, Any], results: dict[str, Any], task_model) -> None:
    """Process a single system task configuration."""
    existing_task = task_model.objects.filter(
        name=system_task_config["name"], function_name=system_task_config["function_name"], is_system_task=True
    ).first()

    if existing_task:
        _update_existing_system_task(existing_task, system_task_config, results)
    else:
        _create_new_system_task(system_task_config, results, task_model)


def _update_existing_system_task(existing_task, system_task_config: dict[str, Any], results: dict[str, Any]) -> None:
    """Update an existing system task if configuration has changed."""
    updated = False

    # Check each field for changes
    for field, config_key in [
        ("task_data", "task_data"),
        ("cron_expression", "cron_expression"),
        ("priority", "priority"),
        ("description", "description"),
    ]:
        if getattr(existing_task, field) != system_task_config[config_key]:
            setattr(existing_task, field, system_task_config[config_key])
            updated = True

    if updated:
        existing_task.save()
        results["updated"] += 1
        results["tasks"].append(f"Updated: {existing_task.name}")
    else:
        results["skipped"] += 1
        results["tasks"].append(f"Skipped: {existing_task.name} (no changes)")


def _create_new_system_task(system_task_config: dict[str, Any], results: dict[str, Any], task_model) -> None:
    """Create a new system task."""
    new_task = task_model.objects.create(
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
        return {"error": "Django not ready", "system_tasks": []}

    system_tasks = Task.objects.filter(is_system_task=True).order_by("name")

    task_info = []
    for task in system_tasks:
        info = {
            "id": task.id,
            "name": task.name,
            "function_name": task.function_name,
            "description": task.description,
            "status": task.status,
            "is_recurring": task.is_recurring,
            "cron_expression": task.cron_expression,
            "priority": task.priority,
            "created": task.created.isoformat() if task.created else None,
            "last_run": task.completed_at.isoformat() if task.completed_at else None,
            "category": next((config["category"] for config in SYSTEM_TASKS if config["name"] == task.name), "unknown"),
        }
        task_info.append(info)

    return {
        "system_tasks": task_info,
        "total_count": len(task_info),
        "categories": list({task["category"] for task in task_info}),
    }


@task(queue="metrics_cleanup", decorate=False)
@task_execution_wrapper("cleanup_metrics_data")
def cleanup_metrics_data(**kwargs) -> dict[str, Any]:
    """
    Clean up old metrics data based on retention policies.

    Retention policies:
    - Hourly collections: 7 days
    - Daily summaries: 30 days
    - Anonymized payloads: 30 days (or 7 days after sent)

    Args:
        **kwargs: Task data containing:
            - hourly_retention_days (int): Days to keep hourly data (default: 7)
            - daily_retention_days (int): Days to keep daily summaries (default: 30)
            - payload_retention_days (int): Days to keep sent payloads (default: 7)
            - dry_run (bool): If true, only count without deleting (default: False)

    Returns:
        dict: Task result with cleanup statistics
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary, HourlyMetricsCollection

    hourly_retention_days = kwargs.get("hourly_retention_days", 7)
    daily_retention_days = kwargs.get("daily_retention_days", 30)
    payload_retention_days = kwargs.get("payload_retention_days", 7)
    dry_run = kwargs.get("dry_run", False)

    log_task_execution("cleanup_metrics_data", "processing", f"Cleaning up metrics data (dry_run={dry_run})")

    results = {
        "hourly_collections": {"found": 0, "deleted": 0},
        "daily_summaries": {"found": 0, "deleted": 0},
        "anonymized_payloads": {"found": 0, "deleted": 0},
    }

    try:
        now = timezone.now()

        # Cleanup hourly collections older than retention period
        hourly_cutoff = now - timedelta(days=hourly_retention_days)
        old_hourly = HourlyMetricsCollection.objects.filter(collection_timestamp__lt=hourly_cutoff)
        results["hourly_collections"]["found"] = old_hourly.count()

        if not dry_run and results["hourly_collections"]["found"] > 0:
            deleted_count, _ = old_hourly.delete()
            results["hourly_collections"]["deleted"] = deleted_count

        # Cleanup daily summaries older than retention period
        daily_cutoff_date = now.date() - timedelta(days=daily_retention_days)
        old_daily = DailyMetricsSummary.objects.filter(summary_date__lt=daily_cutoff_date)
        results["daily_summaries"]["found"] = old_daily.count()

        if not dry_run and results["daily_summaries"]["found"] > 0:
            deleted_count, _ = old_daily.delete()
            results["daily_summaries"]["deleted"] = deleted_count

        # Cleanup sent payloads older than retention period
        # Keep unsent/failed payloads longer (30 days) for retry/debugging
        sent_payload_cutoff = now - timedelta(days=payload_retention_days)
        unsent_payload_cutoff = now - timedelta(days=30)

        old_sent_payloads = AnonymizedMetricsPayload.objects.filter(status="sent", sent_at__lt=sent_payload_cutoff)
        old_unsent_payloads = AnonymizedMetricsPayload.objects.filter(
            status__in=["failed"], created__lt=unsent_payload_cutoff
        )

        total_old_payloads = old_sent_payloads.count() + old_unsent_payloads.count()
        results["anonymized_payloads"]["found"] = total_old_payloads

        if not dry_run and total_old_payloads > 0:
            sent_deleted, _ = old_sent_payloads.delete()
            unsent_deleted, _ = old_unsent_payloads.delete()
            results["anonymized_payloads"]["deleted"] = sent_deleted + unsent_deleted

        log_task_execution("cleanup_metrics_data", "completed", f"Cleanup complete: {results}")

        return create_task_result(
            "success",
            {
                "task_type": "cleanup_metrics_data",
                "dry_run": dry_run,
                "retention_policies": {
                    "hourly_days": hourly_retention_days,
                    "daily_days": daily_retention_days,
                    "payload_days": payload_retention_days,
                },
                "results": results,
            },
        )

    except Exception as e:
        logger.error(f"Error in cleanup_metrics_data: {str(e)}")
        return create_task_result("error", error=f"Cleanup failed: {str(e)}")
