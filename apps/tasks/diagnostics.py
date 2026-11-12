"""
Read-only diagnostics for the task system.

The functions in this module answer the four questions support asks first when a
task issue is reported:

* Which tasks are stuck (and for how long)?
* When did each task type last succeed?
* How many failures has each task type had recently?
* How deep are the dispatcherd queues?

Everything here is a pure read: nothing is marked failed or otherwise mutated.
The scheduler owns state transitions. Functions return plain JSON-serializable
dicts so the same data can back an HTTP endpoint later.
"""

import logging
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max
from django.db.utils import NotSupportedError
from django.utils import timezone

from apps.tasks.models import Task, TaskExecution

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

# Fallback queue registry, used only when apps/settings/dispatcherd.yaml cannot
# be read. The authoritative list is the pg_notify broker ``channels`` entry in
# that file, which is what dispatcherd actually listens on.
_DEFAULT_QUEUES = ("dashboard", "maintenance", "metrics")

# Live dispatcherd keys classify into these buckets; "worker-" keys are actively executing.
_LIVE_BUCKETS = ("queued", "blocked", "delayed")

#: Keys dispatcherd adds *around* the per-command payload, i.e. reply metadata
#: rather than worker/producer records. ``node_id`` is injected by
#: ``DispatcherMain.run_control_action()`` (``dispatcherd/service/main.py``), and
#: ``error`` is what ``service/control_tasks.py`` returns for an unknown control
#: method or what ``Control.parse_replies()`` returns for an unparseable payload.
REPLY_METADATA_KEYS = frozenset({"node_id", "node", "hostname", "control", "reply_to", "control_data", "data", "error"})

#: The keys ``Control.create_message()`` puts in a control *request*. With the
#: pg_notify broker and ``Control.queuename is None`` (this deployment's config)
#: the publisher channel resolves to the reply queue itself, so the broker
#: republishes the request straight back to the caller. A reply carrying nothing
#: beyond these keys is that echo, not evidence that a worker or producer lives.
CONTROL_ECHO_KEYS = frozenset({"control", "reply_to", "control_data", "data"})


def _iso(value):
    """Serialize a datetime to ISO-8601, passing None through."""
    return value.isoformat() if value is not None else None


def _truncate_error(message, limit: int = 200) -> str:
    """Collapse whitespace/newlines and truncate an error message for display."""
    if not message:
        return ""
    collapsed = " ".join(str(message).split())
    if len(collapsed) > limit:
        return collapsed[: limit - 3] + "..."
    return collapsed


def get_known_queues() -> tuple[str, ...]:
    """Return the configured dispatcherd queue names.

    Queue names live in ``apps/settings/dispatcherd.yaml`` (the pg_notify broker
    ``channels``), which is the single source of truth for what dispatcherd
    listens on. Reading it keeps this module aligned with the dispatcher
    instead of duplicating a hard-coded list. If the file is missing or
    unreadable, fall back to ``_DEFAULT_QUEUES`` so diagnostics still render.
    """
    try:
        import yaml

        from apps.tasks.dispatcherd_config import get_config_file_path

        config_file = get_config_file_path()
        if config_file.is_file():
            with config_file.open(encoding="utf-8") as handle:
                config = yaml.safe_load(handle) or {}
            channels = (config.get("brokers") or {}).get("pg_notify", {}).get("channels") or []
            queues = tuple(str(channel) for channel in channels if channel)
            if queues:
                return queues
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        logger.warning("Could not read dispatcherd queue names from config: %s", exc)
    return _DEFAULT_QUEUES


def _running_task_ids_by_live_key(live_state: dict | None) -> dict[int, list[str]]:
    """Map DB task IDs to the live dispatcherd keys reporting them."""
    reported: dict[int, list[str]] = {}
    if not live_state or not live_state.get("live_available"):
        return reported
    for key, message in (live_state.get("running") or {}).items():
        if not isinstance(message, dict):
            continue
        task_id = (message.get("kwargs") or {}).get("task_id")
        if task_id is None:
            continue
        reported.setdefault(int(task_id), []).append(str(key))
    return reported


def get_stuck_tasks(
    stuck_timeout: int | None = None,
    limit: int | None = 20,
    now=None,
    live_state: dict | None = None,
) -> list[dict]:
    """Return running tasks that have exceeded ``stuck_timeout`` seconds."""
    now = now or timezone.now()
    timeout = settings.TASK_TIMEOUT if stuck_timeout is None else stuck_timeout
    threshold = now - timedelta(seconds=timeout)

    queryset = Task.objects.filter(
        status="running",
        started_at__isnull=False,
        started_at__lt=threshold,
    ).order_by("started_at")
    if limit:
        queryset = queryset[:limit]

    tasks = list(queryset)
    if not tasks:
        return []

    task_ids = [task.id for task in tasks]

    # Latest running execution per task supplies worker_id / execution_id.
    latest_executions: dict[int, TaskExecution] = {}
    executions = TaskExecution.objects.filter(task_id__in=task_ids, status="running").order_by("-started_at")
    for execution in executions:
        latest_executions.setdefault(execution.task_id, execution)

    reported_by_live_key = _running_task_ids_by_live_key(live_state)

    results = []
    for task in tasks:
        execution = latest_executions.get(task.id)
        results.append(
            {
                "task_id": task.id,
                "name": task.name,
                "function_name": task.function_name,
                "started_at": _iso(task.started_at),
                "duration_seconds": (now - task.started_at).total_seconds(),
                "attempts": task.attempts,
                "worker_id": execution.worker_id if execution else None,
                "execution_id": execution.id if execution else None,
                # Empty list means the DB says running but no worker reports it
                # (likely a dead worker); populated means a worker is executing it.
                "reported_by": reported_by_live_key.get(task.id, []),
            }
        )
    return results


def get_last_success_by_function(now=None) -> list[dict]:
    """Return the last successful completion time for every known task function.

    Functions that have never succeeded are included with ``last_success_at`` set
    to ``None`` — "never succeeded" is itself a useful diagnostic. Results are
    sorted stalest-first, with never-succeeded functions first.
    """
    from apps.tasks.tasks import TASK_FUNCTIONS

    now = now or timezone.now()

    aggregates = dict(
        TaskExecution.objects.filter(status="completed", completed_at__isnull=False)
        .values_list("task__function_name")
        .annotate(last_success_at=Max("completed_at"))
    )

    # Latest completing task name per function. distinct() on a field is
    # PostgreSQL-only; fall back to a bounded ordered scan elsewhere.
    task_names: dict[str, str] = {}
    completed = TaskExecution.objects.filter(status="completed", completed_at__isnull=False)
    try:
        latest_rows = list(
            completed.order_by("task__function_name", "-completed_at")
            .distinct("task__function_name")
            .values_list("task__function_name", "task__name", "completed_at")
        )
        for function_name, task_name, _completed_at in latest_rows:
            task_names[function_name] = task_name
    except NotSupportedError:
        seen: set[str] = set()
        for function_name, task_name in completed.order_by("-completed_at").values_list(
            "task__function_name", "task__name"
        ):
            if function_name not in seen:
                seen.add(function_name)
                task_names[function_name] = task_name

    rows = []
    for function_name in TASK_FUNCTIONS:
        last_success_at = aggregates.get(function_name)
        rows.append(
            {
                "function_name": function_name,
                "last_success_at": _iso(last_success_at),
                "age_seconds": (now - last_success_at).total_seconds() if last_success_at else None,
                "task_name": task_names.get(function_name),
            }
        )

    # Stalest first; never-succeeded rows sort before everything else.
    rows.sort(key=lambda row: (row["last_success_at"] is not None, row["last_success_at"] or ""))
    return rows


def get_failure_counts(hours: int = 24, limit: int | None = None, now=None) -> list[dict]:
    """Return failure counts per task function within the last ``hours`` hours."""
    now = now or timezone.now()
    since = now - timedelta(hours=hours)

    failures = TaskExecution.objects.filter(status="failed", completed_at__gte=since)
    aggregates = failures.values("task__function_name").annotate(
        failure_count=Count("id"), last_failure_at=Max("completed_at")
    )

    rows: dict[str, dict] = {}
    for aggregate in aggregates:
        function_name = aggregate["task__function_name"]
        if not function_name:
            continue
        rows[function_name] = {
            "function_name": function_name,
            "failure_count": aggregate["failure_count"],
            "legacy_task_failures": 0,
            "last_failure_at": _iso(aggregate["last_failure_at"]),
            "last_error": "",
        }

    # Latest error message per function.
    latest_errors: dict[str, str] = {}
    try:
        latest_rows = list(
            failures.order_by("task__function_name", "-completed_at")
            .distinct("task__function_name")
            .values_list("task__function_name", "error_message")
        )
        for function_name, error_message in latest_rows:
            if function_name:
                latest_errors[function_name] = error_message or ""
    except NotSupportedError:
        seen_errors: set[str] = set()
        for function_name, error_message in failures.order_by("-completed_at").values_list(
            "task__function_name", "error_message"
        ):
            if function_name and function_name not in seen_errors:
                seen_errors.add(function_name)
                latest_errors[function_name] = error_message or ""

    # Legacy/defensive: failed Task rows with no execution history at all.
    legacy_tasks = Task.objects.filter(status="failed", completed_at__gte=since, executions__isnull=True)
    for task in legacy_tasks:
        row = rows.setdefault(
            task.function_name,
            {
                "function_name": task.function_name,
                "failure_count": 0,
                "legacy_task_failures": 0,
                "last_failure_at": None,
                "last_error": "",
            },
        )
        row["failure_count"] += 1
        row["legacy_task_failures"] += 1
        task_completed_at = _iso(task.completed_at)
        if task_completed_at and (row["last_failure_at"] is None or task_completed_at > row["last_failure_at"]):
            row["last_failure_at"] = task_completed_at
            row["last_error"] = task.error_message or row["last_error"]

    for function_name, row in rows.items():
        row["last_error"] = _truncate_error(latest_errors.get(function_name) or row["last_error"])

    results = sorted(rows.values(), key=lambda row: row["last_failure_at"] or "", reverse=True)
    if limit:
        results = results[:limit]
    return results


def _control_replies(control, command: str, timeout: float) -> tuple[list, str | None]:
    """Issue one dispatcherd control command, returning ``(replies, error)``.

    A single failing command must not discard the replies of the others, so the
    exception is converted into an error string and an empty reply list.
    """
    try:
        return list(control.control_with_reply(command, timeout=timeout) or []), None
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        logger.warning("dispatcherd control command %r failed: %s", command, exc)
        return [], f"{type(exc).__name__}: {exc}"


def _is_state_reply(reply) -> bool:
    """True only for a reply that carries dispatcherd state.

    A bare echo of the control request (``{"control": ..., "reply_to": ...}``)
    proves nothing about the daemon: the pg_notify broker produces one even when
    no dispatcherd process is running. Anything beyond the request envelope --
    worker ids, producer names, or just the ``node_id`` a real daemon always
    stamps on its reply -- means something actually answered.
    """
    return isinstance(reply, dict) and bool(set(reply) - CONTROL_ECHO_KEYS)


def _merge_running_replies(replies: list) -> dict:
    """Merge ``running`` control replies into one key -> message mapping."""
    running: dict = {}
    for reply in replies:
        if not isinstance(reply, dict):
            continue
        for key, value in reply.items():
            if key in REPLY_METADATA_KEYS:
                continue
            running[str(key)] = value
    return running


def _merge_worker_replies(replies: list) -> tuple[list[dict], int]:
    """Extract worker records, dropping reply metadata and non-dict values.

    dispatcherd's own fallback reply is ``{'error': 'JSON parse error', ...}``;
    its values are strings. Only dict worker records are renderable, so the
    rest are counted and reported as a warning instead of crashing the report.
    A real reply also carries ``node_id`` (a string), which is reply metadata --
    not a malformed worker, and never a worker called ``node_id``.
    """
    workers: list[dict] = []
    malformed = 0
    for reply in replies:
        if not isinstance(reply, dict):
            continue
        for key, value in reply.items():
            if key in REPLY_METADATA_KEYS:
                continue
            if isinstance(value, dict):
                workers.append(value)
            else:
                malformed += 1
    return workers, malformed


def _merge_producer_replies(replies: list) -> list[dict]:
    """Flatten ``producers`` control replies into a list of producer records."""
    producers: list[dict] = []
    for reply in replies:
        if not isinstance(reply, dict):
            continue
        for name, data in reply.items():
            if name in REPLY_METADATA_KEYS:
                continue
            producer = {"producer": name}
            if isinstance(data, dict):
                producer.update(data)
            producers.append(producer)
    return producers


def get_dispatcherd_state(timeout: float = 2.0) -> dict:
    """Collect live dispatcherd state, degrading gracefully when unavailable.

    ``live_available`` is only ``True`` when dispatcherd actually answered at
    least one control command. With no daemon running the broker simply returns
    no replies after ``timeout`` instead of raising -- and, with the pg_notify
    broker, it returns the control *request* echoed back on the reply channel.
    Neither is a healthy idle system, so echoes are discarded and the absence of
    a real reply is reported as unavailable. Per-command failures are recorded in
    ``query_errors`` and surfaced as ``warnings``.
    """
    state = {
        "live_available": False,
        "running": {},
        "workers": [],
        "producers": [],
        "error": None,
        "query_errors": {},
        "warnings": [],
    }

    try:
        from apps.tasks.dispatcherd_config import ensure_dispatcherd_configured

        ensure_dispatcherd_configured()

        from dispatcherd.factories import get_control_from_settings

        control = get_control_from_settings()
    except Exception as exc:  # noqa: BLE001 - diagnostics must never raise
        logger.warning("Live dispatcherd state unavailable: %s", exc)
        state["error"] = f"{type(exc).__name__}: {exc}"
        return state

    replies: dict[str, list] = {}
    query_errors: dict[str, str] = {}
    for command in ("running", "workers", "producers"):
        raw_replies, error = _control_replies(control, command, timeout)
        # Drop control-request echoes at ingestion so they can never be counted
        # as evidence, nor merged into workers/producers/running.
        replies[command] = [reply for reply in raw_replies if _is_state_reply(reply)]
        if error:
            query_errors[command] = error
        for reply in replies[command]:
            reply_error = reply.get("error")
            if isinstance(reply_error, str) and reply_error:
                query_errors.setdefault(command, f"dispatcherd error: {reply_error}")

    warnings = []
    workers, malformed_workers = _merge_worker_replies(replies["workers"])
    if malformed_workers:
        warnings.append(f"ignored {malformed_workers} malformed dispatcherd worker entries")
    warnings.extend(f"{command} query failed: {error}" for command, error in query_errors.items())

    # Availability must reflect a meaningful reply, not the absence of an
    # exception and not the broker echoing our own request back.
    live_available = any(replies.values())

    state.update(
        {
            "live_available": live_available,
            "running": _merge_running_replies(replies["running"]),
            "workers": workers,
            "producers": _merge_producer_replies(replies["producers"]),
            "query_errors": query_errors,
            "warnings": warnings,
        }
    )
    if not live_available:
        state["error"] = (
            "; ".join(f"{command}: {error}" for command, error in query_errors.items())
            or "no replies from dispatcherd (control timeout)"
        )
    return state


def get_queue_depth(live_state: dict | None = None) -> dict:
    """Return database backlog plus live dispatcherd queue depth per queue."""
    from apps.tasks.tasks import get_queue_for_function

    pending_functions = list(Task.objects.filter(status="pending").values_list("function_name", flat=True))
    pending_counts: Counter = Counter(get_queue_for_function(function_name) for function_name in pending_functions)

    live_counts: dict[str, dict[str, int]] = {}
    queues = set(get_known_queues()) | set(pending_counts)

    if live_state and live_state.get("live_available"):
        running = live_state.get("running") or {}
        task_ids = []
        for message in running.values():
            if isinstance(message, dict):
                task_id = (message.get("kwargs") or {}).get("task_id")
                if task_id is not None:
                    task_ids.append(task_id)
        task_queues = dict(Task.objects.filter(id__in=task_ids).values_list("id", "function_name"))
        task_queues = {task_id: get_queue_for_function(name) for task_id, name in task_queues.items()}

        for key, message in running.items():
            bucket = next((name for name in _LIVE_BUCKETS if str(key).startswith(f"{name}-")), None)
            if bucket is None:
                continue
            queue = None
            if isinstance(message, dict):
                queue = message.get("channel")
                task_id = (message.get("kwargs") or {}).get("task_id")
                if queue is None and task_id is not None:
                    queue = task_queues.get(int(task_id))
            queue = str(queue) if queue else "unknown"
            queues.add(queue)
            live_counts.setdefault(queue, dict.fromkeys(_LIVE_BUCKETS, 0))[bucket] += 1

    queue_rows = []
    for queue in sorted(queues):
        live = live_counts.get(queue, {})
        queue_rows.append(
            {
                "queue": queue,
                "pending_in_db": pending_counts.get(queue, 0),
                "queued_live": live.get("queued", 0),
                "blocked_live": live.get("blocked", 0),
                "delayed_live": live.get("delayed", 0),
            }
        )

    return {
        "live_available": bool(live_state and live_state.get("live_available")),
        "error": (live_state or {}).get("error"),
        "warnings": (live_state or {}).get("warnings") or [],
        "query_errors": (live_state or {}).get("query_errors") or {},
        "queues": queue_rows,
        "dispatcherd_workers": (live_state or {}).get("workers", []),
        "dispatcherd_producers": (live_state or {}).get("producers", []),
    }


def get_diagnostics(
    hours: int = 24,
    stuck_timeout: int | None = None,
    limit: int = 20,
    include_live: bool = True,
) -> dict:
    """Collect task diagnostics as a JSON-serializable dict.

    Args:
        hours: Lookback window for failure counts.
        stuck_timeout: Stuck threshold in seconds; defaults to ``settings.TASK_TIMEOUT``.
        limit: Maximum rows returned for the stuck and failure sections.
        include_live: Query dispatcherd for live queue/worker state.
    """
    now = timezone.now()
    timeout = settings.TASK_TIMEOUT if stuck_timeout is None else stuck_timeout

    if include_live:
        live_state = get_dispatcherd_state()
    else:
        live_state = {
            "live_available": False,
            "running": {},
            "workers": [],
            "producers": [],
            "error": "disabled",
            "query_errors": {},
            "warnings": [],
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _iso(now),
        "task_timeout_seconds": timeout,
        "window_hours": hours,
        "stuck_tasks": get_stuck_tasks(stuck_timeout=timeout, limit=limit, now=now, live_state=live_state),
        "last_success": get_last_success_by_function(now=now),
        "failures_in_window": get_failure_counts(hours=hours, limit=limit, now=now),
        "queue_depth": get_queue_depth(live_state=live_state),
    }


def _format_duration(seconds: float | None) -> str:
    """Format a duration in seconds as zero-padded ``HH:MM:SS``."""
    if seconds is None:
        return "never"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _render_stuck_tasks(lines: list[str], data: dict, limit: int) -> None:
    """Append the stuck-tasks section."""
    stuck_tasks = data.get("stuck_tasks") or []
    lines.append(f"Stuck tasks ({len(stuck_tasks)})")
    lines.append("-" * 50)
    if not stuck_tasks:
        lines.append("No stuck tasks.")
        return

    for task in stuck_tasks[:limit]:
        lines.append(f"  {task['name']} (ID: {task['task_id']})")
        lines.append(f"    Function: {task['function_name']}")
        lines.append(f"    Started: {task['started_at']} | Duration: {_format_duration(task['duration_seconds'])}")
        lines.append(f"    Attempts: {task['attempts']} | Worker: {task.get('worker_id') or 'unknown'}")
        reported_by = task.get("reported_by") or []
        if reported_by:
            lines.append(f"    Reported by dispatcherd: {', '.join(reported_by)}")
        else:
            lines.append("    Reported by dispatcherd: none (worker may have died)")
        lines.append("")


def _render_last_success(lines: list[str], data: dict) -> None:
    """Append the last-successful-run section."""
    lines.append("Last successful run by task type")
    lines.append("-" * 50)
    lines.append(f"  {'FUNCTION':<40} {'LAST SUCCESS':<28} AGE")
    for row in data.get("last_success") or []:
        lines.append(
            f"  {row['function_name']:<40} {str(row.get('last_success_at') or 'never'):<28} "
            f"{_format_duration(row.get('age_seconds'))}"
        )
    lines.append("")


def _render_failures(lines: list[str], data: dict, limit: int) -> None:
    """Append the recent-failures section."""
    failures = data.get("failures_in_window") or []
    lines.append(f"Failures in the last {data.get('window_hours')}h")
    lines.append("-" * 50)
    if not failures:
        lines.append("No failures in the window.")
        return

    for row in failures[:limit]:
        lines.append(
            f"  {row['function_name']}: {row['failure_count']} failure(s) | last: {row.get('last_failure_at')}"
        )
        if row.get("last_error"):
            lines.append(f"    Last error: {_truncate_error(row['last_error'])}")


def _render_queue_depth(lines: list[str], data: dict) -> None:
    """Append the queue-depth section."""
    queue_depth = data.get("queue_depth") or {}
    lines.append("Queue depth")
    lines.append("-" * 50)
    lines.append(f"  {'QUEUE':<16} {'PENDING (DB)':>12} {'QUEUED':>8} {'BLOCKED':>8} {'DELAYED':>8}")
    for row in queue_depth.get("queues") or []:
        lines.append(
            f"  {row['queue']:<16} {row['pending_in_db']:>12} {row['queued_live']:>8} "
            f"{row['blocked_live']:>8} {row['delayed_live']:>8}"
        )

    for warning in queue_depth.get("warnings") or []:
        lines.append(f"Warning: {warning}")

    if not queue_depth.get("live_available"):
        lines.append(f"Live dispatcherd state unavailable: {queue_depth.get('error') or 'unknown error'}")
        return

    workers = queue_depth.get("dispatcherd_workers") or []
    producers = queue_depth.get("dispatcherd_producers") or []
    lines.append(f"Workers: {len(workers)} | Producers: {len(producers)}")
    for worker in workers:
        # Never assume the shape of a control reply: an older or hand-edited
        # payload must not take the whole report down.
        if not isinstance(worker, dict):
            lines.append(f"  Warning: unexpected worker entry {worker!r}")
            continue
        lines.append(
            f"  worker-{worker.get('worker_id')}: {worker.get('status')} | "
            f"current task: {worker.get('current_task') or 'idle'}"
        )
    for producer in producers:
        if not isinstance(producer, dict):
            lines.append(f"  Warning: unexpected producer entry {producer!r}")
            continue
        lines.append(f"  {producer.get('producer')}: produced {producer.get('produced_count', 0)}")


def render_diagnostics_text(data: dict, limit: int = 20) -> str:
    """Render the diagnostics dict as human-readable text."""
    lines = [
        "Metrics service task diagnostics",
        "=" * 50,
        f"Generated at: {data.get('generated_at')}",
        f"Stuck threshold: {data.get('task_timeout_seconds')}s",
        f"Failure window: {data.get('window_hours')}h",
        "",
    ]
    _render_stuck_tasks(lines, data, limit)
    _render_last_success(lines, data)
    _render_failures(lines, data, limit)
    _render_queue_depth(lines, data)
    lines.append("")
    lines.append("Use --format json for scripting.")

    return "\n".join(lines)
