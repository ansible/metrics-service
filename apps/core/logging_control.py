"""Runtime control of the service log level.

The service runs as several process types (Gunicorn web workers, dispatcherd
workers, and the APScheduler process) which may live in separate pods. A single
database row (:class:`~apps.core.models.RuntimeLogLevelOverride`) is the shared
channel; each process applies it at a bounded refresh point:

* web requests   -> :class:`apps.core.middleware.LogLevelMiddleware`
* scheduler loop -> ``UnifiedTaskScheduler._periodic_database_sync``
* task workers   -> ``execute_db_task``

The override is ephemeral by design:

* it expires after ``expires_at``;
* a process that started after the row was written ignores it
  (``override.modified < process_started_at()``), so restarting reverts to
  ``METRICS_SERVICE_LOG_LEVEL`` / ``settings.LOG_LEVEL``.

All database access is best-effort. A failure to read the override must never
break request or task handling.
"""

from __future__ import annotations

import logging
import os
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
    """Set every managed logger to ``level`` in this process."""
    name, value = _coerce_level(level)
    names = managed_loggers()
    for logger_name in names:
        logging.getLogger(logger_name).setLevel(value)
    for logger_name in OPTIONAL_LOGGERS:
        if logger_name in logging.Logger.manager.loggerDict:
            logging.getLogger(logger_name).setLevel(value)
    global _APPLIED_LEVEL
    _APPLIED_LEVEL = name
    return dict.fromkeys(names, name)


def revert() -> dict[str, str]:
    """Restore every managed logger to the configured baseline."""
    global _APPLIED_LEVEL
    result = apply_level(BASELINE_LEVEL)
    _APPLIED_LEVEL = None
    return result


def _revert_if_applied() -> None:
    global _APPLIED_LEVEL
    if _APPLIED_LEVEL is not None:
        try:
            revert()
        except ValueError:  # pragma: no cover - BASELINE_LEVEL is validated at import
            logger.warning("Could not revert runtime log level to baseline %s", BASELINE_LEVEL)


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

        from apps.tasks.dispatcherd_config import _postgres_connection_config

        db_config = settings.DATABASES["default"]
        broker_config = _postgres_connection_config(db_config)
        control = dispatcherd.control.Control(
            broker_name="pg_notify",
            broker_config=broker_config,
            queue="metrics",
        )
        return control.control_with_reply("set_log_level", timeout=2, data={"level": level})
    except Exception as exc:  # noqa: BLE001 - dispatcherd may not be running
        logger.debug("Could not notify dispatcherd of log level change: %s", exc)
        return None
