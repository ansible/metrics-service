"""
Clean up old completed and failed tasks from the database.

This task removes tasks that have been completed or failed for more than
the specified number of days. This helps maintain database performance
and prevents unlimited growth of task history.

Two retention tiers are supported:

Standard retention (days_old):
    All completed/failed non-recurring tasks older than days_old days are deleted.

Short retention (hourly_tasks_hours_old):
    Execution records for hourly collector tasks (function_name="collect_hourly_metrics")
    are deleted after hourly_tasks_hours_old hours regardless of days_old. These tasks
    are high-frequency and their raw execution records have no long-term value once the
    underlying HourlyMetricsCollection records have been written.
"""

import logging
from datetime import timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone

from ..utils import create_task_result, log_task_execution

logger = logging.getLogger(__name__)

# Function names whose execution records rotate on the short retention schedule.
_HOURLY_TASK_FUNCTION_NAMES = {"collect_hourly_metrics"}

# Django deletion-info key for TaskExecution rows.
_TASK_EXECUTION_DELETE_KEY = "tasks.TaskExecution"


def _build_old_tasks_queryset(cutoff_date, preserve_recurring: bool):
    """Return a queryset of completed/failed tasks older than cutoff_date."""
    from ..models import Task

    base = Q(status__in=["completed", "failed"])
    if preserve_recurring:
        base &= Q(cron_expression__isnull=True)

    # Prefer completed_at; fall back to modified for tasks that never set it.
    by_completed = base & Q(completed_at__isnull=False, completed_at__lt=cutoff_date)
    by_modified = base & Q(completed_at__isnull=True, modified__lt=cutoff_date)

    return Task.objects.filter(by_completed | by_modified)


def _delete_old_tasks(
    old_tasks, hourly_tasks, include_executions: bool, task_count: int, hourly_task_count: int
) -> tuple[int, int, int]:
    """Delete old tasks and their execution records.

    Returns (deleted_tasks, deleted_hourly_tasks, deleted_executions).
    """
    from ..models import TaskExecution

    all_tasks_to_delete = old_tasks | hourly_tasks
    if not all_tasks_to_delete.exists():
        return 0, 0, 0

    log_task_execution(
        "cleanup_old_tasks",
        "processing",
        f"Deleting {task_count} standard + {hourly_task_count} hourly tasks",
    )

    if include_executions:
        _, exec_del = TaskExecution.objects.filter(task__in=all_tasks_to_delete).delete()
        deleted_executions = exec_del.get(_TASK_EXECUTION_DELETE_KEY, 0)

    _, old_del = old_tasks.delete()
    _, hourly_del = hourly_tasks.delete()

    if not include_executions:
        # Accumulate cascade-deleted executions from both querysets.
        deleted_executions = old_del.get(_TASK_EXECUTION_DELETE_KEY, 0) + hourly_del.get(_TASK_EXECUTION_DELETE_KEY, 0)

    return old_del.get("tasks.Task", 0), hourly_del.get("tasks.Task", 0), deleted_executions


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
            - days_old (int): Days after which completed/failed tasks are deleted (default: 5).
            - hourly_tasks_hours_old (int|None): Hours after which hourly collector execution
              records are deleted. When set, these are cleaned up independently of days_old
              since they accumulate quickly (up to ~24 executions/day per collector).
              Default: None (falls through to standard days_old retention).
            - dry_run (bool): If True, only count tasks that would be deleted (default: False).
            - include_executions (bool): Also cleanup related TaskExecution records (default: True).
            - preserve_recurring (bool): If True, exclude recurring tasks from cleanup (default: True).

    Returns:
        dict: Task result dictionary with cleanup statistics
    """
    from ..models import Task, TaskExecution  # TaskExecution needed for the execution_count query

    days_old = kwargs.get("days_old", 5)
    hourly_tasks_hours_old = kwargs.get("hourly_tasks_hours_old")
    dry_run = kwargs.get("dry_run", False)
    include_executions = kwargs.get("include_executions", True)
    preserve_recurring = kwargs.get("preserve_recurring", True)

    log_task_execution("cleanup_old_tasks", "processing", f"Cleaning up tasks older than {days_old} days")

    cutoff_date = timezone.now() - timedelta(days=days_old)
    old_tasks = _build_old_tasks_queryset(cutoff_date, preserve_recurring)

    # Short-retention pass: hourly collector executions have their own tighter cutoff.
    # They are excluded from the standard queryset to avoid double-counting.
    hourly_tasks = Task.objects.none()
    if hourly_tasks_hours_old is not None:
        hourly_cutoff = timezone.now() - timedelta(hours=int(hourly_tasks_hours_old))
        log_task_execution(
            "cleanup_old_tasks",
            "processing",
            f"Also cleaning up hourly collector tasks older than {hourly_tasks_hours_old}h",
        )
        hourly_tasks = _build_old_tasks_queryset(hourly_cutoff, preserve_recurring).filter(
            function_name__in=_HOURLY_TASK_FUNCTION_NAMES
        )
        # Exclude hourly tasks from the standard queryset so counts/deletes don't overlap.
        old_tasks = old_tasks.exclude(function_name__in=_HOURLY_TASK_FUNCTION_NAMES)

    task_count = old_tasks.count()
    hourly_task_count = hourly_tasks.count()
    execution_count = 0

    if include_executions:
        execution_count = TaskExecution.objects.filter(task__in=old_tasks | hourly_tasks).count()

    deleted_tasks = 0
    deleted_hourly_tasks = 0
    deleted_executions = 0

    suffix = " (recurring tasks preserved)" if preserve_recurring else ""
    if not dry_run:
        deleted_tasks, deleted_hourly_tasks, deleted_executions = _delete_old_tasks(
            old_tasks, hourly_tasks, include_executions, task_count, hourly_task_count
        )
        message = f"Deleted {deleted_tasks + deleted_hourly_tasks} tasks and {deleted_executions} executions{suffix}"
        log_task_execution("cleanup_old_tasks", "completed", message)
    else:
        message = f"Found {task_count + hourly_task_count} tasks and {execution_count} executions that would be deleted{suffix}"
        log_task_execution("cleanup_old_tasks", "completed", message)

    return create_task_result(
        "success",
        {
            "days_old": days_old,
            "hourly_tasks_hours_old": hourly_tasks_hours_old,
            "cutoff_date": cutoff_date.isoformat(),
            "dry_run": dry_run,
            "include_executions": include_executions,
            "preserve_recurring": preserve_recurring,
            "tasks_found": task_count,
            "hourly_tasks_found": hourly_task_count,
            "executions_found": execution_count,
            "tasks_deleted": deleted_tasks,
            "hourly_tasks_deleted": deleted_hourly_tasks,
            "executions_deleted": deleted_executions,
        },
    )
