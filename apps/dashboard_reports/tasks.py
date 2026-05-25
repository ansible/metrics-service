"""
Background tasks for dashboard reports data collection and cleanup.

Provides three dispatcherd tasks:
- collect_dashboard_reports_initial_data: 90-day historical backfill, one batch per call
- collect_dashboard_reports_data: incremental sync from last known timestamp
- cleanup_dashboard_reports_old_data: removes JobData records beyond retention period

Backfill design
---------------
The 90-day initial backfill can contain hundreds of thousands of jobs. Processing
everything in a single task call risks hitting the 10-minute task timeout and leaves
no progress checkpoint if the task crashes.

Instead, collect_dashboard_reports_initial_data processes exactly ONE batch per call.
The cursor (last processed job ID) is persisted in the next Task's task_data so the
scheduler can resume from the right place after each commit. This means:

- Each task call is bounded to ~batch_size jobs (default 5 000).
- A crash at any point loses at most one batch — the cursor in the DB marks where to resume.
- The incremental follow-up task (daily_dashboard_collection) is only activated once the
  final batch completes successfully.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from django.db import transaction
from metrics_utility.library.collectors.dashboard import DashboardJobsResultType, dashboard_jobs
from metrics_utility.library.collectors.dashboard.queries import get_min_max_job_id_query

from apps.dashboard_reports.models import JobData
from apps.tasks.models import Task
from apps.tasks.task_groups import DASHBOARD_COLLECTION_GROUP
from apps.tasks.utils import create_task_result, get_db_connection, log_task_execution

DEFAULT_DB_NAME = "awx"
DEFAULT_BATCH_SIZE = 5000
_DATE_FIELD = "finished"

logger = logging.getLogger(__name__)


class _PartialSyncRollbackError(Exception):
    """Sentinel raised inside a transaction.atomic() block to roll back all saves when any job fails to sync."""


def _parse_dt(value: Any) -> datetime | None:
    """Coerce value to a timezone-aware datetime.

    - None      → None
    - str       → parsed via fromisoformat; naive result is assumed UTC
    - datetime  → returned unchanged if tz-aware; naive datetime is localised to UTC
    - other     → raises TypeError so callers receive a structured error
    """
    if value is None:
        return None
    if isinstance(value, str):
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    raise TypeError(f"_parse_dt: expected str, datetime, or None; got {type(value).__name__!r}")


def _collect_jobs(db_connection, since: datetime, until: datetime) -> DashboardJobsResultType:
    """Collect dashboard jobs for incremental collection (small window, no batching needed)."""
    return dashboard_jobs(db=db_connection, since=since, until=until, date_field=_DATE_FIELD).gather()


def _collect_jobs_batch(
    db_connection, since: datetime, until: datetime, after_id: int, batch_size: int
) -> DashboardJobsResultType:
    """Collect one cursor-paginated batch for the backfill."""
    return dashboard_jobs(
        db=db_connection,
        since=since,
        until=until,
        after_id=after_id,
        batch_size=batch_size,
        date_field=_DATE_FIELD,
    ).gather()


def _get_backfill_bounds(db_connection, since: datetime, until: datetime) -> tuple[int | None, int | None]:
    """Return (min_id, max_id) for jobs in the backfill window, or (None, None) if no jobs exist."""
    query, params = get_min_max_job_id_query(since, until, date_field=_DATE_FIELD)
    with db_connection.cursor() as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
    if row is None or row[0] is None:
        return None, None
    return int(row[0]), int(row[1])


def _schedule_next_backfill_batch(
    since: datetime, until: datetime, after_id: int, max_id: int, batch_size: int
) -> None:
    """Create a new pending Task to continue the backfill from after_id."""
    Task.objects.create(
        name=f"collect_dashboard_reports_initial_data_batch_{after_id}",
        description="Dashboard reports backfill batch (auto-scheduled)",
        function_name="collect_dashboard_reports_initial_data",
        task_data={
            "since": since.isoformat(),
            "until": until.isoformat(),
            "after_id": after_id,
            "max_id": max_id,
            "batch_size": batch_size,
        },
        is_system_task=False,
        status="pending",
    )


def _establish_backfill_cursor(
    db_connection,
    since: datetime,
    until: datetime,
    after_id: int | None,
    max_id: int | None,
    task_name: str,
) -> tuple[int | None, int | None, dict[str, Any] | None]:
    """Resolve cursor bounds on the first backfill call; return an early result when done or on error."""
    if after_id is not None:
        return after_id, max_id, None

    try:
        min_id, max_id = _get_backfill_bounds(db_connection, since, until)
    except Exception as e:
        return None, max_id, create_task_result("error", error=f"Failed to establish backfill bounds: {str(e)}")

    if min_id is None:
        log_task_execution(task_name=task_name, operation="completed", details="No jobs found in backfill window")
        return None, max_id, _activate_incremental_task(
            data={
                "task_type": task_name,
                "date_range": {"start": since.isoformat(), "end": until.isoformat()},
                "job_count": 0,
            }
        )

    return min_id - 1, max_id, None


def _run_backfill_batch(
    db_connection,
    since: datetime,
    until: datetime,
    after_id: int,
    max_id: int,
    batch_size: int,
    task_name: str,
) -> dict[str, Any]:
    """Collect, sync, and either schedule the next batch or activate incremental collection."""
    log_task_execution(
        task_name=task_name,
        operation="processing",
        details=f"Collecting batch after_id={after_id} (max_id={max_id}) for {since.isoformat()} to {until.isoformat()}",
    )

    try:
        jobs = _collect_jobs_batch(db_connection, since, until, after_id, batch_size)
    except Exception as e:
        logger.error(f"Error collecting backfill batch: {str(e)}")
        return create_task_result("error", error=f"Batch collection failed: {str(e)}")

    failed_jobs = _sync_jobs_atomically(jobs["results"])
    if failed_jobs:
        return create_task_result("error", error=f"Failed to sync {len(failed_jobs)} job(s): {failed_jobs}")

    job_count = jobs["count"]
    last_id = jobs["results"][-1]["id"] if jobs["results"] else after_id

    log_task_execution(
        task_name=task_name,
        operation="processing",
        details=f"Synced {job_count} jobs, cursor now at {last_id}",
    )

    batch_data = {
        "task_type": task_name,
        "date_range": {"start": since.isoformat(), "end": until.isoformat()},
        "job_count": job_count,
        "cursor": last_id,
        "max_id": max_id,
    }

    if job_count == 0 or last_id >= max_id:
        return _activate_incremental_task(data=batch_data)

    try:
        _schedule_next_backfill_batch(since, until, last_id, max_id, batch_size)
    except Exception as e:
        logger.error(f"Error scheduling next backfill batch: {str(e)}")
        return create_task_result("error", error=f"Failed to schedule next batch: {str(e)}")

    return create_task_result("success", data={**batch_data, "batch_complete": False})


def _activate_incremental_task(data: dict) -> dict[str, Any]:
    """Create the daily_dashboard_collection follow-up task if not already present.

    Called once the backfill is complete (or the window is empty). Mirrors the
    existing follow-up task logic from the original single-call implementation.
    """
    task_name = "collect_dashboard_reports_initial_data"

    log_task_execution(
        task_name=task_name,
        operation="processing",
        details="Creating follow-up task for collecting dashboard reports data (every 6 hours) after initial data collection.",
    )

    dashboard_tasks = list(
        filter(lambda t: t["task_id"] == "daily_dashboard_collection", DASHBOARD_COLLECTION_GROUP.tasks)
    )

    if len(dashboard_tasks) == 0:
        error_msg = "No task with task_id 'daily_dashboard_collection' found in DASHBOARD_COLLECTION_GROUP"
        logger.error(error_msg)
        return create_task_result("error", error=error_msg)

    follow_up_task_id = dashboard_tasks[0].get("task_id")
    daily_dashboard_collection_task = dashboard_tasks[0]
    task_data = dashboard_tasks[0].get("args", {}).copy()
    if DASHBOARD_COLLECTION_GROUP.feature_flag:
        task_data["_feature_flag"] = DASHBOARD_COLLECTION_GROUP.feature_flag

    try:
        _, created = Task.objects.get_or_create(
            name=follow_up_task_id,
            is_system_task=True,
            defaults={
                "description": daily_dashboard_collection_task.get("description", ""),
                "function_name": daily_dashboard_collection_task["function"],
                "task_data": task_data,
                "cron_expression": daily_dashboard_collection_task.get("cron"),
                "status": "pending",
            },
        )
        if created:
            data["Follow-up task creation"] = "success"
        else:
            logger.info(f"Task '{follow_up_task_id}' already exists. Skipping creation of follow-up task.")
            data["Follow-up task creation"] = "skipped"
    except Exception as e:
        logger.error(f"Error creating follow-up task for collecting dashboard reports data: {str(e)}")
        return create_task_result("error", error=f"Creating follow-up task failed: {str(e)}")

    return create_task_result("success", data=data)


def _sync_jobs_atomically(job_results: list) -> list:
    """
    Persist all jobs in a single atomic transaction.

    Returns the list of job IDs that failed to sync.  If any job fails every
    save made in this call is rolled back, keeping JobData.last_timestamp()
    unchanged so the next incremental run retries from the same watermark.

    Note: retry behaviour for the outer Task is handled by the Task model's max_attempts
    mechanism (default: 3 attempts). When this function signals failure the calling task
    returns create_task_result("error"), which marks the Task as failed and allows the
    scheduler to retry it automatically up to max_attempts times via Task.can_retry().
    """
    failed_jobs: list = []
    try:
        with transaction.atomic():
            for job in job_results:
                try:
                    JobData.create_or_update_from_awx(job)
                except Exception as e:
                    logger.error(f"Error creating/updating JobData for job {job['id']}: {str(e)}")
                    failed_jobs.append(job["id"])
            if failed_jobs:
                raise _PartialSyncRollbackError()
    except _PartialSyncRollbackError:
        pass  # transaction rolled back; caller inspects failed_jobs
    return failed_jobs


def _collect_data(task_name: str, **kwargs) -> dict[str, Any]:
    """
    Core data collection logic for incremental dashboard reports collection.

    Used only by collect_dashboard_reports_data. The initial backfill task
    (collect_dashboard_reports_initial_data) uses its own batched flow.
    """
    result = {
        "error": False,
        "message": "",
        "data": {"task_type": task_name, "date_range": {"start": None, "end": None}, "job_count": 0},
    }
    db_name = kwargs.get("database", DEFAULT_DB_NAME)
    until = _parse_dt(kwargs.get("until"))
    since = _parse_dt(kwargs.get("since"))

    if until is None:
        until = datetime.now(tz=UTC)
    if since is None:
        since = JobData.last_timestamp()
        if since is None:
            since = until - timedelta(days=90)
            since = since.replace(hour=0, minute=0, second=0, microsecond=0)
            since = since.astimezone(tz=UTC)

    if since >= until:
        msg = f"Invalid date range: since ({since.isoformat()}) must be before until ({until.isoformat()})"
        logger.error(msg)
        result["error"] = True
        result["message"] = msg
        return result

    start_str = since.isoformat()
    end_str = until.isoformat()

    log_task_execution(
        task_name=task_name, operation="processing", details=f"Collecting dashboard data for: {start_str} to {end_str}"
    )

    try:
        db_connection = get_db_connection(db_name)
        jobs = _collect_jobs(db_connection, since=since, until=until)
    except Exception as e:
        logger.error(f"Error collecting jobs: {str(e)}")
        result["error"] = True
        result["message"] = f"Collecting jobs failed: {str(e)}"
        return result

    failed_jobs = _sync_jobs_atomically(jobs["results"])

    if failed_jobs:
        result["error"] = True
        result["message"] = f"Failed to sync {len(failed_jobs)} job(s): {failed_jobs}"
        return result

    job_count = jobs["count"]
    log_task_execution(
        task_name=task_name,
        operation="completed",
        details=f"Collected and stored data for {job_count} jobs from {start_str} to {end_str}",
    )
    result["data"] = {
        "task_type": task_name,
        "date_range": {"start": start_str, "end": end_str},
        "job_count": job_count,
    }
    return result


def collect_dashboard_reports_initial_data(**kwargs) -> dict[str, Any]:
    """
    One-batch-per-call 90-day historical AWX job data backfill.

    Each invocation processes up to batch_size jobs starting from after_id, then
    either schedules the next batch as a new pending Task or, when the cursor
    reaches max_id, activates the daily_dashboard_collection recurring task.

    Args (all passed via task_data / kwargs):
        since (str | datetime | None): Start of backfill window. Defaults to 90 days ago.
        until (str | datetime | None): End of backfill window. Defaults to now.
        after_id (int | None): Exclusive lower bound for cursor pagination. None on first call.
        max_id (int | None): Upper bound established on first call; carried through batches.
        batch_size (int): Maximum jobs per batch. Defaults to DEFAULT_BATCH_SIZE (5 000).
        database (str): AWX database alias. Defaults to "awx".
    """
    task_name = "collect_dashboard_reports_initial_data"

    until = _parse_dt(kwargs.get("until")) or datetime.now(tz=UTC)
    since = _parse_dt(kwargs.get("since"))
    if since is None:
        since = until - timedelta(days=90)
        since = since.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)

    after_id = kwargs.get("after_id")
    max_id = kwargs.get("max_id")
    batch_size = int(kwargs.get("batch_size", DEFAULT_BATCH_SIZE))
    db_name = kwargs.get("database", DEFAULT_DB_NAME)

    if since >= until:
        msg = f"Invalid date range: since ({since.isoformat()}) must be before until ({until.isoformat()})"
        logger.error(msg)
        return create_task_result("error", error=msg)

    try:
        db_connection = get_db_connection(db_name)
    except Exception as e:
        return create_task_result("error", error=f"DB connection failed: {str(e)}")

    after_id, max_id, early_result = _establish_backfill_cursor(
        db_connection, since, until, after_id, max_id, task_name
    )
    if early_result is not None:
        return early_result

    return _run_backfill_batch(db_connection, since, until, after_id, max_id, batch_size, task_name)


def collect_dashboard_reports_data(**kwargs) -> dict[str, Any]:
    """
    Incrementally collect AWX job data since the last known JobData timestamp.

    Falls back to 90 days ago if no previous records exist.
    Returns a task result dict with status, date range, job count, and any error details.
    """
    task_name = "collect_dashboard_reports_data"
    result = _collect_data(task_name=task_name, **kwargs)
    error = result.get("error", False)

    if error:
        return create_task_result(
            "error", error=result.get("message", "An unknown error occurred during incremental data collection")
        )
    return create_task_result("success", data=result.get("data", {}))


def cleanup_dashboard_reports_old_data(**kwargs) -> dict[str, Any]:
    """
    Delete JobData records with a finished date older than retention_period_days (default: 90).

    Returns a task result dict with the number of deleted records, cutoff date, and any error details.
    """
    retention_period_days = kwargs.get("retention_period_days", 90)
    try:
        retention_period_days = int(retention_period_days)
    except (TypeError, ValueError):
        logger.error(
            "cleanup_dashboard_reports_old_data: retention_period_days=%r is not a valid integer; aborting cleanup",
            retention_period_days,
        )
        return create_task_result("error", error=f"Invalid retention_period_days value: {retention_period_days!r}")
    if retention_period_days < 0:
        logger.warning(
            "cleanup_dashboard_reports_old_data: retention_period_days=%d is negative which would produce a future "
            "cutoff date and delete current records; clamping to 0",
            retention_period_days,
        )
        retention_period_days = 0
    cutoff_date = datetime.now(tz=UTC) - timedelta(days=retention_period_days)
    cutoff_date = cutoff_date.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_date_str = cutoff_date.isoformat()

    log_task_execution(
        task_name="cleanup_dashboard_reports_old_data",
        operation="processing",
        details=f"Cleaning up JobData records older than {cutoff_date_str} (retention period: {retention_period_days} days)",
    )

    try:
        queryset = JobData.objects.filter(finished__lt=cutoff_date)
        jobdata_count = queryset.count()
        queryset.delete()
        log_task_execution(
            task_name="cleanup_dashboard_reports_old_data",
            operation="completed",
            details=f"Deleted {jobdata_count} JobData records finished before {cutoff_date_str}",
        )
        return create_task_result(
            "success",
            data={
                "deleted_records": jobdata_count,
                "cutoff_date": cutoff_date_str,
                "retention_period_days": retention_period_days,
            },
        )
    except Exception as e:
        logger.error(f"Error during cleanup of old JobData records: {str(e)}")
        return create_task_result("error", error=f"Cleanup failed: {str(e)}")
