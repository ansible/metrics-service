"""Atomic coordination for on-demand analytics collection."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.analytics.models import LOCAL_SOURCE, AnalyticsCollectionClaim


def _is_stale(claim: AnalyticsCollectionClaim, now: datetime | None = None) -> bool:
    """Return whether an active claim has outlived the task execution timeout."""
    if claim.status not in {"pending", "running"}:
        return False
    now = now or timezone.now()
    stale_after = getattr(settings, "ANALYTICS_ON_DEMAND_CLAIM_STALE_AFTER", 3600)
    return claim.modified <= now - timedelta(seconds=stale_after)


def acquire_claim(
    *,
    collector: str,
    since: datetime | None,
    until: datetime | None,
    task_factory: Callable[[], object],
    source: str = LOCAL_SOURCE,
) -> tuple[AnalyticsCollectionClaim, str]:
    """Create or reuse a claim and its task under one transaction.

    The unique digest handles concurrent inserts. The nested savepoint lets the losing request
    recover from the expected uniqueness error without breaking the surrounding transaction.
    """
    claim_key = AnalyticsCollectionClaim.make_key(collector, source, since, until)
    with transaction.atomic():
        try:
            with transaction.atomic():
                claim = AnalyticsCollectionClaim.objects.create(
                    claim_key=claim_key,
                    collector=collector,
                    source=source,
                    since=since,
                    until=until,
                )
            claim.task = task_factory()
            claim.save(update_fields=["task", "modified"])
            return claim, "created"
        except IntegrityError:
            claim = AnalyticsCollectionClaim.objects.select_for_update().get(claim_key=claim_key)

        task = claim.task
        if claim.status == "completed" and claim.payload_id:
            return claim, "completed"
        if (
            claim.status in {"pending", "running"}
            and task is not None
            and task.status in {"pending", "running"}
            and not _is_stale(claim)
        ):
            return claim, "existing"

        previous_status = claim.status
        claim.status = "pending"
        claim.task = task_factory()
        claim.payload = None
        claim.error_message = ""
        claim.save(update_fields=["status", "task", "payload", "error_message", "modified"])
        return claim, "recovered" if previous_status in {"pending", "running"} else "retry"


def claim_for_execution(execution_id: int | None) -> AnalyticsCollectionClaim | None:
    """Find the claim belonging to a dispatched task execution, if any."""
    if not execution_id:
        return None
    from apps.tasks.models import TaskExecution

    try:
        execution = TaskExecution.objects.select_related("task").get(pk=execution_id)
    except TaskExecution.DoesNotExist:
        return None
    return AnalyticsCollectionClaim.objects.filter(task=execution.task).first()


def start_claim(claim: AnalyticsCollectionClaim) -> bool:
    """Move a pending claim to running, refusing a claim superseded by stale recovery."""
    updated = AnalyticsCollectionClaim.objects.filter(pk=claim.pk, task=claim.task, status="pending").update(
        status="running", modified=timezone.now()
    )
    if updated:
        return True
    claim.refresh_from_db()
    return claim.task_id == getattr(claim.task, "pk", None) and claim.status == "running"


def finish_claim(
    claim: AnalyticsCollectionClaim,
    *,
    status: str,
    payload=None,
    error_message: str = "",
) -> None:
    """Record the terminal result only if this task still owns the claim."""
    AnalyticsCollectionClaim.objects.filter(pk=claim.pk, task=claim.task).update(
        status=status,
        payload=payload,
        error_message=error_message,
        modified=timezone.now(),
    )
