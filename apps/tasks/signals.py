"""
Unified signal handlers for task management.

This module contains Django signal handlers that manage both immediate task execution
and registration of scheduled/recurring tasks with the task scheduler.
"""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Task

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Task)
def task_created_or_updated(sender, instance, created, **kwargs):
    """
    Handle task creation and updates.

    Only handles immediate execution tasks. Scheduled and recurring tasks
    are handled by the simple scheduler.
    """
    task = instance

    # Skip signal processing for system tasks to avoid recursive loops
    if getattr(task, "_skip_signals", False):
        return

    try:
        if created:
            logger.info(f"New task created: {task.name} (ID: {task.id})")
            _handle_new_task(task)
        else:
            logger.info(f"Task updated: {task.name} (ID: {task.id})")
            _handle_updated_task(task)

        # Register scheduled/recurring tasks with task scheduler
        _register_with_scheduler(task, created)

    except Exception as e:
        logger.error(f"Error in task signal handler: {str(e)}")


def _handle_new_task(task):
    """Handle a newly created task - only immediate execution."""
    # Only handle tasks for immediate execution (no scheduled time, no recurring)
    if task.is_ready_to_run() and task.status == "pending" and not task.scheduled_time and not task.is_recurring:
        # Check if task already has execution records to avoid duplicate submissions
        from .models import TaskExecution

        if TaskExecution.objects.filter(task=task).exists():
            logger.debug(f"Task {task.name} already has execution records, skipping submission")
            return

        logger.info(f"Task ready for immediate execution: {task.name}")
        _submit_task_to_dispatcherd_directly(task)
        return

    # Scheduled/recurring tasks will be registered with scheduler below
    if task.scheduled_time or task.is_recurring:
        logger.info(f"Task will be registered with task scheduler: {task.name}")


def _handle_updated_task(task):
    """Handle an updated task - only immediate execution."""
    # Skip if task is already being processed or completed to avoid loops
    if task.status in ["running", "completed", "failed"]:
        return

    # If task is now ready to run and pending (and not scheduled/recurring)
    if task.is_ready_to_run() and task.status == "pending" and not task.scheduled_time and not task.is_recurring:
        # Check if task already has execution records to avoid duplicate submissions
        from .models import TaskExecution

        if TaskExecution.objects.filter(task=task).exists():
            logger.debug(f"Task {task.name} already has execution records, skipping submission")
            return

        logger.info(f"Updated task now ready for immediate execution: {task.name}")
        _submit_task_to_dispatcherd_directly(task)


def _submit_task_to_dispatcherd_directly(task):
    """
    Submit a task directly to dispatcherd for immediate execution.
    """
    try:
        from .tasks_system import submit_task_to_dispatcher

        submit_task_to_dispatcher(task)
        logger.info(f"Submitted task to dispatcherd: {task.name} (ID: {task.id})")

    except Exception as e:
        logger.error(f"Error submitting task to dispatcherd: {str(e)}")
        task.status = "failed"
        task.error_message = f"Failed to submit to dispatcherd: {str(e)}"
        task._skip_signals = True  # Prevent infinite recursion
        task.save()


def _register_with_scheduler(task, is_new_task):
    """Register scheduled/recurring tasks with the task scheduler."""
    try:
        from .cron_scheduler import get_scheduler

        scheduler = get_scheduler()

        # Only register if task has scheduled time or is recurring
        if task.status == "pending" and (task.scheduled_time or task.is_recurring):
            if is_new_task:
                scheduler.add_database_task(task)
            else:
                scheduler.update_database_task(task)

    except Exception as e:
        logger.debug(f"Could not register task with scheduler: {e}")
        # This is not critical for immediate tasks


@receiver(post_delete, sender=Task)
def task_deleted(sender, instance, **kwargs):
    """Handle task deletion by removing from scheduler."""
    try:
        from .cron_scheduler import get_scheduler

        scheduler = get_scheduler()
        scheduler.remove_database_task_by_id(instance.id)
        logger.info(f"Removed task {instance.name} (ID: {instance.id}) from scheduler")

    except Exception as e:
        logger.debug(f"Could not remove task from scheduler: {e}")
