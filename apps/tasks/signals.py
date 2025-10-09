"""
Django signals for task management integration.

This module provides signals that connect API endpoints with the cron-based
scheduler, allowing dynamic task scheduling and management.
"""

import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .cron_scheduler import get_scheduler
from .models import Task, TaskExecution
from .task_groups import get_task_group_status

logger = logging.getLogger(__name__)

# Signal control to prevent recursion
_signals_enabled = True

def _disable_signals():
    """Temporarily disable signals to prevent recursion."""
    global _signals_enabled
    _signals_enabled = False

def _enable_signals():
    """Re-enable signals."""
    global _signals_enabled
    _signals_enabled = True


@receiver(post_save, sender=Task)
def task_created_or_updated(sender, instance, created, **kwargs):
    """
    Handle task creation and updates.

    When a task is created or updated, this signal will:
    - Schedule immediate tasks if they're ready to run  
    - Add recurring tasks to the cron scheduler
    - Update existing scheduled tasks
    - Integrate with task groups system for proper categorization
    """
    # Skip if signals are disabled to prevent recursion
    if not _signals_enabled:
        return
        
    try:
        scheduler = get_scheduler()

        if created:
            logger.info(f"New task created: {instance.name} ({instance.function_name})")
            _handle_new_task(instance, scheduler)
        else:
            logger.info(f"Task updated: {instance.name} ({instance.function_name})")
            _handle_updated_task(instance, scheduler)

    except Exception as e:
        logger.error(f"Error handling task signal for {instance.id}: {str(e)}")


@receiver(post_delete, sender=Task)
def task_deleted(sender, instance, **kwargs):
    """
    Handle task deletion.

    When a task is deleted, remove it from the cron scheduler.
    """
    try:
        scheduler = get_scheduler()
        scheduler.remove_task(f"task_{instance.id}")
        logger.info(f"Removed deleted task from scheduler: {instance.name}")
    except Exception as e:
        logger.error(f"Error removing deleted task {instance.id}: {str(e)}")


@receiver(post_save, sender=TaskExecution)
def task_execution_created(sender, instance, created, **kwargs):
    """
    Handle task execution creation.

    This can be used to trigger dependent tasks or notifications.
    """
    if created:
        logger.info(f"Task execution created: {instance.task.name} - {instance.status}")


def _handle_new_task(task, scheduler):
    """Handle a newly created task."""
    task_id = f"task_{task.id}"

    # Route task based on its scheduling requirements
    logger.info(f"New task created: {task.name} - routing to appropriate processor")
    
    # Check if task is ready to run immediately
    if task.is_ready_to_run() and not task.scheduled_time and not task.is_recurring:
        logger.info(f"Submitting immediate task to dispatcherd: {task.name}")
        # Submit directly to dispatcherd for immediate execution
        _submit_task_to_dispatcherd_directly(task)
        return

    # Handle recurring tasks
    if task.is_recurring and task.cron_expression:
        logger.info(f"Adding recurring task to scheduler: {task.name}")
        scheduler.add_dynamic_task(
            task_id=task_id,
            function_name=task.function_name,
            cron_expression=task.cron_expression,
            args=task.task_data or {},
            description=task.name,
        )
        return

    # Handle scheduled tasks (one-time future execution)
    if task.scheduled_time and task.scheduled_time > timezone.now():
        logger.info(f"Adding scheduled task to cron scheduler: {task.name} for {task.scheduled_time}")
        _schedule_future_task(task, scheduler)
        return


def _handle_updated_task(task, scheduler):
    """Handle an updated task."""
    task_id = f"task_{task.id}"

    # Route updated tasks if they become ready
    logger.info(f"Task updated: {task.name} - status: {task.status}")
    
    # If task is now ready to run and pending
    if task.is_ready_to_run() and task.status == "pending":
        if not task.scheduled_time and not task.is_recurring:
            logger.info(f"Updated task now ready for immediate execution: {task.name}")
            _submit_task_to_dispatcherd_directly(task)
            return

    # Update recurring task if it exists
    if task.is_recurring and task.cron_expression:
        logger.info(f"Updating recurring task: {task.name}")
        scheduler.update_task(
            task_id=task_id,
            function=task.function_name,
            cron=task.cron_expression,
            args=task.task_data or {},
            description=task.name,
        )
        return


def _schedule_future_task(task, scheduler):
    """
    Schedule a task for future execution using APScheduler DateTrigger.
    """
    try:
        from apscheduler.triggers.date import DateTrigger
        
        task_id = f"scheduled_task_{task.id}"
        
        # Create a date trigger for the scheduled time
        trigger = DateTrigger(run_date=task.scheduled_time)
        
        # Add job to scheduler
        scheduler.scheduler.add_job(
            func=_execute_scheduled_database_task,
            trigger=trigger,
            args=[task.id],
            id=task_id,
            name=f"Scheduled: {task.name}",
            replace_existing=True,
            max_instances=1,
        )
        
        logger.info(f"Added scheduled task {task.name} to run at {task.scheduled_time}")
        
    except Exception as e:
        logger.error(f"Failed to schedule future task {task.name}: {str(e)}")
        # Mark task as failed
        task.status = "failed"
        task.error_message = f"Failed to schedule: {str(e)}"
        task.save()


# Signal handlers for API endpoints
@receiver(pre_save, sender=Task)
def task_pre_save(sender, instance, **kwargs):
    """
    Handle task before save.

    This can be used to validate task data or set default values.
    """
    # Ensure task_data is a dict
    if instance.task_data is None:
        instance.task_data = {}

    # Set default timeout if not specified
    if not hasattr(instance, "timeout_seconds") or instance.timeout_seconds is None:
        instance.timeout_seconds = 3600


# Utility functions for API integration
def schedule_task_via_api(
    function_name: str,
    task_data: dict = None,
    cron_expression: str = None,
    scheduled_time=None,
    is_recurring: bool = False,
    task_name: str = None,
):
    """
    Schedule a task via API call.

    This function can be called from API endpoints to schedule tasks
    through the cron scheduler.

    Args:
        function_name: Name of the function to execute
        task_data: Data to pass to the function
        cron_expression: Cron expression for recurring tasks
        scheduled_time: Specific time to run the task
        is_recurring: Whether this is a recurring task
        task_name: Human-readable name for the task

    Returns:
        Task instance or scheduler job ID
    """
    if task_data is None:
        task_data = {}

    scheduler = get_scheduler()

    if is_recurring and cron_expression:
        # Schedule recurring task
        task_id = f"api_recurring_{timezone.now().timestamp()}"
        scheduler.add_dynamic_task(
            task_id=task_id,
            function_name=function_name,
            cron_expression=cron_expression,
            args=task_data,
            description=task_name or function_name,
        )
        return task_id

    elif scheduled_time:
        # Schedule one-time future task
        # For now, create a database task
        task = Task.objects.create(
            name=task_name or function_name,
            function_name=function_name,
            task_data=task_data,
            scheduled_time=scheduled_time,
            is_recurring=False,
        )
        return task

    else:
        # Schedule immediate task
        return scheduler.schedule_immediate_task(function_name=function_name, args=task_data)


def cancel_scheduled_task(task_id: str):
    """
    Cancel a scheduled task.

    Args:
        task_id: ID of the task to cancel
    """
    scheduler = get_scheduler()

    # Try to remove from scheduler first
    try:
        scheduler.remove_task(task_id)
        logger.info(f"Removed task from scheduler: {task_id}")
    except Exception as e:
        logger.warning(f"Task {task_id} not found in scheduler: {str(e)}")

    # Also try to cancel database task if it exists
    try:
        if task_id.startswith("task_"):
            db_task_id = task_id.replace("task_", "")
            task = Task.objects.get(id=db_task_id)
            task.status = "cancelled"
            task.save()
            logger.info(f"Cancelled database task: {task.name}")
    except Task.DoesNotExist:
        logger.debug(f"Database task {task_id} not found")


def get_task_status(task_id: str):
    """
    Get the status of a scheduled task.

    Args:
        task_id: ID of the task

    Returns:
        Dictionary with task status information
    """
    scheduler = get_scheduler()

    # Check scheduler first
    status = scheduler.get_task_status(task_id)
    if status:
        return status

    # Check database task
    try:
        if task_id.startswith("task_"):
            db_task_id = task_id.replace("task_", "")
            task = Task.objects.get(id=db_task_id)
            return {
                "id": task_id,
                "name": task.name,
                "status": task.status,
                "function_name": task.function_name,
                "created": task.created,
                "scheduled_time": task.scheduled_time,
            }
    except Task.DoesNotExist:
        pass

    return None


# Feature flag change handling
def handle_feature_flag_change(flag_name: str, new_value: bool):
    """
    Handle feature flag changes that affect task groups.
    
    This function should be called when feature flags are updated
    to reload the task registry and update active tasks.
    
    Args:
        flag_name: Name of the feature flag that changed
        new_value: New value of the feature flag
    """
    logger.info(f"Feature flag changed: {flag_name} = {new_value}")
    
    # Check if this flag affects any task groups
    task_group_flags = ["ANONYMIZED_DATA_COLLECTION", "METRICS_COLLECTION_ENABLED"]
    
    if flag_name in task_group_flags:
        try:
            scheduler = get_scheduler()
            scheduler.reload_task_registry()
            logger.info(f"Task registry reloaded due to feature flag change: {flag_name}")
        except Exception as e:
            logger.error(f"Failed to reload task registry after feature flag change: {str(e)}")


def reload_task_groups():
    """
    Manually reload task groups and update the scheduler.
    
    This can be called from management commands or API endpoints
    to refresh the task registry when configuration changes.
    """
    try:
        scheduler = get_scheduler()
        scheduler.reload_task_registry()
        
        # Log current status
        group_status = get_task_group_status()
        for group_name, status in group_status.items():
            enabled_status = "enabled" if status["enabled"] else "disabled"
            logger.info(f"Task group '{group_name}': {enabled_status} ({status['enabled_tasks']}/{status['total_tasks']} tasks)")
            
        logger.info("Task groups reloaded successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to reload task groups: {str(e)}")
        return False


def _execute_scheduled_database_task(task_id):
    """
    Execute a scheduled database task when its time arrives.
    
    This function is called by APScheduler when a scheduled task is ready to run.
    """
    try:
        task = Task.objects.get(id=task_id)
        
        # Check if task is still pending and ready to run
        if task.status == "pending" and task.is_ready_to_run():
            logger.info(f"Executing scheduled task: {task.name}")
            _submit_task_to_dispatcherd_directly(task)
        else:
            logger.warning(f"Scheduled task {task.name} is no longer pending or ready (status: {task.status})")
            
    except Task.DoesNotExist:
        logger.error(f"Scheduled task with ID {task_id} no longer exists")
    except Exception as e:
        logger.error(f"Failed to execute scheduled task {task_id}: {str(e)}")


def _submit_task_to_dispatcherd_directly(task):
    """
    Submit a task directly to dispatcherd bypassing the cron scheduler.
    
    This is used for immediate execution tasks that don't need scheduling.
    """
    try:
        from .tasks import submit_task_to_dispatcher
        
        logger.info(f"Submitting task {task.id} directly to dispatcherd")
        
        # Temporarily disable signals to prevent recursion
        _disable_signals()
        try:
            submit_task_to_dispatcher(task)
        finally:
            _enable_signals()
        
    except Exception as e:
        logger.error(f"Failed to submit task {task.id} to dispatcherd: {str(e)}")
        # Update task status to failed - also disable signals to prevent loops
        _disable_signals()
        try:
            task.status = "failed"
            task.error_message = f"Failed to submit to dispatcher: {str(e)}"
            task.save()
        finally:
            _enable_signals()
