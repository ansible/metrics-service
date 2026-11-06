"""Read-only collectors for the support bundle.

Every collector is safe to run against a live instance: no locks are taken, no
rows are written, and dispatcherd control calls are bounded and fail open to
database-only data. The total dispatcherd probe budget is
:data:`CONTROL_TOTAL_TIMEOUT_SECONDS` per collector, shared across every control
command, so a hung or absent broker cannot stall the bundle.
"""

from __future__ import annotations

import importlib.metadata
import os
import platform
import socket
import time
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
#: Per-command wait, and the shared budget for all control commands in one collector.
CONTROL_TIMEOUT_SECONDS = 2
CONTROL_TOTAL_TIMEOUT_SECONDS = 5

#: Ask for replies from every dispatcherd node; the timeout, not this number, is
#: the real bound (a single-node deployment simply waits out the command timeout).
MAX_CONTROL_REPLIES = 64

#: Keys dispatcherd puts in a reply to identify the node that sent it. They are
#: reported separately in ``nodes`` so multi-node payloads do not overwrite them.
NODE_ID_KEYS = ("node_id", "node", "hostname")

#: Keys present in an echo of the control *request* (``{"control": ...,
#: "reply_to": ...}``). A payload carrying nothing else is not evidence that a
#: worker or producer is alive, so it must not make ``available`` true.
CONTROL_ECHO_KEYS = frozenset({"control", "reply_to", "data"})

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


def _normalise_reply(reply: Any) -> dict:
    return reply if isinstance(reply, dict) else {"result": reply}


def _is_state_reply(reply: dict) -> bool:
    """False for a bare echo of the control request (no node state at all)."""
    return bool(set(reply) - CONTROL_ECHO_KEYS)


def _probe_control(
    commands: tuple[str, ...],
    timeout: float = CONTROL_TIMEOUT_SECONDS,
    total_timeout: float = CONTROL_TOTAL_TIMEOUT_SECONDS,
) -> dict[str, list[dict]]:
    """Send *commands* over one control connection and collect **every** reply.

    All commands share a single deadline of *total_timeout* seconds, so a dead
    broker costs at most that once per collector instead of ``len(commands) *
    timeout``. ``expected_replies`` is set high so multi-node deployments return
    one reply per node rather than silently reporting only the first; the
    per-command *timeout* is what actually bounds the wait.

    Returns ``{command: [reply, ...]}``; a command that could not start before
    the deadline maps to an empty list. Bare control-request echoes are dropped
    so they cannot be mistaken for a live node.
    """
    if get_control_from_settings is None:  # pragma: no cover
        raise RuntimeError("dispatcherd is not available")
    control = get_control_from_settings()
    deadline = time.monotonic() + total_timeout
    replies: dict[str, list[dict]] = {}
    for command in commands:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            replies[command] = []
            continue
        raw = control.control_with_reply(
            command,
            expected_replies=MAX_CONTROL_REPLIES,
            timeout=min(timeout, remaining),
        )
        replies[command] = [reply for reply in map(_normalise_reply, raw or []) if _is_state_reply(reply)]
    return replies


def _merge_replies(replies: list[dict]) -> dict:
    """Merge per-node reply mappings into one mapping (first node wins a clash)."""
    merged: dict = {}
    for reply in replies:
        for key, value in reply.items():
            if key in NODE_ID_KEYS:
                continue
            merged.setdefault(str(key), value)
    return merged


def _node_ids(replies: dict[str, list[dict]]) -> list[str]:
    """Sorted node identifiers seen in any reply (empty when the nodes omit them)."""
    nodes: set[str] = set()
    for reply_list in replies.values():
        for reply in reply_list:
            for key in NODE_ID_KEYS:
                value = reply.get(key)
                if isinstance(value, str) and value:
                    nodes.add(value)
    return sorted(nodes)


def _dispatcherd_state(replies: dict[str, list[dict]]) -> dict:
    """Summarise a probe: availability, node count, and per-command reply counts.

    ``available`` is only true when dispatcherd actually answered something --
    an absent daemon returns ``[]`` from the broker after the timeout without
    raising, which must not be reported as a healthy idle system.
    """
    reply_counts = {command: len(reply_list) for command, reply_list in replies.items()}
    nodes = _node_ids(replies)
    available = any(reply_counts.values())
    state: dict[str, Any] = {
        "available": available,
        "partial": available and any(count == 0 for count in reply_counts.values()),
        "nodes": nodes,
        "node_count": len(nodes),
        "reply_counts": reply_counts,
    }
    if not available:
        state["error"] = "no replies from dispatcherd (control timeout)"
    return state


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
        replies = _probe_control(("running", "workers"))
        running = _merge_replies(replies["running"])
        dispatcherd = {
            "running": running,
            "workers": _merge_replies(replies["workers"]),
            **_dispatcherd_state(replies),
        }
    except Exception as exc:  # noqa: BLE001 - never fail the bundle on control errors
        dispatcherd = {
            "available": False,
            "partial": False,
            "nodes": [],
            "node_count": 0,
            "error": f"{type(exc).__name__}: {exc}",
            "running": {},
            "workers": {},
        }

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
        replies = _probe_control(("running", "workers", "producers"))
        running_replies = replies["running"]
        queued = sum(1 for reply in running_replies for key in reply if str(key).startswith("queued-"))
        blocked = sum(1 for reply in running_replies for key in reply if str(key).startswith("blocked-"))
        delayed = sum(1 for reply in running_replies for key in reply if str(key).startswith("delayed-"))
        live = {
            "queued": queued,
            "blocked": blocked,
            "delayed": delayed,
            "workers": _merge_replies(replies["workers"]),
            "producers": _merge_replies(replies["producers"]),
            **_dispatcherd_state(replies),
        }
    except Exception as exc:  # noqa: BLE001 - control errors fall back to DB-only data
        live = {
            "available": False,
            "partial": False,
            "nodes": [],
            "node_count": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }

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
