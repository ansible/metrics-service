"""
Fail tasks that are stuck in 'running' status beyond their timeout.

This task detects tasks permanently orphaned by a worker crash and marks them
failed so the execution history is accurate and operators can see what happened.
"""

import logging
from typing import Any

from django.utils import timezone

from ..utils import create_task_result, log_task_execution

logger = logging.getLogger(__name__)


def cleanup_stuck_tasks(**kwargs) -> dict[str, Any]:
    """
    Detect and fail tasks that are stuck in 'running' status beyond their timeout.

    When the dispatcherd worker is killed mid-execution, in-flight tasks are left permanently in 'running' with no completed_at. This task detects those orphans and marks them failed.

    Each task's own timeout_seconds field is used, so tasks with different timeouts
    are evaluated correctly.

    Args:
        **kwargs: Task data containing optional parameters:
            - dry_run (bool): If True, only count tasks that would be failed (default: False)

    Returns:
        dict: Task result dictionary with stuck task statistics
    """
    from ..models import Task, TaskExecution

    dry_run = kwargs.get("dry_run", False)

    log_task_execution("cleanup_stuck_tasks", "processing", "Scanning for tasks stuck beyond their timeout")

    now = timezone.now()
    stuck_ids = [
        t.id
        for t in Task.objects.filter(status="running")
        if t.started_at and (now - t.started_at).total_seconds() > t.timeout_seconds
    ]
    stuck_tasks = Task.objects.filter(id__in=stuck_ids, status="running")
    task_count = stuck_tasks.count()
    execution_count = TaskExecution.objects.filter(task__in=stuck_tasks, status="running").count()

    failed_tasks = 0
    failed_executions = 0

    if not dry_run and task_count > 0:
        log_task_execution("cleanup_stuck_tasks", "processing", f"Failing {task_count} stuck task(s)")

        error_message = "Task timed out — worker died before completion (detected by cleanup_stuck_tasks)"

        failed_executions = TaskExecution.objects.filter(task__in=stuck_tasks, status="running").update(
            status="failed",
            error_message=error_message,
            completed_at=now,
        )
        failed_tasks = stuck_tasks.update(
            status="failed",
            error_message=error_message,
            completed_at=now,
        )

        message = f"Failed {failed_tasks} stuck task(s) and {failed_executions} execution(s)"
        log_task_execution("cleanup_stuck_tasks", "completed", message)
    else:
        message = f"Found {task_count} stuck task(s) and {execution_count} execution(s) that would be failed"
        log_task_execution("cleanup_stuck_tasks", "completed", message)

    return create_task_result(
        "success",
        {
            "dry_run": dry_run,
            "tasks_found": task_count,
            "executions_found": execution_count,
            "tasks_failed": failed_tasks,
            "executions_failed": failed_executions,
        },
    )
