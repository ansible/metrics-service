"""Read-only collectors for the support bundle.

Every collector is safe to run against a live instance: no locks are taken, no
rows are written, and dispatcherd control calls are bounded and fail open to
database-only data.
"""

from __future__ import annotations

import importlib.metadata
import os
import platform
import socket
from datetime import UTC, date, datetime
from typing import Any

import yaml
from django import get_version as django_version
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Max
from django.utils import timezone as django_timezone

from apps.analytics.models import AnalyticsPayload
from apps.core.json_utils import to_jsonable
from apps.core.support_bundle.redaction import redact_settings
from apps.tasks.dispatcherd_config import ensure_dispatcherd_configured, get_config_file_path
from apps.tasks.models import (
    AnonymizedMetricsPayload,
    DailyMetricsSummary,
    HourlyMetricsCollection,
    Task,
    TaskExecution,
)
from apps.tasks.tasks import TASK_METADATA, get_queue_for_function

try:  # pragma: no cover - dispatcherd is a hard dependency, guarded for import safety
    from dispatcherd.factories import get_control_from_settings
except ImportError:  # pragma: no cover
    get_control_from_settings = None

DEFAULT_TASK_TIMEOUT = 3600
CONTROL_TIMEOUT_SECONDS = 2
MAX_TASK_ROWS = 500
MAX_HISTORY_ROWS = 100
MAX_DAILY_SUMMARIES = 30
MAX_SEGMENT_ROWS = 30


def _now() -> datetime:
    return django_timezone.now()


def _iso(value: Any) -> Any:
    """Convert datetimes/dates to ISO strings; leave everything else unchanged."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _package_version() -> str | None:
    try:
        return importlib.metadata.version("metrics-service")
    except importlib.metadata.PackageNotFoundError:
        return None


def collect_meta() -> dict:
    """Runtime metadata shared by every section of the bundle."""
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "metrics_service_version": _package_version(),
        "django_version": django_version(),
        "python_version": platform.python_version(),
        "task_timeout_seconds": getattr(settings, "TASK_TIMEOUT", DEFAULT_TASK_TIMEOUT),
        "bundle_format_version": 1,
    }


def _control_reply(command: str, timeout: int = CONTROL_TIMEOUT_SECONDS) -> dict:
    """Send one bounded dispatcherd control command and return its reply payload."""
    if get_control_from_settings is None:  # pragma: no cover
        raise RuntimeError("dispatcherd is not available")
    control = get_control_from_settings()
    replies = control.control_with_reply(command, timeout=timeout)
    if not replies:
        return {}
    reply = replies[0]
    return reply if isinstance(reply, dict) else {"result": reply}


def _dispatcherd_uuid_by_function(running: dict) -> dict[str, str]:
    """Map function name -> task uuid when exactly one dispatcherd task matches."""
    matches: dict[str, list[str]] = {}
    for value in running.values():
        if not isinstance(value, dict):
            continue
        function_name = value.get("task")
        task_uuid = value.get("uuid")
        if function_name and task_uuid:
            matches.setdefault(function_name, []).append(str(task_uuid))
    return {name: uuids[0] for name, uuids in matches.items() if len(uuids) == 1}


def _open_worker_ids(task_ids: list[int]) -> dict[int, str | None]:
    """Return the latest open execution's worker_id keyed by task id."""
    worker_ids: dict[int, str | None] = {}
    executions = (
        TaskExecution.objects.filter(task_id__in=task_ids, completed_at__isnull=True)
        .order_by("task_id", "-started_at")
        .values("task_id", "worker_id")
    )
    for execution in executions:
        worker_ids.setdefault(execution["task_id"], execution["worker_id"])
    return worker_ids


def _task_row(task: Task, now: datetime, timeout: int, worker_id: str | None, current_task_uuid: str | None) -> dict:
    duration = (now - task.started_at).total_seconds() if task.started_at else None
    stuck = task.status == "running" and task.started_at is not None and duration is not None and duration > timeout
    return {
        "task_id": task.pk,
        "name": task.name,
        "function_name": task.function_name,
        "status": task.status,
        "started_at": _iso(task.started_at),
        "duration_seconds": duration,
        "attempts": task.attempts,
        "worker_id": worker_id,
        "current_task_uuid": current_task_uuid if task.status == "running" else None,
        "stuck": stuck,
        "source": "db",
    }


def collect_tasks() -> dict:
    """Dispatcherd running state merged with database task truth."""
    timeout = int(getattr(settings, "TASK_TIMEOUT", DEFAULT_TASK_TIMEOUT))
    now = _now()

    running: dict = {}
    try:
        ensure_dispatcherd_configured()
        running = _control_reply("running")
        workers = _control_reply("workers")
        dispatcherd = {"available": True, "running": running, "workers": workers}
    except Exception as exc:  # noqa: BLE001 - never fail the bundle on control errors
        dispatcherd = {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    tasks = list(Task.objects.filter(status__in=["pending", "running"]).order_by("id")[:MAX_TASK_ROWS])
    worker_ids = _open_worker_ids([task.pk for task in tasks])
    uuids = _dispatcherd_uuid_by_function(running)
    rows = [_task_row(task, now, timeout, worker_ids.get(task.pk), uuids.get(task.function_name)) for task in tasks]

    return {
        "task_timeout_seconds": timeout,
        "dispatcherd": dispatcherd,
        "tasks": rows,
        "stuck_task_ids": [row["task_id"] for row in rows if row["stuck"]],
        "task_count": len(rows),
    }


def _collector_state(collector_type: str) -> dict:
    base = HourlyMetricsCollection.objects.filter(collector_type=collector_type)
    last_success = base.filter(status__in=["collected", "processed"]).aggregate(latest=Max("collection_timestamp"))[
        "latest"
    ]
    last_failure = base.filter(status="failed").aggregate(latest=Max("collection_timestamp"))["latest"]

    consecutive_failures = 0
    recent_statuses = base.order_by("-collection_timestamp").values_list("status", flat=True)[:MAX_HISTORY_ROWS]
    for status in recent_statuses:
        if status != "failed":
            break
        consecutive_failures += 1

    last_error_message = (
        base.filter(status="failed").order_by("-collection_timestamp").values_list("error_message", flat=True).first()
    )
    return {
        "collector_type": collector_type,
        "last_success_at": _iso(last_success),
        "last_failure_at": _iso(last_failure),
        "consecutive_failures": consecutive_failures,
        "last_error_message": last_error_message or None,
    }


def _collect_daily_summaries() -> list[dict]:
    summaries = []
    for row in DailyMetricsSummary.objects.order_by("-summary_date")[:MAX_DAILY_SUMMARIES]:
        summaries.append(
            {
                "summary_date": _iso(row.summary_date),
                "status": row.status,
                "aggregation_completed_at": _iso(row.aggregation_completed_at),
                "hourly_collections_count": row.hourly_collections_count,
                "missing_hours_count": len(row.missing_hours or []),
                "error_message": row.error_message or None,
            }
        )
    return summaries


def _collect_segment_payloads() -> list[dict]:
    payloads = []
    summary_dates = (
        AnonymizedMetricsPayload.objects.values_list("summary_date", flat=True)
        .distinct()
        .order_by("-summary_date")[:MAX_SEGMENT_ROWS]
    )
    for summary_date in summary_dates:
        row = AnonymizedMetricsPayload.objects.filter(summary_date=summary_date).order_by("-created").first()
        if row is None:  # pragma: no cover - distinct() guarantees a row
            continue
        # anonymized_data is intentionally never serialized.
        payloads.append(
            {
                "summary_date": _iso(row.summary_date),
                "status": row.status,
                "retry_count": row.retry_count,
                "sent_at": _iso(row.sent_at),
                "error_message": row.error_message or None,
            }
        )
    return payloads


def _collect_analytics_payloads() -> list[dict]:
    payloads = []
    collector_names = AnalyticsPayload.objects.values_list("collector", flat=True).distinct().order_by("collector")
    for collector in collector_names:
        row = AnalyticsPayload.objects.filter(collector=collector).order_by("-finished_at").first()
        if row is None:  # pragma: no cover - distinct() guarantees a row
            continue
        payloads.append(
            {
                "collector": row.collector,
                "cluster_id": row.cluster_id,
                "source": row.source,
                "finished_at": _iso(row.finished_at),
            }
        )
    return payloads


def collect_ingestion() -> dict:
    """Per-collector ingestion health.

    ``cluster_id`` from analytics payloads is the closest available customer
    dimension; metrics-service has no tenant model.
    """
    collector_types = (
        HourlyMetricsCollection.objects.values_list("collector_type", flat=True).distinct().order_by("collector_type")
    )
    return {
        "dimension": "collector",
        "note": "metrics-service has no tenant model; cluster_id is reported where analytics payloads provide it",
        "collectors": [_collector_state(collector_type) for collector_type in collector_types],
        "daily_summaries": _collect_daily_summaries(),
        "segment": _collect_segment_payloads(),
        "analytics_payloads": _collect_analytics_payloads(),
    }


def _configured_channels() -> list[str]:
    """Read queue channel names from the dispatcherd YAML config, when present."""
    try:
        with open(get_config_file_path()) as config_file:
            config = yaml.safe_load(config_file) or {}
    except Exception:  # noqa: BLE001 - a missing/invalid config must not break the bundle
        return []
    broker = config.get("brokers", {}).get("pg_notify", {}) or {}
    return [str(channel) for channel in broker.get("channels", []) or []]


def _pending_counts(queue_names: list[str]) -> dict[str, int]:
    counts = {name: 0 for name in queue_names}
    pending_functions = Task.objects.filter(status="pending").values_list("function_name", flat=True)
    for function_name in pending_functions:
        queue_name = get_queue_for_function(function_name)
        counts[queue_name] = counts.get(queue_name, 0) + 1
    return counts


def collect_queues() -> dict:
    """Pending job counts per queue, plus live dispatcherd queue state."""
    queue_names = set(_configured_channels())
    queue_names.update(get_queue_for_function(function_name) for function_name in TASK_METADATA)
    ordered_queues = sorted(queue_names)
    counts = _pending_counts(ordered_queues)

    live: dict = {"available": False}
    try:
        ensure_dispatcherd_configured()
        running = _control_reply("running")
        workers = _control_reply("workers")
        producers = _control_reply("producers")
        queued = sum(1 for key in running if key.startswith("queued-"))
        blocked = sum(1 for key in running if key.startswith("blocked-"))
        delayed = sum(1 for key in running if key.startswith("delayed-"))
        live = {
            "available": True,
            "queued": queued,
            "blocked": blocked,
            "delayed": delayed,
            "workers": workers,
            "producers": producers,
        }
    except Exception as exc:  # noqa: BLE001 - control errors fall back to DB-only data
        live = {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    return {
        "queues": [{"name": name, "db_pending": counts.get(name, 0)} for name in ordered_queues],
        "db_pending_total": sum(counts.values()),
        "dispatcherd": live,
        "live_available": bool(live.get("available")),
    }


def _database_version() -> Any:
    if connection.vendor == "postgresql":
        return getattr(connection, "pg_version", None)
    if connection.vendor == "sqlite":
        return getattr(getattr(connection, "Database", None), "sqlite_version", None)
    return None


def _migration_names() -> tuple[list[str], list[str]]:
    applied = MigrationRecorder(connection).applied_migrations()
    applied_nodes = set(applied)
    graph_nodes = {node for node in MigrationExecutor(connection).loader.graph.nodes if node[1] is not None}
    applied_names = sorted(f"{app}.{name}" for app, name in applied_nodes if name is not None)
    unapplied_names = sorted(f"{app}.{name}" for app, name in (graph_nodes - applied_nodes))
    return applied_names, unapplied_names


def collect_schema() -> dict:
    """Database connectivity, server version, and migration state."""
    database = settings.DATABASES.get("default", {})
    result: dict[str, Any] = {
        "connected": False,
        "django_version": django_version(),
        "python_version": platform.python_version(),
        "metrics_service_version": _package_version(),
        "database": {
            "engine": database.get("ENGINE"),
            "name": database.get("NAME"),
            "host": database.get("HOST"),
            "port": database.get("PORT"),
        },
    }
    try:
        connection.ensure_connection()
        applied, unapplied = _migration_names()
        result.update(
            {
                "connected": True,
                "vendor": connection.vendor,
                "version": _database_version(),
                "applied_migrations": applied,
                "unapplied_migrations": unapplied,
                "applied_migrations_count": len(applied),
                "unapplied_migrations_count": len(unapplied),
            }
        )
    except Exception as exc:  # noqa: BLE001 - report the failure instead of aborting the bundle
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _safe_jsonable(value: Any) -> Any:
    if callable(value):
        return repr(value)
    try:
        return to_jsonable(value)
    except Exception:  # noqa: BLE001 - fall back to a readable representation
        return repr(value)


def collect_settings() -> dict:
    """Fully loaded settings with secrets redacted."""
    from metrics_service.settings import DYNACONF

    raw = {str(key): _safe_jsonable(value) for key, value in DYNACONF.as_dict().items()}
    redacted, summary = redact_settings(raw)
    return {
        "settings": redacted,
        "_redaction": summary,
    }
