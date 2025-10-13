"""
Simplified signal handlers for task management.

This module contains Django signal handlers that handle immediate task execution.
The simple scheduler handles all scheduled and recurring tasks.
"""

import logging

from django.db.models.signals import post_save
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

        # Signal the scheduler to refresh (pick up new tasks on next cycle)
        _signal_scheduler_refresh()

    except Exception as e:
        logger.error(f"Error in task signal handler: {str(e)}")


def _handle_new_task(task):
    """Handle a newly created task - only immediate execution."""
    # Only handle tasks for immediate execution (no scheduled time, no recurring)
    if task.is_ready_to_run() and task.status == "pending" and not task.scheduled_time and not task.is_recurring:
        logger.info(f"Task ready for immediate execution: {task.name}")
        _submit_task_to_dispatcherd_directly(task)
        return

    # All other tasks (scheduled/recurring) are handled by the scheduler
    if task.scheduled_time or task.is_recurring:
        logger.info(f"Task will be handled by scheduler: {task.name}")


def _handle_updated_task(task):
    """Handle an updated task - only immediate execution."""
    # If task is now ready to run and pending (and not scheduled/recurring)
    if task.is_ready_to_run() and task.status == "pending" and not task.scheduled_time and not task.is_recurring:
        logger.info(f"Updated task now ready for immediate execution: {task.name}")
        _submit_task_to_dispatcherd_directly(task)


def _submit_task_to_dispatcherd_directly(task):
    """
    Submit a task directly to dispatcherd for immediate execution.
    """
    try:
        from .tasks import submit_task_to_dispatcher

        submit_task_to_dispatcher(task)
        logger.info(f"Submitted task to dispatcherd: {task.name} (ID: {task.id})")

    except Exception as e:
        logger.error(f"Error submitting task to dispatcherd: {str(e)}")
        task.status = "failed"
        task.error_message = f"Failed to submit to dispatcherd: {str(e)}"
        task._skip_signals = True  # Prevent infinite recursion
        task.save()


def _signal_scheduler_refresh():
    """Signal the scheduler that new tasks may be available."""
    try:
        from .simple_scheduler import refresh_scheduler

        refresh_scheduler()
    except Exception as e:
        logger.debug(f"Could not signal scheduler refresh: {e}")
        # This is not critical, scheduler will pick up tasks on next cycle anyway
