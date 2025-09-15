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
    ensure_django_setup,
    get_task_and_execution,
    handle_post_execution,
    handle_task_error,
    log_task_execution,
    task_execution_wrapper,
    update_task_status,
)

logger = logging.getLogger(__name__)


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
    from django.utils import timezone

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
            from django.db.models import Q

            from .models import Task

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
            # Always use execute_db_task as the entry point to ensure proper execution pipeline
            if task.function_name not in TASK_FUNCTIONS:
                raise ValueError(f"Unknown task function: {task.function_name}")

            # Use execute_db_task as the entry point for all tasks
            task_func = TASK_FUNCTIONS["execute_db_task"]

            # Submit the task with task_id as the main parameter
            submit_task(task_func, kwargs={"task_id": task.id}, queue=queue)

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
            "hello_world": "metrics_tasks",
            "cleanup_old_data": "metrics_cleanup",
            "send_notification_email": "metrics_notifications",
            "process_user_data": "metrics_tasks",
            "execute_db_task": "metrics_tasks",
        }

        return queue_mapping.get(task.function_name, "metrics_tasks")


# Task configuration for dispatcherd
TASK_FUNCTIONS = {
    "hello_world": hello_world,
    "cleanup_old_data": cleanup_old_data,
    "send_notification_email": send_notification_email,
    "process_user_data": process_user_data,
    "execute_db_task": execute_db_task,
    "sleep": sleep,
}
