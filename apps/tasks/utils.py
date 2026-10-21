"""
Utility functions for task management and execution.
"""

import logging
from datetime import UTC
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


def ensure_django_setup():
    """
    Ensure Django is properly configured for dispatcherd workers.

    This function must be called at the beginning of any task function
    that needs to access Django models or ORM functionality, since
    dispatcherd workers run in separate processes without Django initialized.
    """
    import django
    from django.conf import settings

    if not settings.configured:
        import os

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metrics_service.settings")
        django.setup()


def _fetch_task_by_id(task_id: int) -> Any:
    """Fetch a Task instance by ID, returning None and logging on failure."""
    try:
        from .models import Task

        return Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        logger.error(f"Task instance not found for task_id: {task_id}")
        return None
    except Exception:
        logger.exception(f"Failed to get task instance for task_id: {task_id}")
        return None


def _fetch_execution_by_id(execution_id: int) -> Any:
    """Fetch a TaskExecution instance by ID, returning None and logging on failure."""
    try:
        from .models import TaskExecution

        return TaskExecution.objects.get(id=execution_id)
    except TaskExecution.DoesNotExist:
        logger.error(f"Execution instance not found for execution_id: {execution_id}")
        return None
    except Exception:
        logger.exception(f"Failed to get execution instance for execution_id: {execution_id}")
        return None


def handle_task_error(
    task_instance: Any = None,
    execution_instance: Any = None,
    error_message: str = "",
    exception: Exception | None = None,
    task_id: int | None = None,
    execution_id: int | None = None,
) -> dict[str, Any]:
    """
    Standardized error handling for task execution.

    This function provides a common way to handle task execution errors,
    reducing duplication across task execution functions.

    Args:
        task_instance: The task model instance (can be None if task_id provided)
        execution_instance: Optional task execution instance
        error_message (str): Custom error message
        exception (Exception): Optional exception that caused the error
        task_id (int): Optional task ID if task_instance is None
        execution_id (int): Optional execution ID if execution_instance is None

    Returns:
        dict: Error result dictionary
    """
    if exception:
        error_message = error_message or f"Task execution failed: {str(exception)}"

    if not task_instance and task_id:
        task_instance = _fetch_task_by_id(task_id)

    if not execution_instance and execution_id:
        execution_instance = _fetch_execution_by_id(execution_id)

    try:
        with transaction.atomic():
            now = timezone.now()

            # Only fail the exact claim that produced this error. A timed-out
            # worker must not overwrite a retry that has already been claimed.
            if task_instance:
                from .models import Task

                task_updates = {
                    "status": "failed",
                    "error_message": error_message,
                    "completed_at": now,
                    "modified": now,
                }
                task_queryset = Task.objects.filter(pk=task_instance.pk)

                if execution_instance:
                    task_queryset.filter(status="running", started_at=execution_instance.started_at).update(
                        **task_updates
                    )
                elif task_instance.status == "pending":
                    task_updates["attempts"] = F("attempts") + 1
                    task_queryset.filter(status="pending").update(**task_updates)
                elif task_instance.status == "running":
                    task_queryset.filter(status="running", started_at=task_instance.started_at).update(**task_updates)

            # Keep the attempt's outcome, but never rewrite an execution that
            # has already been finalized (for example, by stuck-task recovery).
            if execution_instance:
                from .models import TaskExecution

                execution_updates = {
                    "status": "failed",
                    "error_message": error_message,
                    "completed_at": now,
                    "modified": now,
                }
                if execution_instance.started_at:
                    execution_updates["execution_time_seconds"] = (now - execution_instance.started_at).total_seconds()
                TaskExecution.objects.filter(
                    pk=execution_instance.pk,
                    task_id=task_instance.pk if task_instance else execution_instance.task_id,
                    status="running",
                ).update(**execution_updates)

            if task_instance:
                task_instance.refresh_from_db()
            if execution_instance:
                execution_instance.refresh_from_db()

    except Exception as save_error:
        logger.exception(f"Failed to update task status after error: {save_error}")

    # Deferred past the transaction so status=="failed" and attempts are incremented before can_retry() is called.
    # Defaults to ERROR when no task context is available.
    if task_instance and task_instance.can_retry():
        logger.warning(error_message)
    else:
        logger.error(error_message)

    return create_task_result("error", error=error_message)


def update_task_status(
    task_instance: Any,
    execution_instance: Any = None,
    status: str = "",
    result_data: dict[str, Any] | None = None,
    error_message: str = "",
) -> None:
    """
    Standardized task status updating.

    This function provides a common way to update task and execution status,
    reducing duplication across task execution functions.

    Args:
        task_instance: The task model instance
        execution_instance: Optional task execution instance
        status (str): New status for the task
        result_data (dict): Optional result data
        error_message (str): Optional error message

    Returns:
        None

    Note:
        This does not handle the transition to "running". Claiming a task
        (setting started_at and incrementing attempts) is owned exclusively by
        _claim_task, which does it atomically. Completion and failure updates
        only apply to the same still-running claim, so cancellation and later
        retries cannot be overwritten by stale worker results.
    """
    if status == "running":
        raise ValueError("update_task_status cannot set status='running'; use _claim_task to claim a task")
    if status not in {"completed", "failed"}:
        raise ValueError("update_task_status only accepts status='completed' or status='failed'")

    with transaction.atomic():
        from .models import Task, TaskExecution

        now = timezone.now()
        task_updates = {"status": status, "modified": now}
        if result_data is not None:
            task_updates["result_data"] = result_data
        if error_message or status == "completed":
            task_updates["error_message"] = error_message
        task_updates["completed_at"] = now

        expected_started_at = execution_instance.started_at if execution_instance else task_instance.started_at
        Task.objects.filter(
            pk=task_instance.pk,
            status="running",
            started_at=expected_started_at,
        ).update(**task_updates)

        # A cancelled task remains cancelled, while its still-running execution
        # can record the result the worker actually produced. A timed-out or
        # superseded execution is left untouched.
        if execution_instance:
            execution_updates = {"status": status, "modified": now}
            if result_data is not None:
                execution_updates["result_data"] = result_data
            if error_message or status == "completed":
                execution_updates["error_message"] = error_message
            execution_updates["completed_at"] = now
            if execution_instance.started_at:
                execution_updates["execution_time_seconds"] = (now - execution_instance.started_at).total_seconds()
            TaskExecution.objects.filter(
                pk=execution_instance.pk,
                task_id=task_instance.pk,
                status="running",
            ).update(**execution_updates)

        task_instance.refresh_from_db()
        if execution_instance:
            execution_instance.refresh_from_db()


def create_task_result(status: str, data: dict[str, Any] | None = None, error: str = "") -> dict[str, Any]:
    """
    Create a standardized task result dictionary.

    This function provides a consistent format for task results,
    reducing duplication across task functions.

    Args:
        status (str): Task status (success, error, etc.)
        data (dict): Optional result data
        error (str): Optional error message

    Returns:
        dict: Standardized result dictionary
    """
    result = {
        "status": status,
        "timestamp": timezone.now().isoformat(),
    }

    if data:
        result.update(data)

    if error:
        result["error"] = error

    return result


def log_task_execution(task_name: str, operation: str, details: str = "", level: str = "info"):
    """
    Standardized logging for task execution.

    This function provides consistent logging format across all task operations,
    reducing duplication in logging statements.

    Args:
        task_name (str): Name of the task
        operation (str): Operation being performed (start, complete, error, etc.)
        details (str): Additional details to log
        level (str): Log level (info, warning, error, debug)

    Returns:
        None
    """
    message = f"Task '{task_name}' {operation}"
    if details:
        message += f": {details}"

    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message)


def parse_datetime_string(date_str: str | None) -> Any:
    """
    Parse an ISO datetime string, return None if invalid.

    Naive datetimes (without timezone info) are assumed to be UTC.

    Args:
        date_str: ISO format datetime string (supports 'Z' suffix)

    Returns:
        timezone-aware datetime object or None if invalid/empty
    """
    from datetime import datetime

    if not date_str:
        return None
    try:
        # Replace 'Z' with '+00:00' for ISO parsing
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

        # If naive datetime, make it timezone-aware (assume UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        return dt
    except (ValueError, AttributeError):
        return None


_AWX_PROBE_TABLES = ("main_unifiedjob",)


def _check_db_ready(connection, probe_tables):
    """Return True if at least one probe table exists in the database."""
    with connection.cursor() as cursor:
        for table in probe_tables:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
                [table],
            )
            if cursor.fetchone()[0]:
                return True
    return False


def get_db_connection(db_name: str = "awx"):
    """
    Get a raw database connection that supports PostgreSQL COPY commands.

    Django's CursorDebugWrapper doesn't support the COPY command, so we need
    to use the raw connection for metrics-utility collectors that use COPY
    for efficient data extraction.

    Args:
        db_name: Database name from Django settings (default: 'awx')

    Returns:
        Raw database connection object (psycopg3 connection)

    Note:
        DO NOT CLOSE the returned connection. It is a Django-managed singleton
        shared across multiple tasks. Django handles connection lifecycle.
    """
    from django.db import connections

    # Get the raw connection to bypass Django's cursor wrapper
    # This is necessary for PostgreSQL COPY commands used by metrics-utility
    # NOTE: Do not call close_old_connections() here as it closes ALL connections
    # including the default connection that may be holding advisory locks in run_with_lock()
    django_connection = connections[db_name]

    # Django's ensure_connection() only reconnects when self.connection is None.
    # A connection dropped by the server is not None — it is a stale psycopg3
    # object. Probe it with SELECT 1 before handing it to the collector:
    #   - catches connections already marked closed (.closed == True)
    #   - catches silent network drops where .closed is still False
    # Five collectors run per hour so the round-trip overhead is negligible.
    if django_connection.connection is not None:
        try:
            django_connection.connection.execute("SELECT 1")
        except Exception:
            logger.warning(f"Database connection '{db_name}' is stale, reconnecting")
            django_connection.close()

    django_connection.ensure_connection()

    return django_connection.connection


def awx_db_ready() -> bool:
    """
    Check if AWX controller database tables are available.

    This prevents scheduling collector tasks before controller migrations complete,
    avoiding startup race conditions. Useful for any component that needs to wait
    for controller DB initialization.

    Returns:
        True if at least one AWX probe table exists, False otherwise
    """
    try:
        # Use get_db_connection() to inherit stale-connection recovery logic
        # (SELECT 1 probe + reconnect), preventing false negatives on transient stale connections
        raw_conn = get_db_connection("awx")
        return _check_db_ready(raw_conn, _AWX_PROBE_TABLES)
    except Exception as e:
        logger.debug(f"AWX DB readiness check failed: {e}")
        return False


def run_with_lock(lock_key: str, task_name: str, fn, **kwargs):
    """
    Execute a task function under a PostgreSQL advisory lock.

    If the lock cannot be acquired (another instance of the same task is running),
    returns an error result which triggers auto-retry.

    Args:
        lock_key: Unique key for the advisory lock
        task_name: Task name for logging
        fn: Task function to execute
        **kwargs: Arguments to pass to fn
    """
    from django.db import close_old_connections, connection
    from metrics_utility.library.lock import lock

    # Close any stale/unusable connections before acquiring lock
    close_old_connections()

    with lock(lock_key, wait=False, db=connection) as acquired:
        if not acquired:
            msg = f"Could not acquire lock '{lock_key}' — another {task_name} instance is running"
            logger.warning(msg)
            log_task_execution(task_name, "skipped", msg)
            return create_task_result("error", error=msg)
        return fn(**kwargs)


def generate_salt() -> str:
    """
    Generate a unique UUID4 salt for anonymization.

    Returns:
        str: UUID4 string
    """
    import uuid

    return str(uuid.uuid4())


def _serialize_args(kwargs):
    """Convert task kwargs to a JSON-serializable dict, turning datetime values into ISO strings."""
    if not kwargs:
        return {}

    params = {}

    for key, value in kwargs.items():
        # Convert datetime objects to ISO strings for database storage
        if hasattr(value, "isoformat"):
            params[key] = value.isoformat()
        else:
            params[key] = value

    return params


def _run_post_collect_hook(hook, raw_data: Any, collector_type: str) -> None:
    """Call hook(raw_data), logging failures without aborting the rollup pipeline."""
    try:
        hook(raw_data)
    except Exception as hook_exc:
        error_msg = f"post_collect_hook failed for {collector_type}: {hook_exc}"
        logger.warning(error_msg)


def _persist_collection(
    collection_model: Any,
    collector_type: str,
    collection_mode: str,
    timestamp: Any,
    rollup_data: Any,
    collection_params: dict,
    task_execution_instance: Any,
) -> dict[str, Any]:
    """Upsert an HourlyMetricsCollection record and return a task result dict.

    Treats a concurrent-write IntegrityError as success — the other execution
    already persisted the data, so there is nothing left to do.
    """
    from django.db import IntegrityError

    try:
        collection, created = collection_model.objects.update_or_create(
            collector_type=collector_type,
            collection_timestamp=timestamp,
            defaults={
                "raw_data": rollup_data,
                "status": "collected",
                "error_message": "",
                "collection_parameters": collection_params,
                "task_execution": task_execution_instance,
            },
        )
    except IntegrityError:
        logger.warning(
            f"Duplicate collection skipped for {collector_type} at {timestamp.isoformat()} "
            f"(unique constraint violation - record already written by concurrent execution)"
        )
        return create_task_result(
            "success",
            {
                "message": f"Skipped duplicate {collection_mode} collection for {collector_type}",
                "task_type": f"collect_{collector_type}",
                "collector_type": collector_type,
                "timestamp": timestamp.isoformat(),
            },
        )

    action = "Created" if created else "Updated"
    log_task_execution(f"collect_{collector_type}", "completed", f"{action} {collection_mode} ID: {collection.id}")
    return create_task_result(
        "success",
        {
            "message": f"{action} {collection_mode} collection for {collector_type}",
            "task_type": f"collect_{collector_type}",
            "collection_id": collection.id,
            "collector_type": collector_type,
            "timestamp": timestamp.isoformat(),
        },
    )


def generic_collect_metrics(
    collector_type: str,
    collector_registry: dict[str, dict[str, Any]],
    collection_mode: str,
    timestamp: Any,
    db_connection: Any,
    collector_kwargs: dict[str, Any] | None = None,
    task_execution_id: int | None = None,
    post_collect_hook=None,
) -> dict[str, Any]:
    """Generic metrics collection for hourly/snapshot collectors with optional rollup processing."""
    import contextlib

    from apps.tasks.models import HourlyMetricsCollection

    if collector_type not in collector_registry:
        valid = ", ".join(sorted(collector_registry.keys()))
        return create_task_result("error", error=f"Unknown collector_type: {collector_type}. Valid types: {valid}")

    config = collector_registry[collector_type]
    log_task_execution(f"collect_{collector_type}", "processing", f"Collecting {collector_type} ({collection_mode})")

    collection_params = _serialize_args(collector_kwargs)

    task_execution_instance = None
    if task_execution_id:
        try:
            from apps.tasks.models import TaskExecution

            task_execution_instance = TaskExecution.objects.get(id=task_execution_id)
        except Exception:
            logger.debug(f"TaskExecution {task_execution_id} not found, proceeding without link")

    try:
        # For snapshot collectors, filter out collection_time (audit-only param, not used by collector)
        actual_collector_kwargs = collector_kwargs.copy() if collector_kwargs else {}
        if collection_mode == "snapshot" and "collection_time" in actual_collector_kwargs:
            actual_collector_kwargs.pop("collection_time")

        collector = config["collector_func"](db=db_connection, **actual_collector_kwargs)
        gather_started = timezone.now()
        raw_data = collector.gather()
        gather_finished = timezone.now()

        # Persist the raw pre-prepare() output for the analytics API (enabled collectors only).
        # Best-effort and non-invasive: failures are swallowed inside the helper so the existing
        # rollup path below is never affected. Lazy import avoids a tasks<->analytics import cycle.
        from apps.analytics.persist import persist_analytics_payload

        persist_analytics_payload(
            collector_type,
            raw_data,
            since=actual_collector_kwargs.get("since"),
            until=actual_collector_kwargs.get("until"),
            started_at=gather_started,
            finished_at=gather_finished,
            raise_on_error=not config.get("persist_to_hourly", True),
            db_connection=db_connection,
        )

        if post_collect_hook is not None:
            _run_post_collect_hook(post_collect_hook, raw_data, collector_type)

        if not config.get("persist_to_hourly", True):
            return create_task_result(
                "success",
                {
                    "message": f"Persisted analytics-only collection for {collector_type}",
                    "task_type": f"collect_{collector_type}",
                    "collector_type": collector_type,
                },
            )

        rollup_data = config["rollup_processor"]().prepare(raw_data) if config["rollup_processor"] else raw_data

        return _persist_collection(
            HourlyMetricsCollection,
            collector_type,
            collection_mode,
            timestamp,
            rollup_data,
            collection_params,
            task_execution_instance,
        )

    except Exception as e:
        logger.exception(f"Failed to collect {collector_type} {collection_mode} metrics: {str(e)}")

        # Store failed collection for audit trail (critical for diagnosing missing rollup data).
        # Analytics-only collectors deliberately do not use the hourly collection table.
        if config.get("persist_to_hourly", True):
            with contextlib.suppress(Exception):
                HourlyMetricsCollection.objects.update_or_create(
                    collector_type=collector_type,
                    collection_timestamp=timestamp,
                    defaults={
                        "raw_data": {},
                        "status": "failed",
                        "error_message": str(e),
                        "collection_parameters": collection_params,
                        "task_execution": task_execution_instance,
                    },
                )

        return create_task_result(
            "error",
            {"task_type": f"collect_{collector_type}", "collector_type": collector_type},
            error=f"Collection failed: {str(e)}",
        )
