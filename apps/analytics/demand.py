"""Helpers for resolving analytics collection demand against existing tasks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.utils import timezone

from apps.analytics.registry import CollectorEntry
from apps.tasks.models import Task
from apps.tasks.utils import parse_datetime_string

logger = logging.getLogger(__name__)

_TASK_FUNCTIONS = {
    "hourly": "collect_hourly_metrics",
    "daily": "collect_daily_metrics",
    "snapshot": "collect_snapshot_metrics",
}


@dataclass(frozen=True)
class CollectionWindow:
    """A canonical half-open collection window."""

    since: datetime
    until: datetime


@dataclass(frozen=True)
class TaskPeriod:
    """Resolved period metadata for a task involving one collector."""

    window: CollectionWindow | None = None
    snapshot_at: datetime | None = None
    resolvable: bool = True


def _utc(value: datetime) -> datetime:
    """Return an aware UTC datetime."""
    if timezone.is_naive(value):
        value = timezone.make_aware(value, UTC)
    return value.astimezone(UTC)


def _floor_hour(value: datetime) -> datetime:
    """Return the UTC hour boundary containing ``value``."""
    value = _utc(value)
    return value.replace(minute=0, second=0, microsecond=0)


def _floor_day(value: datetime) -> datetime:
    """Return the UTC day boundary containing ``value``."""
    value = _utc(value)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def previous_and_current_windows(mode: str, now: datetime) -> tuple[CollectionWindow, CollectionWindow]:
    """Return the previous and current canonical windows for a windowed mode."""
    if mode == "hourly":
        current_start = _floor_hour(now)
        size = timedelta(hours=1)
    elif mode == "daily":
        current_start = _floor_day(now)
        size = timedelta(days=1)
    else:
        raise ValueError(f"Mode does not have collection windows: {mode}")

    return (
        CollectionWindow(current_start - size, current_start),
        CollectionWindow(current_start, current_start + size),
    )


def _parse_task_timestamp(task: Task, key: str) -> datetime | None:
    """Parse a task timestamp, logging malformed persisted metadata."""
    raw_value = (task.task_data or {}).get(key)
    if not raw_value:
        return None
    parsed = parse_datetime_string(raw_value)
    if parsed is None:
        logger.warning("Unable to resolve analytics task %s: invalid %s=%r", task.pk, key, raw_value)
    return parsed


def _task_targets_entry(entry: CollectorEntry, task: Task) -> bool:
    """Return whether task metadata identifies the requested collector."""
    data = task.task_data or {}
    if task.function_name == "collect_analytics_on_demand":
        return data.get("collector") == entry.name
    return task.function_name == _TASK_FUNCTIONS.get(entry.mode) and data.get("collector_type") == entry.collector_type


def _resolve_on_demand_period(entry: CollectorEntry, task: Task) -> TaskPeriod:
    """Resolve the period of an analytics on-demand task."""
    data = task.task_data or {}
    if not entry.accepts_since_until:
        return TaskPeriod(snapshot_at=_utc(task.created))

    since = _parse_task_timestamp(task, "since")
    until = _parse_task_timestamp(task, "until")
    invalid_since = "since" in data and data["since"] is not None and since is None
    invalid_until = "until" in data and data["until"] is not None and until is None
    if invalid_since or invalid_until:
        return TaskPeriod(resolvable=False)
    if since is None or until is None:
        # Open-ended custom POST windows are valid, but cannot equal a canonical demand window.
        return TaskPeriod()
    return TaskPeriod(window=CollectionWindow(_utc(since), _utc(until)))


def _resolve_windowed_period(entry: CollectorEntry, task: Task, now: datetime) -> TaskPeriod:
    """Resolve the period of a regular hourly or daily task."""
    data = task.task_data or {}
    reference = _utc(task.scheduled_time or now)
    timestamp = _parse_task_timestamp(task, "hour_timestamp")
    if data.get("hour_timestamp") and timestamp is None:
        return TaskPeriod(resolvable=False)

    if entry.mode == "hourly":
        start = _utc(timestamp) if timestamp else _floor_hour(reference) - timedelta(hours=1)
        return TaskPeriod(window=CollectionWindow(start, start + timedelta(hours=1)))

    until = _utc(timestamp) if timestamp else _floor_day(reference)
    return TaskPeriod(window=CollectionWindow(until - timedelta(days=1), until))


def _resolve_snapshot_period(task: Task) -> TaskPeriod:
    """Resolve the freshness timestamp of a regular snapshot task."""
    collection_timestamp = _parse_task_timestamp(task, "collection_timestamp")
    if (task.task_data or {}).get("collection_timestamp") and collection_timestamp is None:
        return TaskPeriod(resolvable=False)
    # Demand freshness is based on when the task was created. collection_timestamp identifies the
    # rollup day, which is intentionally different from the snapshot's actual execution age.
    return TaskPeriod(snapshot_at=_utc(task.created))


def resolve_task_period(entry: CollectorEntry, task: Task, now: datetime) -> TaskPeriod | None:
    """Resolve a task's intended collection period without changing task semantics.

    ``hour_timestamp`` is the start of an hourly window and the end of a daily window. Tasks
    without an explicit timestamp retain their existing fallback behavior: the previous period
    relative to their scheduled time, or relative to ``now`` for immediate tasks.
    """
    if not _task_targets_entry(entry, task):
        return None

    if task.function_name == "collect_analytics_on_demand":
        return _resolve_on_demand_period(entry, task)

    if task.cron_expression:
        # A recurring template describes future executions, not one concrete period.
        return TaskPeriod()

    if entry.mode in ("hourly", "daily"):
        return _resolve_windowed_period(entry, task, now)
    return _resolve_snapshot_period(task)


def relevant_tasks(entry: CollectorEntry):
    """Return all task rows that may represent work for ``entry``."""
    function_names = {"collect_analytics_on_demand", _TASK_FUNCTIONS[entry.mode]}
    return Task.objects.filter(function_name__in=function_names).order_by("id")


def has_cron_template(entry: CollectorEntry) -> bool:
    """Return whether an enabled recurring task template covers this collector."""
    return (
        relevant_tasks(entry)
        .filter(status="pending", cron_expression__isnull=False)
        .exclude(cron_expression="")
        .filter(task_data__collector_type=entry.collector_type)
        .exists()
    )
