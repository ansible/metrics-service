"""
Clean up old ActivityStream entries from the database.

This task removes ActivityStream (django-ansible-base) entries that are older than
the configured number of days. This helps maintain database performance and prevents
unlimited growth of audit logs.
"""

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

from ..utils import create_task_result, log_task_execution, task, task_execution_wrapper

logger = logging.getLogger(__name__)


@task(queue="metrics_cleanup", decorate=False)
@task_execution_wrapper("cleanup_activitystream")
def cleanup_activitystream(**kwargs) -> dict[str, Any]:
    """
    Clean up old ActivityStream entries from the database.

    This task removes ActivityStream (django-ansible-base) entries older than the
    specified number of days to maintain database performance and bound audit log growth.

    Args:
        **kwargs: Task data containing cleanup parameters:
            - days_old (int): Number of days old entries must be to qualify for deletion (default: 7).
              Must be >= 1 to prevent accidental wholesale deletion.
            - dry_run (bool): If True, only count entries that would be deleted (default: False)

    Returns:
        dict: Task result dictionary with cleanup statistics

    Raises:
        ValueError: If days_old is less than 1.
    """
    from ansible_base.activitystream.models import Entry as ActivityStreamEntry

    days_old = kwargs.get("days_old", 7)
    dry_run = kwargs.get("dry_run", False)

    if not isinstance(days_old, int) or days_old < 1:
        raise ValueError(f"days_old must be a positive integer (got {days_old!r})")

    log_task_execution(
        "cleanup_activitystream",
        "processing",
        f"Cleaning up ActivityStream entries older than {days_old} days",
    )

    cutoff_date = timezone.now() - timedelta(days=days_old)
    old_entries = ActivityStreamEntry.objects.filter(created__lt=cutoff_date)
    found = old_entries.count()
    deleted = 0

    if not dry_run and found > 0:
        _, deletion_info = old_entries.delete()
        deleted = deletion_info.get("dab_activitystream.Entry", 0)
        log_task_execution("cleanup_activitystream", "completed", f"Deleted {deleted} ActivityStream entries")
    else:
        log_task_execution(
            "cleanup_activitystream", "completed", f"Found {found} ActivityStream entries that would be deleted"
        )

    return create_task_result(
        "success",
        {
            "days_old": days_old,
            "cutoff_date": cutoff_date.isoformat(),
            "dry_run": dry_run,
            "found": found,
            "deleted": deleted,
        },
    )
