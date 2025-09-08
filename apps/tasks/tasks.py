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

# Import dispatcherd task decorator
try:
    from dispatcherd.publish import task
except ImportError:
    # Fallback decorator if dispatcherd is not available
    def task(queue=None, decorate=False):
        def decorator(func):
            return func

        return decorator


from .utils import (
    create_task_result,
    handle_task_error,
    log_task_execution,
    update_task_status,
    validate_task_data,
)

logger = logging.getLogger(__name__)


@task(queue="metrics_cleanup", decorate=False)
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


@task(queue="metrics_notifications", decorate=False)
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


@task(queue="metrics_tasks", decorate=False)
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
        from django.contrib.auth import get_user_model

        User = get_user_model()

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


@task(queue="metrics_tasks", decorate=False)
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


def _get_task_and_execution(task_id: int, execution_id: int | None) -> tuple[Any, Any]:
    """Get task and execution objects with proper locking."""
    from .models import Task, TaskExecution

    with transaction.atomic():
        task = Task.objects.select_for_update().get(id=task_id)
        execution = None

        if execution_id:
            execution = TaskExecution.objects.get(id=execution_id)

    return task, execution


def _handle_post_execution(task: Any) -> None:
    """Handle post-execution tasks like dependencies and recurring tasks."""
    if task.status == "completed":
        trigger_dependent_tasks(task)

    if task.is_recurring and task.status == "completed":
        schedule_next_occurrence(task)


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
                    # Submit task to scheduler
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
    Task scheduler that moves pending tasks from the database to the dispatcher queue.

    This scheduler polls the database for pending tasks and publishes them to
    the appropriate dispatcherd queue for execution.
    """

    def __init__(self, poll_interval: int = 30):
        """
        Initialize the task scheduler.

        Args:
            poll_interval: How often to check for pending tasks (in seconds)
        """
        self.poll_interval = poll_interval
        self.running = False

    def start(self):
        """Start the task scheduler main loop."""
        self.running = True
        logger.info(f"Task scheduler started with {self.poll_interval}s poll interval")

        while self.running:
            try:
                self.process_pending_tasks()
                time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Error in task scheduler: {str(e)}")
                time.sleep(self.poll_interval)

    def stop(self):
        """Stop the task scheduler."""
        self.running = False
        logger.info("Task scheduler stopped")

    def process_pending_tasks(self):
        """Process all pending tasks and publish them to dispatcher queues."""
        try:
            from .models import Task
            from django.db.models import Q

            # Get all pending tasks that are ready to run
            # Include tasks with no scheduled_time (immediate execution) and tasks whose time has come
            with transaction.atomic():
                pending_tasks = Task.objects.filter(status="pending").filter(
                    Q(scheduled_time__isnull=True) | Q(scheduled_time__lte=timezone.now())
                )

                if not pending_tasks.exists():
                    return

                logger.info(f"Found {pending_tasks.count()} pending tasks ready for execution")

                for task in pending_tasks:
                    try:
                        # Lock this specific task for update
                        locked_task = Task.objects.select_for_update().get(id=task.id, status="pending")
                        self.publish_task(locked_task)
                    except Task.DoesNotExist:
                        # Task was already processed by another worker
                        logger.debug(f"Task {task.id} already processed")
                        continue
                    except Exception as e:
                        logger.error(f"Failed to publish task {task.id}: {str(e)}")
                        # Mark task as failed if we can't publish it
                        try:
                            failed_task = Task.objects.get(id=task.id)
                            failed_task.status = "failed"
                            failed_task.error_message = f"Failed to publish to dispatcher: {str(e)}"
                            failed_task.completed_at = timezone.now()
                            failed_task.save()
                        except Exception as save_error:
                            logger.error(f"Failed to mark task {task.id} as failed: {str(save_error)}")

        except Exception as e:
            logger.error(f"Error processing pending tasks: {str(e)}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    def publish_task(self, task):
        """
        Publish a single task to the appropriate dispatcher queue.

        Args:
            task: Task instance to publish
        """
        try:
            # Import dispatcherd submit function
            from dispatcherd.publish import submit_task

            # Determine the appropriate queue based on task type
            queue = self.get_queue_for_task(task)

            # Prepare task data for the function
            function_data = task.task_data.copy() if task.task_data else {}
            function_data["task_id"] = task.id

            # Update task status to running
            task.status = "running"
            task.started_at = timezone.now()
            task.save()

            # Submit to dispatcher
            # Get the actual function from TASK_FUNCTIONS
            function_name = task.function_name
            if function_name not in TASK_FUNCTIONS:
                raise ValueError(f"Unknown task function: {function_name}")

            task_func = TASK_FUNCTIONS[function_name]

            # Submit the task
            submit_task(task_func, kwargs=function_data, queue=queue)

            logger.info(f"Submitted task {task.id} ({task.function_name}) to queue {queue}")

        except Exception as e:
            logger.error(f"Failed to submit task {task.id}: {str(e)}")
            # Roll back the status change
            task.status = "pending"
            task.started_at = None
            task.save()
            raise

    def get_queue_for_task(self, task):
        """
        Determine the appropriate queue for a task based on its function.

        Args:
            task: Task instance

        Returns:
            str: Queue name
        """
        # Map function names to queues
        queue_mapping = {
            "cleanup_old_data": "metrics_cleanup",
            "send_notification_email": "metrics_notifications",
            "process_user_data": "metrics_tasks",
            "execute_db_task": "metrics_tasks",
        }

        return queue_mapping.get(task.function_name, "metrics_tasks")


# Task configuration for dispatcherd
TASK_FUNCTIONS = {
    "cleanup_old_data": cleanup_old_data,
    "send_notification_email": send_notification_email,
    "process_user_data": process_user_data,
    "execute_db_task": execute_db_task,
}

# Legacy scheduled tasks configuration (kept for backward compatibility)
SCHEDULED_TASKS = {
    "daily_cleanup": {
        "function": "cleanup_old_data",
        "schedule": 86400,  # Run daily (in seconds)
        "data": {"days_old": 30},
    },
}
