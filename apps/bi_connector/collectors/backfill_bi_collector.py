"""
Backfill task for existing hourly/daily collectors.

Drives collect_hourly_metrics or collect_snapshot_metrics over an explicit
date range, committing one period at a time and tracking progress in a
CollectionBatch so a failure resumes from the last committed point.

This writes into the existing HourlyMetricsCollection model — not into the
new billing storage models. Use collect_bi_billing_data for billing collectors.
"""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.utils.timezone import now

from apps.tasks.utils import parse_datetime_string

if TYPE_CHECKING:
    from apps.bi_connector.models import CollectionBatch

logger = logging.getLogger(__name__)

SNAPSHOT_COLLECTORS = frozenset(
    {
        "execution_environments",
        "config",
        "controller_version_service",
        "table_metadata",
        "feature_flags_service",
    }
)

# All collector types accepted by backfill_bi_collector.
ALLOWED_BACKFILL_COLLECTOR_TYPES = SNAPSHOT_COLLECTORS | frozenset(
    {
        "job_host_summary_service",
        "unified_jobs",
        "credentials_service",
        "main_jobevent_service",
        "task_executions_service",
    }
)


def _load_batch(batch_id: int | None) -> "CollectionBatch | None":
    """Load a CollectionBatch by PK, mark it running, and return it (or None)."""
    if batch_id is None:
        return None
    from apps.bi_connector.models import CollectionBatch

    batch = CollectionBatch.objects.get(pk=batch_id)
    batch.status = "running"
    batch.started_at = now()
    batch.save(update_fields=["status", "started_at", "modified"])
    return batch


def _resume_cursor(batch: "CollectionBatch | None", since: datetime) -> datetime:
    """Return the datetime to resume from, honoring batch.cursor if set."""
    if batch and batch.cursor and "last_committed" in batch.cursor:
        resumed = parse_datetime_string(batch.cursor["last_committed"])
        return resumed if resumed is not None else since
    return since


def _collect_one_window(is_snapshot: bool, collector_type: str, current: datetime) -> None:
    """Dispatch a single collection window to the appropriate collector."""
    from apps.tasks.collectors.collect_hourly_metrics import collect_hourly_metrics
    from apps.tasks.collectors.collect_snapshot_metrics import collect_snapshot_metrics

    if is_snapshot:
        collect_snapshot_metrics(
            collector_type=collector_type,
            collection_timestamp=current.isoformat(),
        )
    else:
        collect_hourly_metrics(
            collector_type=collector_type,
            hour_timestamp=current.isoformat(),
        )


def _run_collection_loop(
    collector_type: str, since: datetime, until: datetime, batch: "CollectionBatch | None"
) -> int:
    """
    Iterate over all time windows between *since* and *until*, calling the
    appropriate collector for each, and committing batch progress after each window.

    Returns the number of periods collected.
    """
    is_snapshot = collector_type in SNAPSHOT_COLLECTORS
    step = timedelta(days=1) if is_snapshot else timedelta(hours=1)
    current = _resume_cursor(batch, since)
    periods_collected = 0

    while current < until:
        window_end = min(current + step, until)
        _collect_one_window(is_snapshot, collector_type, current)
        periods_collected += 1

        if batch is not None:
            batch.cursor = {"last_committed": window_end.isoformat()}
            batch.records_imported = (batch.records_imported or 0) + 1
            batch.save(update_fields=["cursor", "records_imported", "modified"])

        current = window_end

    return periods_collected


def backfill_bi_collector(task_data: dict | None = None, **kwargs) -> dict:
    """
    Backfill an existing collector over a historical date range.

    task_data keys:
        collector_type (str)  — must be a key in TASK_FUNCTIONS (hourly or snapshot)
        since          (str)  — ISO 8601 start datetime (inclusive)
        until          (str)  — ISO 8601 end datetime (exclusive)
        batch_id       (int)  — optional CollectionBatch PK for progress tracking
    """
    task_data = task_data or {}

    collector_type: str | None = task_data.get("collector_type")
    since_str: str | None = task_data.get("since")
    until_str: str | None = task_data.get("until")
    batch_id: int | None = task_data.get("batch_id")

    if not collector_type:
        raise ValueError("collector_type is required in task_data")
    if collector_type not in ALLOWED_BACKFILL_COLLECTOR_TYPES:
        raise ValueError(
            f"Unknown collector_type: {collector_type!r}. "
            f"Valid types: {sorted(ALLOWED_BACKFILL_COLLECTOR_TYPES)}"
        )
    if not since_str or not until_str:
        raise ValueError("since and until are required in task_data")

    since = parse_datetime_string(since_str)
    until = parse_datetime_string(until_str)
    if since is None:
        raise ValueError(f"Invalid since datetime: {since_str!r}")
    if until is None:
        raise ValueError(f"Invalid until datetime: {until_str!r}")
    if since >= until:
        raise ValueError(f"'since' must be before 'until', got since={since!r}, until={until!r}")

    batch = _load_batch(batch_id)

    try:
        periods_collected = _run_collection_loop(collector_type, since, until, batch)
    except Exception as exc:
        if batch is not None:
            batch.status = "failed"
            batch.error_message = str(exc)
            batch.save(update_fields=["status", "error_message", "modified"])
        raise

    if batch is not None:
        batch.status = "completed"
        batch.completed_at = now()
        batch.save(update_fields=["status", "completed_at", "modified"])

    logger.info(
        "backfill_bi_collector: completed %d periods for collector_type=%s",
        periods_collected,
        collector_type,
    )

    return {
        "status": "success",
        "periods_collected": periods_collected,
        "collector_type": collector_type,
    }
