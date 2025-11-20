"""
Background tasks for metrics_service using dispatcherd.

This module provides task functions and utilities for executing background
tasks with proper error handling, status tracking, and dependency management.
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

# Constants for repeated strings
MSG_METRICS_UTILITY_NOT_AVAILABLE = "metrics-utility is not available"
LABEL_METRICS_COLLECTION = "Metrics Collection"
LABEL_DB_CONNECTION = "Database name from Django settings (default: 'awx')"
LABEL_START_DATE = "Start date for collection (ISO format)"
LABEL_END_DATE = "End date for collection (ISO format)"
EXAMPLE_START_DATE = "2024-01-01T00:00:00Z"

# Import metrics-utility collectors
try:
    # TODO The AS is just a filler till this is corrected with a later PR
    from metrics_utility.library.anonymize.anonymized_rollups_processor import (
        anonymized_rollups_processor,
    )
    from metrics_utility.library.collectors.controller import (
        config,
    )
    from metrics_utility.library.collectors.controller import job_host_summary as anonymous
    from metrics_utility.library.collectors.controller import main_host as job_host_summary
    from metrics_utility.library.collectors.controller import main_jobevent as host_metric

    METRICS_UTILITY_AVAILABLE = True
except ImportError as e:
    logger.warning(f"metrics-utility not available: {e}")
    METRICS_UTILITY_AVAILABLE = False

try:
    from dispatcherd.publish import task
except ImportError:

    def task():
        def decorator(func):
            return func

        return decorator


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_anonymous_metrics")
def collect_anonymous_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect anonymous metrics using metrics-utility library.

    This task uses the anonymous collector from metrics-utility to gather
    anonymous system metrics without exposing sensitive information.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)
            - custom_params (dict): Additional custom parameters (optional)

    Returns:
        dict: Task result with collected metrics data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_anonymous_metrics", "processing", "Collecting anonymous metrics")

    try:
        # Get parameters from kwargs
        from django.db import connections

        db_name = kwargs.get("database", "awx")
        since = kwargs.get("since")
        until = kwargs.get("until")
        custom_params = kwargs.get("custom_params")

        # Create collector instance
        db_connection = connections[db_name]
        collector = anonymous(db=db_connection, since=since, until=until, custom_params=custom_params)

        # Gather data
        metrics_data = collector.gather()

        return create_task_result(
            "success",
            {
                "task_type": "collect_anonymous_metrics",
                "metrics_data": metrics_data,
                "collector_type": "anonymous",
                "parameters_used": {
                    "database": db_name,
                    "since": since,
                    "until": until,
                    "custom_params": custom_params,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_anonymous_metrics: {str(e)}")
        return create_task_result("error", error=f"Collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_config_metrics")
def collect_config_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect configuration metrics using metrics-utility library.

    This task uses the config collector from metrics-utility to gather
    system configuration information from the AWX database.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')

    Returns:
        dict: Task result with collected configuration data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_config_metrics", "processing", "Collecting configuration metrics")

    try:
        from django.db import connections

        # Get db name from kwargs, default to 'awx' (defined in defaults.py)
        db_name = kwargs.get("database", "awx")

        # Get the Django db connection for the AWX database
        db_connection = connections[db_name]

        # Create collector instance with Django database connection
        collector = config(db=db_connection)

        config_data = collector.gather()

        return create_task_result(
            "success",
            {
                "task_type": "collect_config_metrics",
                "config_data": config_data,
                "collector_type": "config",
                "parameters_used": {"database": db_name},
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_config_metrics: {str(e)}")
        return create_task_result("error", error=f"Collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_job_host_summary")
def collect_job_host_summary(**kwargs) -> dict[str, Any]:
    """
    Collect job host summary metrics using metrics-utility library.

    This task uses the job_host_summary collector from metrics-utility to gather
    job execution statistics and host performance data.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)

    Returns:
        dict: Task result with collected job host summary data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_job_host_summary", "processing", "Collecting job host summary metrics")

    try:
        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        since = kwargs.get("since")
        until = kwargs.get("until")

        db_connection = connections[db_name]
        # Create collector instance
        collector = job_host_summary(db=db_connection, since=since, until=until)

        # Gather data
        summary_data = collector.gather()

        return create_task_result(
            "success",
            {
                "task_type": "collect_job_host_summary",
                "summary_data": summary_data,
                "collector_type": "job_host_summary",
                "parameters_used": {"database": db_name, "since": since, "until": until},
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_job_host_summary: {str(e)}")
        return create_task_result("error", error=f"Collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_host_metrics")
def collect_host_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect host metrics using metrics-utility library.

    This task uses the host_metric collector from metrics-utility to gather
    host performance and system metrics.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)

    Returns:
        dict: Task result with collected host metrics data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_host_metrics", "processing", "Collecting host metrics")

    try:
        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        since = kwargs.get("since")

        db_connection = connections[db_name]
        # Create collector instance
        collector = host_metric(db=db_connection, since=since)

        # Gather data
        host_data = collector.gather()

        return create_task_result(
            "success",
            {
                "task_type": "collect_host_metrics",
                "host_data": host_data,
                "collector_type": "host_metric",
                "parameters_used": {"database": db_name, "since": since},
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_host_metrics: {str(e)}")
        return create_task_result("error", error=f"Collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_all_metrics")
def collect_all_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect all available metrics using multiple collectors.

    This task runs multiple collectors in sequence to gather comprehensive
    metrics data from the system.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)
            - collectors (list): List of specific collectors to run (optional)

    Returns:
        dict: Task result with all collected metrics data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_all_metrics", "processing", "Collecting all metrics")

    try:
        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        db_connection = connections[db_name]
        since = kwargs.get("since")
        until = kwargs.get("until")
        collectors_list = kwargs.get("collectors", ["anonymous", "config", "host_metric"])

        all_results = {}

        # Run each requested collector
        for collector_name in collectors_list:
            try:
                if collector_name == "anonymous":
                    collector_instance = anonymous(db=db_connection, since=since, until=until)
                elif collector_name == "config":
                    collector_instance = config(db=db_connection)
                elif collector_name == "job_host_summary":
                    collector_instance = job_host_summary(db=db_connection, since=since, until=until)
                elif collector_name == "host_metric":
                    collector_instance = host_metric(db=db_connection, since=since)
                else:
                    logger.warning(f"Unknown collector: {collector_name}")
                    continue

                # Gather data from this collector
                collector_data = collector_instance.gather()
                all_results[collector_name] = collector_data

            except Exception as e:
                logger.error(f"Error running collector {collector_name}: {str(e)}")
                all_results[collector_name] = {"error": str(e)}

        return create_task_result(
            "success",
            {
                "task_type": "collect_all_metrics",
                "all_results": all_results,
                "collectors_run": collectors_list,
                "parameters_used": {"database": db_name, "since": since, "until": until},
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_all_metrics: {str(e)}")
        return create_task_result("error", error=f"Collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("anonymize_collected_data")
def anonymize_collected_data(**kwargs) -> dict[str, Any]:
    """
    Anonymize collected data using metrics-utility library.

    Anonymization process collects data from the controller DB, processes it through anonymized
    rollups, and returns anonymized JSON data.

    Args:
        **kwargs: Task data containing anonymization parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - salt (str): Salt string for hashing sensitive data (required)
            - since (str): Start date for data collection (ISO format, optional)
            - until (str): End date for data collection (ISO format, optional)
            - ship_path (str): Base path for saving rollup files (optional, defaults to MEDIA_ROOT)
            - save_rollups (bool): Whether to save rollup files to disk (default: True)

    Returns:
        dict: Task result with anonymized data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("anonymize_collected_data", "processing", "Anonymizing collected data")

    try:
        from datetime import datetime

        from django.conf import settings
        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        salt = kwargs.get("salt")
        since = kwargs.get("since")
        until = kwargs.get("until")
        ship_path = kwargs.get("ship_path")
        save_rollups = kwargs.get("save_rollups", True)

        # Validate required parameters
        if not salt:
            return create_task_result("error", error="salt parameter is required for anonymization")

        # Convert string dates to datetime objects if provided as strings
        if since and isinstance(since, str):
            try:
                since = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                return create_task_result("error", error=f"Invalid date format for 'since': {since}")

        if until and isinstance(until, str):
            try:
                until = datetime.fromisoformat(until.replace("Z", "+00:00"))
            except ValueError:
                return create_task_result("error", error=f"Invalid date format for 'until': {until}")

        # Get the Django db connection
        db_connection = connections[db_name]

        # Default ship_path to MEDIA_ROOT if not provided
        if not ship_path:
            ship_path = str(settings.MEDIA_ROOT)

        # Call the anonymization processor
        anonymized_data = anonymized_rollups_processor(
            db=db_connection,
            salt=salt,
            since=since,
            until=until,
            ship_path=ship_path,
            save_rollups=save_rollups,
        )

        return create_task_result(
            "success",
            {
                "task_type": "anonymize_collected_data",
                "anonymized_data": anonymized_data,
                "parameters_used": {
                    "database": db_name,
                    "salt": "******" if salt else None,
                    "since": since.isoformat() if since else None,
                    "until": until.isoformat() if until else None,
                    "ship_path": ship_path,
                    "save_rollups": save_rollups,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in anonymize_collected_data: {str(e)}")
        return create_task_result("error", error=f"Anonymization failed: {str(e)}")


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

    return create_task_result(
        "success",
        {
            "message": message,
            "task_type": "sleep",
            "duration": duration,
            "completed": True,
        },
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


# DEPRECATED: TaskScheduler class removed
# Functionality moved to SimpleTaskScheduler in simple_scheduler.py


# Task configuration for dispatcherd
TASK_FUNCTIONS = {
    "hello_world": hello_world,
    "cleanup_old_data": cleanup_old_data,
    "cleanup_old_tasks": cleanup_old_tasks,
    "send_notification_email": send_notification_email,
    "process_user_data": process_user_data,
    "execute_db_task": execute_db_task,
    "sleep": sleep,
    "collect_anonymous_metrics": collect_anonymous_metrics,
    "collect_config_metrics": collect_config_metrics,
    "collect_job_host_summary": collect_job_host_summary,
    "collect_host_metrics": collect_host_metrics,
    "collect_all_metrics": collect_all_metrics,
    "anonymize_collected_data": anonymize_collected_data,
}

# Enhanced task metadata for dashboard display
TASK_METADATA = {
    "hello_world": {
        "category": "Testing",
        "description": "Simple hello world task for testing the dispatcherd integration",
        "parameters": {},
        "examples": [{"name": "Basic Hello World", "data": {}}],
    },
    "sleep": {
        "category": "Testing",
        "description": "Sleep for a specified number of seconds (useful for testing)",
        "parameters": {
            "duration": {
                "type": "integer",
                "default": 10,
                "description": "Number of seconds to sleep",
                "min": 1,
                "max": 300,
            }
        },
        "examples": [
            {"name": "Sleep 10 seconds", "data": {"duration": 10}},
            {"name": "Sleep 30 seconds", "data": {"duration": 30}},
        ],
    },
    "cleanup_old_data": {
        "category": "Maintenance",
        "description": "Clean up old data from the system based on age criteria",
        "parameters": {
            "days_old": {
                "type": "integer",
                "default": 30,
                "description": "Number of days old data should be to qualify for cleanup",
                "min": 1,
                "max": 365,
            },
            "data_types": {
                "type": "array",
                "default": ["default"],
                "description": "List of data types to clean up",
                "items": ["logs", "temp_files", "cache", "default"],
            },
        },
        "examples": [
            {"name": "Cleanup 30 day old data", "data": {"days_old": 30}},
            {"name": "Cleanup logs older than 7 days", "data": {"days_old": 7, "data_types": ["logs"]}},
        ],
    },
    "cleanup_old_tasks": {
        "category": "Maintenance",
        "description": "Clean up old completed and failed tasks (preserves recurring tasks by default)",
        "parameters": {
            "days_old": {
                "type": "integer",
                "default": 5,
                "description": "Number of days old tasks should be to qualify for cleanup",
                "min": 1,
                "max": 365,
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "If true, only count tasks that would be deleted without actually deleting",
            },
            "include_executions": {
                "type": "boolean",
                "default": True,
                "description": "Also cleanup related TaskExecution records",
            },
            "preserve_recurring": {
                "type": "boolean",
                "default": True,
                "description": "If true, exclude recurring tasks from cleanup (recommended)",
            },
        },
        "examples": [
            {"name": "Standard cleanup (5 days)", "data": {"days_old": 5}},
            {"name": "Test cleanup (dry run)", "data": {"days_old": 7, "dry_run": True}},
            {"name": "Conservative cleanup", "data": {"days_old": 10, "include_executions": False}},
        ],
    },
    "send_notification_email": {
        "category": "Communication",
        "description": "Send notification email to specified recipients",
        "parameters": {
            "recipient": {
                "type": "string",
                "required": True,
                "description": "Email address of the recipient",
                "pattern": "email",
            },
            "subject": {"type": "string", "default": "Notification", "description": "Email subject line"},
            "message": {"type": "string", "default": "", "description": "Email message body"},
            "html_message": {"type": "string", "description": "Optional HTML version of the message"},
        },
        "examples": [
            {
                "name": "Basic notification",
                "data": {
                    "recipient": "admin@example.com",
                    "subject": "System Alert",
                    "message": "System maintenance completed",
                },
            },
            {
                "name": "Custom message",
                "data": {"recipient": "user@example.com", "subject": "Welcome", "message": "Welcome to our service!"},
            },
        ],
    },
    "process_user_data": {
        "category": "Data Processing",
        "description": "Process user data in the background with various operations",
        "parameters": {
            "user_id": {"type": "integer", "description": "ID of the user to process (required for most operations)"},
            "operation": {
                "type": "string",
                "default": "sync",
                "description": "Type of operation to perform",
                "choices": ["sync", "validate", "hello_world"],
            },
            "message": {"type": "string", "description": "Custom message for hello_world operation"},
        },
        "examples": [
            {"name": "Hello World", "data": {"operation": "hello_world", "message": "Hello from the system!"}},
            {"name": "Sync user data", "data": {"user_id": 1, "operation": "sync"}},
            {"name": "Validate user", "data": {"user_id": 1, "operation": "validate"}},
        ],
    },
    "execute_db_task": {
        "category": "System",
        "description": "Execute a database-defined task with comprehensive lifecycle management",
        "parameters": {
            "task_id": {"type": "integer", "required": True, "description": "ID of the task to execute"},
            "execution_id": {"type": "integer", "description": "ID of the execution record (optional)"},
        },
        "examples": [{"name": "Execute task by ID", "data": {"task_id": 123}}],
    },
    "collect_anonymous_metrics": {
        "category": LABEL_METRICS_COLLECTION,
        "description": "Collect anonymous system metrics without exposing sensitive information",
        "parameters": {
            "db": {"type": "string", "description": LABEL_DB_CONNECTION},
            "since": {"type": "string", "description": LABEL_START_DATE, "pattern": "datetime"},
            "until": {"type": "string", "description": LABEL_END_DATE, "pattern": "datetime"},
            "custom_params": {"type": "object", "description": "Additional custom parameters for collection"},
        },
        "examples": [
            {"name": "Basic anonymous collection", "data": {}},
            {
                "name": "Date range collection",
                "data": {"since": EXAMPLE_START_DATE, "until": "2024-01-02T00:00:00Z"},
            },
        ],
    },
    "collect_config_metrics": {
        "category": LABEL_METRICS_COLLECTION,
        "description": "Collect system configuration information and metadata",
        "parameters": {"db": {"type": "string", "description": "Database name from Django settings (default: 'awx')"}},
        "examples": [{"name": "Collect configuration", "data": {}}],
    },
    "collect_job_host_summary": {
        "category": LABEL_METRICS_COLLECTION,
        "description": "Collect job execution statistics and host performance data",
        "parameters": {
            "db": {"type": "string", "description": LABEL_DB_CONNECTION},
            "since": {"type": "string", "description": LABEL_START_DATE, "pattern": "datetime"},
            "until": {"type": "string", "description": LABEL_END_DATE, "pattern": "datetime"},
        },
        "examples": [
            {"name": "Current job summary", "data": {}},
            {"name": "Weekly job summary", "data": {"since": EXAMPLE_START_DATE, "until": "2024-01-08T00:00:00Z"}},
        ],
    },
    "collect_host_metrics": {
        "category": LABEL_METRICS_COLLECTION,
        "description": "Collect host performance and system metrics",
        "parameters": {
            "db": {"type": "string", "description": LABEL_DB_CONNECTION},
            "since": {"type": "string", "description": LABEL_START_DATE, "pattern": "datetime"},
        },
        "examples": [
            {"name": "Current host metrics", "data": {}},
            {"name": "Historical host metrics", "data": {"since": EXAMPLE_START_DATE}},
        ],
    },
    "collect_all_metrics": {
        "category": LABEL_METRICS_COLLECTION,
        "description": "Run multiple collectors in sequence to gather comprehensive metrics",
        "parameters": {
            "database": {"type": "string", "description": LABEL_DB_CONNECTION},
            "since": {"type": "string", "description": LABEL_START_DATE, "pattern": "datetime"},
            "until": {"type": "string", "description": LABEL_END_DATE, "pattern": "datetime"},
            "collectors": {
                "type": "array",
                "default": ["anonymous", "config", "host_metric"],
                "description": "List of specific collectors to run",
                "items": ["anonymous", "config", "job_host_summary", "host_metric"],
            },
        },
        "examples": [
            {"name": "All default collectors", "data": {}},
            {"name": "Specific collectors", "data": {"collectors": ["anonymous", "config"]}},
            {
                "name": "Full metrics with date range",
                "data": {
                    "since": EXAMPLE_START_DATE,
                    "until": "2024-01-02T00:00:00Z",
                    "collectors": ["anonymous", "config", "host_metric"],
                },
            },
        ],
    },
    "anonymize_collected_data": {
        "category": LABEL_METRICS_COLLECTION,
        "description": "Anonymize collected data from Controller DB using metrics-utility anonymization feature",
        "parameters": {
            "database": {"type": "string", "description": LABEL_DB_CONNECTION},
            "salt": {
                "type": "string",
                "required": True,
                "description": "Salt string for hashing sensitive data (required for anonymization)",
            },
            "since": {"type": "string", "description": LABEL_START_DATE, "pattern": "datetime"},
            "until": {"type": "string", "description": LABEL_END_DATE, "pattern": "datetime"},
            "ship_path": {
                "type": "string",
                "description": "Base path for saving rollup files (defaults to MEDIA_ROOT)",
            },
            "save_rollups": {
                "type": "boolean",
                "default": True,
                "description": "Whether to save rollup files to disk",
            },
        },
        "examples": [
            {
                "name": "Basic anonymization",
                "data": {"salt": "my-secret-salt-value"},
            },
            {
                "name": "Anonymize with date range",
                "data": {
                    "salt": "my-secret-salt-value",
                    "since": EXAMPLE_START_DATE,
                    "until": "2024-01-02T00:00:00Z",
                },
            },
            {
                "name": "Anonymize without saving rollups",
                "data": {"salt": "my-secret-salt-value", "save_rollups": False},
            },
        ],
    },
}

# System-defined tasks are now handled by APScheduler cron scheduler only
# Database-backed recurring tasks are disabled to avoid double scheduling
# All recurring tasks are managed in apps/tasks/cron_scheduler.py
SYSTEM_TASKS = [
    # Database-backed system tasks disabled - use APScheduler instead
    # See apps/tasks/cron_scheduler.py for all recurring task definitions
]


def create_system_tasks() -> dict[str, Any]:
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
