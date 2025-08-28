"""
Background tasks for metrics_service using dispatcherd.

This module provides task functions and utilities for executing background
tasks with proper error handling, status tracking, and dependency management.
"""

import logging
import os
import time
from typing import Any

from django.db import transaction
from django.utils import timezone

from .utils import (
    create_task_result,
    handle_task_error,
    log_task_execution,
    update_task_status,
    validate_task_data,
)

logger = logging.getLogger(__name__)


def cleanup_old_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    Clean up old data from the system.

    This task removes old data from the system based on specified age criteria.
    It supports cleanup of various data types including activity streams, logs,
    and other time-based data.

    Args:
        data (dict): Task data containing cleanup parameters:
            - days_old (int): Number of days old data should be to qualify for cleanup (default: 30)
            - data_types (list): List of data types to clean up (optional)

    Returns:
        dict: Task result dictionary with cleanup statistics
    """
    log_task_execution("cleanup_old_data", "start", "Starting data cleanup process")

    # Validate input data
    validation_error = validate_task_data(data, required_fields=[])
    if validation_error:
        return create_task_result("error", error=validation_error)

    days_old = data.get("days_old", 30)
    data_types = data.get("data_types", ["default"])

    cleaned_count = 0

    try:
        log_task_execution("cleanup_old_data", "processing", f"Cleaning up data older than {days_old} days")

        # Add your actual cleanup logic here
        # For example: delete old activity stream entries, logs, etc.

        # Example cleanup implementations:
        # from datetime import timedelta
        # cutoff_date = timezone.now() - timedelta(days=days_old)

        # if "activity_stream" in data_types:
        #     ActivityStream.objects.filter(timestamp__lt=cutoff_date).delete()
        #
        # if "task_executions" in data_types:
        #     TaskExecution.objects.filter(completed_at__lt=cutoff_date).delete()

        log_task_execution("cleanup_old_data", "complete", f"Cleaned {cleaned_count} items")

        return create_task_result(
            "success",
            {
                "cleaned_count": cleaned_count,
                "days_old": days_old,
                "data_types": data_types,
            },
        )

    except Exception as e:
        error_msg = f"Cleanup failed: {str(e)}"
        log_task_execution("cleanup_old_data", "error", error_msg, level="error")
        return create_task_result("error", error=error_msg)


def send_notification_email(data: dict[str, Any]) -> dict[str, Any]:
    """
    Send notification email to users.

    This task sends notification emails to specified recipients using Django's
    email functionality. It supports various email parameters and handles
    email delivery errors gracefully.

    Args:
        data (dict): Task data containing email parameters:
            - recipient (str): Email address of the recipient (required)
            - subject (str): Email subject line (default: "Notification")
            - message (str): Email message body
            - html_message (str): Optional HTML version of the message

    Returns:
        dict: Task result dictionary with email delivery status
    """
    log_task_execution("send_notification_email", "start", "Preparing to send notification email")

    # Validate input data
    validation_error = validate_task_data(data, required_fields=["recipient"])
    if validation_error:
        return create_task_result("error", error=validation_error)

    recipient = data.get("recipient")
    subject = data.get("subject", "Notification")
    message = data.get("message", "")
    try:
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

        log_task_execution("send_notification_email", "complete", f"Email sent to {recipient}")

        return create_task_result(
            "success",
            {
                "recipient": recipient,
                "subject": subject,
                "message_length": len(message),
            },
        )

    except Exception as e:
        error_msg = f"Email sending failed: {str(e)}"
        log_task_execution("send_notification_email", "error", error_msg, level="error")
        return create_task_result("error", error=error_msg)


def process_user_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    Process user data in the background.

    Args:
        data: Task data containing user processing parameters

    Returns:
        Task result dictionary
    """
    logger.info("Processing user data")

    user_id = data.get("user_id")
    operation = data.get("operation", "sync")

    try:
        from .models import User

        user = User.objects.get(id=user_id)
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

    except Exception as e:
        logger.error(f"User processing failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
        }


# Task configuration for dispatcherd
TASK_FUNCTIONS = {
    "cleanup_old_data": cleanup_old_data,
    "send_notification_email": send_notification_email,
    "process_user_data": process_user_data,
}


def execute_db_task(data: dict[str, Any]) -> dict[str, Any]:
    """
    Execute a database-defined task with comprehensive error handling and tracking.

    This function is the main entry point for executing tasks that are defined
    in the database. It handles the complete lifecycle of task execution including
    validation, execution, status tracking, and post-execution processing.

    Args:
        data (dict): Task data containing:
            - task_id (int): ID of the task to execute (required)
            - execution_id (int): ID of the execution record (optional)

    Returns:
        dict: Task result dictionary with execution status and results
    """
    log_task_execution("execute_db_task", "start", "Starting database task execution")

    # Validate input data
    validation_error = validate_task_data(data, required_fields=["task_id"])
    if validation_error:
        return create_task_result("error", error=validation_error)

    task_id = data.get("task_id")
    execution_id = data.get("execution_id")

    try:
        # Get task and execution objects
        task, execution = _get_task_and_execution(task_id, execution_id)

        # Validate task function exists
        if task.function_name not in TASK_FUNCTIONS:
            error_msg = f"Task function '{task.function_name}' not found in TASK_FUNCTIONS"
            return handle_task_error(task, execution, error_msg)

        # Start task execution
        update_task_status(task, execution, status="running")
        log_task_execution(task.name, "running", f"Executing function: {task.function_name}")

        # Execute the actual task function
        task_function = TASK_FUNCTIONS[task.function_name]
        result = task_function(task.task_data)

        # Complete task execution
        status = "completed" if result.get("status") == "success" else "failed"
        error_message = result.get("error", "") if status == "failed" else ""

        update_task_status(task, execution, status=status, result_data=result, error_message=error_message)
        log_task_execution(task.name, "completed", f"Task execution finished with status: {status}")

        # Handle post-execution tasks
        _handle_post_execution(task)

        return result

    except Exception as e:
        return handle_task_error(None, None, task_id=task_id, execution_id=execution_id, exception=e)


def _get_task_and_execution(task_id, execution_id):
    """Get task and execution objects with proper locking."""
    from .models import Task, TaskExecution

    with transaction.atomic():
        task = Task.objects.select_for_update().get(id=task_id)
        execution = None

        if execution_id:
            execution = TaskExecution.objects.get(id=execution_id)

    return task, execution


def _validate_task_function(task, execution):
    """Validate that the task function exists and handle errors if not."""
    function_name = task.function_name
    if function_name not in TASK_FUNCTIONS:
        error_msg = f"Task function '{function_name}' not found in TASK_FUNCTIONS"
        logger.error(error_msg)

        with transaction.atomic():
            if execution:
                execution.status = "failed"
                execution.error_message = error_msg
                execution.completed_at = timezone.now()
                execution.save()

            task.status = "failed"
            task.error_message = error_msg
            task.attempts += 1
            task.save()

        return {"status": "error", "error": error_msg}
    return None


def _start_task_execution(task, execution):
    """Start task execution by updating status and timestamps."""
    with transaction.atomic():
        task.status = "running"
        task.started_at = timezone.now()
        task.attempts += 1
        task.save()

        if execution:
            execution.status = "running"
            execution.save()


def _complete_task_execution(task, execution, result):
    """Complete task execution by updating status and results."""
    with transaction.atomic():
        task.refresh_from_db()

        if result.get("status") == "success":
            task.status = "completed"
            task.result_data = result
            task.error_message = ""
        else:
            task.status = "failed"
            task.result_data = result
            task.error_message = result.get("error", "Unknown error")

        task.completed_at = timezone.now()
        task.save()

        if execution:
            execution.refresh_from_db()
            execution.status = task.status
            execution.result_data = result
            execution.error_message = task.error_message
            execution.completed_at = timezone.now()
            execution.save()


def _handle_post_execution(task):
    """Handle post-execution tasks like dependencies and recurring tasks."""
    if task.status == "completed":
        trigger_dependent_tasks(task)

    if task.is_recurring and task.status == "completed":
        schedule_next_occurrence(task)


def _handle_task_execution_error(task_id, execution_id, exception):
    """Handle errors during task execution."""
    from .models import Task, TaskExecution

    error_msg = f"Task execution failed: {str(exception)}"
    logger.error(error_msg)

    if isinstance(exception, Task.DoesNotExist):
        error_msg = f"Task with id {task_id} not found"
        logger.error(error_msg)
        return {"status": "error", "error": error_msg}

    # Update task status on exception
    try:
        with transaction.atomic():
            task = Task.objects.get(id=task_id)
            task.status = "failed"
            task.error_message = error_msg
            task.completed_at = timezone.now()
            task.save()

            if execution_id:
                try:
                    execution = TaskExecution.objects.get(id=execution_id)
                    execution.status = "failed"
                    execution.error_message = error_msg
                    execution.completed_at = timezone.now()
                    execution.save()
                except TaskExecution.DoesNotExist:
                    pass
    except Exception as save_error:
        logger.error(f"Failed to update task status after error: {save_error}")

    return {"status": "error", "error": error_msg}


def trigger_dependent_tasks(completed_task):
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
                    # Submit task to scheduler
                    submit_task_to_dispatcher(task)
                    logger.info(f"Triggered dependent task: {task.name} (ID: {task.id})")

            except Task.DoesNotExist:
                logger.warning(f"Dependent task {task_id} not found")
                continue

    except Exception as e:
        logger.error(f"Error triggering dependent tasks: {str(e)}")


def schedule_next_occurrence(task):
    """
    Schedule the next occurrence of a recurring task.

    Args:
        task: The recurring task to schedule
    """
    from .models import Task

    try:
        next_run_time = task.get_next_run_time()
        if next_run_time:
            # Create a new task instance for the next occurrence
            Task.objects.create(
                name=f"{task.name} (Next)",
                function_name=task.function_name,
                task_data=task.task_data,
                scheduled_time=next_run_time,
                cron_expression=task.cron_expression,
                is_recurring=task.is_recurring,
                priority=task.priority,
                max_attempts=task.max_attempts,
                timeout_seconds=task.timeout_seconds,
                created_by=task.created_by,
            )
            logger.info(f"Scheduled next occurrence of {task.name} for {next_run_time}")

    except Exception as e:
        logger.error(f"Error scheduling next occurrence: {str(e)}")


def submit_task_to_dispatcher(task):
    """
    Submit a task to the dispatcher for execution.

    Args:
        task: The task to submit
    """
    from .models import TaskExecution

    try:
        # Create execution record
        TaskExecution.objects.create(task=task, status="pending", worker_id=f"dispatcher-{os.getpid()}")

        # Submit to dispatcher using the existing dispatcherd system
        # This assumes dispatcherd is running and can handle the execute_db_task function

        # Update task status to indicate it's been submitted
        task.status = "pending"
        task.save()

        logger.info(f"Submitted task {task.name} (ID: {task.id}) to dispatcher")

    except Exception as e:
        logger.error(f"Error submitting task to dispatcher: {str(e)}")
        task.status = "failed"
        task.error_message = f"Failed to submit to dispatcher: {str(e)}"
        task.save()


class TaskScheduler:
    """
    Service to continuously poll the database for ready tasks and submit them to the dispatcher.
    """

    def __init__(self, poll_interval=30):
        self.poll_interval = poll_interval
        self.running = False

    def start(self):
        """Start the task scheduler."""
        self.running = True
        logger.info("Task scheduler started")

        try:
            while self.running:
                try:
                    self.process_ready_tasks()
                    self.cleanup_stale_tasks()
                    time.sleep(self.poll_interval)
                except KeyboardInterrupt:
                    logger.info("Task scheduler stopped by user")
                    break
                except Exception as e:
                    logger.error(f"Error in task scheduler: {str(e)}")
                    time.sleep(self.poll_interval)
        finally:
            self.running = False

    def stop(self):
        """Stop the task scheduler."""
        self.running = False
        logger.info("Task scheduler stopping...")

    def process_ready_tasks(self):
        """Find and submit ready tasks to the dispatcher."""
        from .models import Task

        try:
            # Find tasks that are ready to run
            ready_tasks = Task.objects.filter(status="pending").order_by("priority", "scheduled_time", "created")

            count = 0
            for task in ready_tasks:
                if task.is_ready_to_run():
                    submit_task_to_dispatcher(task)
                    count += 1

            if count > 0:
                logger.info(f"Submitted {count} ready tasks to dispatcher")

        except Exception as e:
            logger.error(f"Error processing ready tasks: {str(e)}")

    def cleanup_stale_tasks(self):
        """Clean up stale tasks that have been running too long."""
        from .models import Task

        try:
            stale_cutoff = timezone.now() - timezone.timedelta(hours=1)

            stale_tasks = Task.objects.filter(status="running", started_at__lt=stale_cutoff)

            count = 0
            for task in stale_tasks:
                # Check if task has exceeded its timeout
                if task.started_at and task.timeout_seconds:
                    runtime = (timezone.now() - task.started_at).total_seconds()
                    if runtime > task.timeout_seconds:
                        task.status = "failed"
                        task.error_message = f"Task timed out after {runtime} seconds"
                        task.completed_at = timezone.now()
                        task.save()
                        count += 1

            if count > 0:
                logger.info(f"Marked {count} stale tasks as failed")

        except Exception as e:
            logger.error(f"Error cleaning up stale tasks: {str(e)}")


# Updated task configuration for dispatcherd
TASK_FUNCTIONS = {
    "cleanup_old_data": cleanup_old_data,
    "send_notification_email": send_notification_email,
    "process_user_data": process_user_data,
    "execute_db_task": execute_db_task,  # New function for database tasks
}

# Legacy scheduled tasks configuration (kept for backward compatibility)
SCHEDULED_TASKS = {
    "daily_cleanup": {
        "function": "cleanup_old_data",
        "schedule": 86400,  # Run daily (in seconds)
        "data": {"days_old": 30},
    },
}
