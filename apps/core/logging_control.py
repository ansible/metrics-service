"""Runtime control of the service log level.

The service runs as several process types (Gunicorn web workers, dispatcherd
workers, and the APScheduler process) which may live in separate pods. A single
database row (:class:`~apps.core.models.RuntimeLogLevelOverride`) is the shared
channel; each process applies it at a bounded refresh point:

* web requests   -> :class:`apps.core.middleware.LogLevelMiddleware`
* scheduler loop -> ``UnifiedTaskScheduler._periodic_database_sync``
* task workers   -> ``execute_db_task`` and, so idle workers also notice a
  clear or TTL expiry, a refresh thread started *after* dispatcherd forks the
  worker pool (see :func:`start_refresh_thread`)

The override is ephemeral by design:

* it expires after ``expires_at``, and an expiry further out than
  ``RUNTIME_LOG_LEVEL_MAX_TTL`` is ignored on the read path (not just clamped
  when written by the CLI), so a hand-written row cannot pin a level;
* a process that started after the row was written ignores it
  (``override.modified < process_started_at()``), so restarting reverts to the
  configured logger levels (``settings.LOGGING``, which defaults to
  ``METRICS_SERVICE_LOG_LEVEL``);
* the level each managed logger had before the override was applied is
  restored on revert, so per-logger configuration survives an override cycle.

All database access is best-effort. A failure to read the override must never
break request or task handling.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import UTC, timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

DEFAULT_MANAGED_LOGGERS = ("ansible_base", "metrics_service", "django", "apps")
MANAGED_LOGGERS = DEFAULT_MANAGED_LOGGERS
OPTIONAL_LOGGERS = ("dispatcherd",)

LEVEL_NAMES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

PROCESS_STARTED_ENV = "METRICS_SERVICE_PROCESS_STARTED_AT"

# Module import time is the fallback process epoch when the env var is absent.
_PROCESS_STARTED_AT = timezone.now()
_PROCESS_STARTED_AT_READY = False
_LAST_SYNC_MONOTONIC = 0.0
_APPLIED_LEVEL: str | None = None
# Levels captured immediately before the first override is applied in this
# process. ``revert()`` restores exactly these values instead of rewriting the
# loggers to ``BASELINE_LEVEL``, because per-logger configuration is often
# different from ``LOG_LEVEL`` (e.g. ``apps/settings/development.py`` raises
# ``django``/``metrics_service``/``ansible_base`` to DEBUG, and deployments may
# silence ``django.db.backends`` with ``LOGGING__loggers__*__level``).
_BASELINE_LEVELS: dict[str, int] = {}

# The dispatcherd *worker* refresh thread. Each forked worker owns exactly one
# thread; the dispatcherd parent never starts one (see start_refresh_thread).
_REFRESH_THREAD: threading.Thread | None = None
_REFRESH_STOP_EVENT: threading.Event | None = None
_REFRESH_THREAD_LOCK = threading.Lock()
REFRESH_THREAD_NAME = "runtime-log-level-sync"

BASELINE_LEVEL = str(getattr(settings, "LOG_LEVEL", "INFO") or "INFO").upper()


def managed_loggers() -> tuple[str, ...]:
    """The four service loggers this feature owns.

    These are fixed deliberately: the merged (DAB + dynaconf) ``LOGGING``
    configuration contains many library loggers, and changing all of them would
    make a "runtime log level" far broader than the story intends. Child loggers
    such as ``apps.tasks`` inherit the level from ``apps``.
    """
    return MANAGED_LOGGERS


def _coerce_level(level: Any) -> tuple[str, int]:
    """Validate a level name and return ``(NAME, int_value)``."""
    if not isinstance(level, str):
        raise ValueError(f"Log level must be a string, got {type(level).__name__}")
    name = level.strip().upper()
    levels = logging.getLevelNamesMapping()
    if name not in LEVEL_NAMES or name not in levels:
        allowed = ", ".join(LEVEL_NAMES)
        raise ValueError(f"Invalid log level {level!r}; expected one of: {allowed}")
    return name, levels[name]


def process_started_at():
    """Return this process's epoch, from env or module import time."""
    global _PROCESS_STARTED_AT, _PROCESS_STARTED_AT_READY
    if not _PROCESS_STARTED_AT_READY:
        raw = os.environ.get(PROCESS_STARTED_ENV)
        if raw:
            parsed = parse_datetime(raw)
            if parsed is not None:
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed, UTC)
                _PROCESS_STARTED_AT = parsed
        _PROCESS_STARTED_AT_READY = True
    return _PROCESS_STARTED_AT


def reset_process_started_at(value=None) -> None:
    """Override the process epoch (tests and long-lived processes only)."""
    global _PROCESS_STARTED_AT, _PROCESS_STARTED_AT_READY
    _PROCESS_STARTED_AT = value or timezone.now()
    _PROCESS_STARTED_AT_READY = True


def reset_throttle() -> None:
    """Clear the sync throttle so the next call always queries the database."""
    global _LAST_SYNC_MONOTONIC
    _LAST_SYNC_MONOTONIC = 0.0


def apply_level(level: str) -> dict[str, str]:
    """Set every managed logger to ``level`` in this process.

    The level each logger had *before* the first override was applied is
    captured once and later restored by :func:`revert`; repeated applies (the
    per-request/task refresh) never overwrite that snapshot.
    """
    name, value = _coerce_level(level)
    names = managed_loggers()
    for logger_name in names:
        _BASELINE_LEVELS.setdefault(logger_name, logging.getLogger(logger_name).level)
        logging.getLogger(logger_name).setLevel(value)
    for logger_name in OPTIONAL_LOGGERS:
        if logger_name in logging.Logger.manager.loggerDict:
            _BASELINE_LEVELS.setdefault(logger_name, logging.getLogger(logger_name).level)
            logging.getLogger(logger_name).setLevel(value)
    global _APPLIED_LEVEL
    _APPLIED_LEVEL = name
    return dict.fromkeys(names, name)


def revert() -> dict[str, str]:
    """Restore every managed logger to the level it had before the override.

    Only loggers captured by :func:`apply_level` are touched. When no override
    was applied in this process this is a no-op, so configured per-logger
    levels are never rewritten to ``BASELINE_LEVEL``.

    Returns the restored ``{logger: level_name}`` mapping.
    """
    global _APPLIED_LEVEL
    restored: dict[str, str] = {}
    for logger_name, value in _BASELINE_LEVELS.items():
        logging.getLogger(logger_name).setLevel(value)
        restored[logger_name] = str(logging.getLevelName(value))
    _BASELINE_LEVELS.clear()
    _APPLIED_LEVEL = None
    return restored


def _revert_if_applied() -> None:
    if _APPLIED_LEVEL is not None:
        revert()


def get_active_override():
    """Return the override row, or ``None`` when there is none."""
    from apps.core.models import RuntimeLogLevelOverride

    return RuntimeLogLevelOverride.objects.filter(pk=1).first()


def sync_from_db(respect_process_start: bool = True, force: bool = False) -> str | None:
    """Apply the database override to this process, if appropriate.

    Throttled by ``RUNTIME_LOG_LEVEL_REFRESH_SECONDS`` unless ``force`` is set.
    Returns the currently applied level name (or ``None`` when baseline).
    """
    global _LAST_SYNC_MONOTONIC

    interval = float(getattr(settings, "RUNTIME_LOG_LEVEL_REFRESH_SECONDS", 1) or 0)
    now_mono = time.monotonic()
    if not force and interval > 0 and (now_mono - _LAST_SYNC_MONOTONIC) < interval:
        return _APPLIED_LEVEL
    _LAST_SYNC_MONOTONIC = now_mono

    try:
        override = get_active_override()
    except Exception as exc:  # noqa: BLE001 - log control must never break the caller
        logger.debug("Runtime log level sync skipped: %s", exc)
        return _APPLIED_LEVEL

    if override is None or override.expires_at <= timezone.now():
        _revert_if_applied()
        return _APPLIED_LEVEL

    # ``set_override`` caps the TTL, but the row is a plain table: a level
    # written directly to the database must not pin a process indefinitely.
    # Enforce the same bound on the read path and fail safe (baseline) rather
    # than honouring an over-long expiry.
    max_ttl = int(getattr(settings, "RUNTIME_LOG_LEVEL_MAX_TTL", 3600) or 0)
    if max_ttl and override.expires_at > timezone.now() + timedelta(seconds=max_ttl):
        logger.warning(
            "Ignoring runtime log level override %s: expires_at %s exceeds RUNTIME_LOG_LEVEL_MAX_TTL (%ss)",
            override.level,
            override.expires_at.isoformat(),
            max_ttl,
        )
        _revert_if_applied()
        return _APPLIED_LEVEL

    if respect_process_start and override.modified < process_started_at():
        # This process started after the override was written: a restart has
        # happened, so run at the configured baseline.
        _revert_if_applied()
        return _APPLIED_LEVEL

    try:
        apply_level(override.level)
    except ValueError as exc:
        logger.warning("Ignoring invalid runtime log level override: %s", exc)
        _revert_if_applied()
    return _APPLIED_LEVEL


def sync_dispatcherd_log_level() -> str | None:
    """One refresh cycle for a dispatcherd process.

    dispatcherd processes have no request boundary of their own: the worker
    pool children run :func:`start_refresh_thread`, and each task entry also
    calls :func:`sync_from_db`. That is what makes clears and TTL expiry
    propagate to the dispatcherd logger; without it a level applied at startup
    would persist indefinitely.
    """
    from django.db import close_old_connections, connection

    # Never close inside an atomic block (tests); production has no long-lived
    # transaction here and benefits from recycling stale connections.
    if not connection.in_atomic_block:
        close_old_connections()
    return sync_from_db(force=True)


def refresh_interval_seconds() -> float:
    """Refresh interval for the worker thread, never below one second."""
    interval = float(getattr(settings, "RUNTIME_LOG_LEVEL_REFRESH_SECONDS", 1) or 1)
    return max(interval, 1.0)


def _refresh_loop(stop_event: threading.Event) -> None:
    """Reconcile the runtime log level until ``stop_event`` is set."""
    interval = refresh_interval_seconds()
    while not stop_event.wait(interval):
        try:
            sync_dispatcherd_log_level()
        except Exception as exc:  # noqa: BLE001 - never kill the sync loop
            logger.debug("Runtime log level sync skipped: %s", exc)


def start_refresh_thread(name: str = REFRESH_THREAD_NAME) -> threading.Thread | None:
    """Start this process's log-level refresh thread (idempotent).

    Call this **only after a dispatcherd worker child has been forked**. The
    thread polls the database, and dispatcherd creates its worker pool with
    ``multiprocessing``'s ``fork`` context: a thread living in the parent at
    that moment leaves the child sharing the parent's in-flight socket, which is
    the exact fork-safety bug ``connections.close_all()`` in ``run_dispatcherd``
    exists to prevent. :class:`apps.tasks.dispatcherd_worker.LogLevelSyncWorker`
    calls this from ``on_start()``, dispatcherd's post-fork hook.

    Returns the running thread, or ``None`` when the current process already has
    one (so repeat calls are harmless).
    """
    global _REFRESH_THREAD, _REFRESH_STOP_EVENT

    with _REFRESH_THREAD_LOCK:
        if _REFRESH_THREAD is not None and _REFRESH_THREAD.is_alive():
            return None
        stop_event = threading.Event()
        thread = threading.Thread(target=_refresh_loop, args=(stop_event,), name=name, daemon=True)
        thread.start()
        _REFRESH_THREAD = thread
        _REFRESH_STOP_EVENT = stop_event
        logger.debug("Started runtime log level refresh thread %s", name)
        return thread


def stop_refresh_thread(timeout: float = 5.0) -> None:
    """Stop this process's refresh thread, if any."""
    global _REFRESH_THREAD, _REFRESH_STOP_EVENT

    with _REFRESH_THREAD_LOCK:
        thread, stop_event = _REFRESH_THREAD, _REFRESH_STOP_EVENT
        _REFRESH_THREAD = None
        _REFRESH_STOP_EVENT = None
    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout)


def active_refresh_thread() -> threading.Thread | None:
    """Return the running refresh thread for this process, if there is one."""
    thread = _REFRESH_THREAD
    return thread if thread is not None and thread.is_alive() else None


def set_override(level: str, ttl_seconds: int | None = None, actor: str = "cli"):
    """Create or replace the shared override row."""
    from apps.core.models import RuntimeLogLevelOverride

    name, _ = _coerce_level(level)
    max_ttl = int(getattr(settings, "RUNTIME_LOG_LEVEL_MAX_TTL", 3600) or 0)
    ttl = max_ttl if ttl_seconds is None else int(ttl_seconds)
    if ttl <= 0:
        raise ValueError("TTL must be a positive number of seconds")
    if max_ttl and ttl > max_ttl:
        raise ValueError(f"TTL must not exceed RUNTIME_LOG_LEVEL_MAX_TTL ({max_ttl}s)")

    expires_at = timezone.now() + timedelta(seconds=ttl)
    with transaction.atomic():
        override, _ = RuntimeLogLevelOverride.objects.update_or_create(
            pk=1,
            defaults={"level": name, "expires_at": expires_at, "set_by": actor},
        )
    return override


def clear_override() -> int:
    """Delete the override row. Returns the number of rows removed."""
    from apps.core.models import RuntimeLogLevelOverride

    deleted, _ = RuntimeLogLevelOverride.objects.all().delete()
    return deleted


def dispatcherd_control_broker_config() -> dict[str, Any]:
    """Broker kwargs for ``dispatcherd.control.Control``.

    ``Control`` hands ``broker_config`` straight to ``get_broker()``, which does
    ``Broker(**broker_config)``. ``dispatcherd.brokers.pg_notify.Broker`` takes
    the psycopg connection arguments under a single ``config`` key, so the flat
    psycopg kwargs must be nested exactly as the YAML builder does
    (``config["brokers"]["pg_notify"]["config"] = pg_config``, see
    :func:`apps.tasks.dispatcherd_config._load_config_with_django_db`). Passing
    them flat raises ``TypeError: unexpected keyword argument 'sslmode'`` and
    the notification never reaches the dispatcherd main process.
    """
    from apps.tasks.dispatcherd_config import _postgres_connection_config

    return {"config": _postgres_connection_config(settings.DATABASES["default"])}


def notify_dispatcherd(level: str) -> Any | None:
    """Best-effort immediate update of the dispatcherd main-process logger.

    The managed loggers live in this process; dispatcherd's own logger is set
    via its control channel. Failure is non-fatal — the database row is still
    authoritative and workers apply it at task entry.
    """
    if not getattr(settings, "DISPATCHERD_ENABLED", True):
        return None
    try:
        import dispatcherd.control

        control = dispatcherd.control.Control(
            broker_name="pg_notify",
            broker_config=dispatcherd_control_broker_config(),
            queue="metrics",
        )
        return control.control_with_reply("set_log_level", timeout=2, data={"level": level})
    except Exception as exc:  # noqa: BLE001 - dispatcherd may not be running
        logger.debug("Could not notify dispatcherd of log level change: %s: %s", type(exc).__name__, exc)
        return None
