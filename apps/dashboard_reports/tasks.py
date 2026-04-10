import logging
from datetime import datetime, timedelta
from typing import Any

import pytz
from metrics_utility.library.collectors.dashboard import DashboardJobsResultType, dashboard_jobs

from apps.dashboard_reports.models import JobData
from apps.tasks.models import Task
from apps.tasks.task_groups import DASHBOARD_COLLECTION_GROUP
from apps.tasks.utils import create_task_result, get_db_connection, log_task_execution

try:
    from dispatcherd.publish import task
except ImportError:

    def task(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


DEFAULT_DB_NAME = "awx"

logger = logging.getLogger(__name__)


def _collect_jobs(db_connection, since: datetime, until: datetime) -> DashboardJobsResultType:
    """
    Collect dashboard jobs data from the database for the specified date range.
    """
    return dashboard_jobs(db=db_connection, since=since, until=until)


def _collect_data(task_name: str, **kwargs) -> dict[str, Any]:
    """
    Core data collection logic for dashboard reports.
    This function can be called by different tasks with varying parameters.
    """
    result = {
        "error": False,
        "message": "",
        "data": {"task_type": task_name, "date_range": {"start": None, "end": None}, "job_count": 0},
    }
    db_name = kwargs.get("database", DEFAULT_DB_NAME)
    db_connection = None
    until = kwargs.get("until")
    since = kwargs.get("since")

    if until is None:
        # Default to now if not provided
        until = datetime.now(tz=pytz.UTC)
    if since is None:
        # For incremental collection, we want to start from the last timestamp in the JobData table
        since = JobData.last_timestamp()
        if since is None:
            # Default to 90 days ago if no previous timestamp is found
            since = until - timedelta(days=90)
            since = since.replace(hour=0, minute=0, second=0, microsecond=0)
            since = since.astimezone(tz=pytz.UTC)

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
        collector = _collect_jobs(db_connection, since=since, until=until)
        jobs = collector.gather()
    except Exception as e:
        logger.error(f"Error collecting jobs: {str(e)}")
        result["error"] = True
        result["message"] = f"Collecting jobs failed: {str(e)}"
        return result
    finally:
        if db_connection is not None:
            try:
                db_connection.close()
            except Exception:
                logger.warning("Failed to close AWX DB connection in _collect_data()")

    failed_jobs = []
    for job in jobs["results"]:
        try:
            JobData.create_or_update_from_awx(job)
        except Exception as e:
            logger.error(f"Error creating/updating JobData for job {job['id']}: {str(e)}")
            failed_jobs.append(job["id"])

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


@task(queue="metrics_collectors", decorate=False)
def collect_dashboard_reports_initial_data(**kwargs) -> dict[str, Any]:
    task_name = "collect_dashboard_reports_initial_data"
    result = _collect_data(task_name=task_name, **kwargs)

    error = result.get("error", False)

    if error:
        return create_task_result(
            "error", error=result.get("message", "An unknown error occurred during initial data collection")
        )
    data = result.get("data", {})

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
    existing_tasks_count = Task.objects.filter(name=follow_up_task_id, is_system_task=True).count()
    if existing_tasks_count > 0:
        logger.info("Task 'collect_dashboard_reports_data' already exists. Skipping creation of follow-up task.")
        data["Follow-up task creation"] = "skipped"
    else:
        daily_dashboard_collection_task = dashboard_tasks[0]
        task_data = dashboard_tasks[0].get("args", {}).copy()
        if DASHBOARD_COLLECTION_GROUP.feature_flag:
            task_data["_feature_flag"] = DASHBOARD_COLLECTION_GROUP.feature_flag
        try:
            Task.objects.create(
                name=follow_up_task_id,
                description=daily_dashboard_collection_task.get("description", ""),
                function_name=daily_dashboard_collection_task["function"],
                task_data=task_data,
                cron_expression=daily_dashboard_collection_task.get("cron"),
                is_system_task=True,
                status="pending",
            )
            data["Follow-up task creation"] = "success"
        except Exception as e:
            logger.error(f"Error creating follow-up task for collecting dashboard reports data: {str(e)}")
            return create_task_result("error", error=f"Creating follow-up task failed: {str(e)}")

    return create_task_result("success", data=data)


@task(queue="metrics_collectors", decorate=False)
def collect_dashboard_reports_data(**kwargs) -> dict[str, Any]:
    task_name = "collect_dashboard_reports_data"
    result = _collect_data(task_name=task_name, **kwargs)
    error = result.get("error", False)

    if error:
        return create_task_result(
            "error", error=result.get("message", "An unknown error occurred during initial data collection")
        )
    return create_task_result("success", data=result.get("data", {}))


@task(queue="metrics_collectors", decorate=False)
def cleanup_dashboard_reports_old_data(**kwargs) -> dict[str, Any]:
    retention_period_days = kwargs.get("retention_period_days", 90)
    cutoff_date = datetime.now(tz=pytz.UTC) - timedelta(days=retention_period_days)
    cutoff_date = cutoff_date.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_date_str = cutoff_date.isoformat()

    log_task_execution(
        task_name="cleanup_dashboard_reports_old_data",
        operation="processing",
        details=f"Cleaning up JobData records older than {cutoff_date_str} (retention period: {retention_period_days} days)",
    )

    try:
        deleted_count, _ = JobData.objects.filter(finished__lt=cutoff_date).delete()
        log_task_execution(
            task_name="cleanup_dashboard_reports_old_data",
            operation="completed",
            details=f"Deleted {deleted_count} JobData records finished before {cutoff_date_str}",
        )
        return create_task_result(
            "success",
            data={
                "deleted_records": deleted_count,
                "cutoff_date": cutoff_date_str,
                "retention_period_days": retention_period_days,
            },
        )
    except Exception as e:
        logger.error(f"Error during cleanup of old JobData records: {str(e)}")
        return create_task_result("error", error=f"Cleanup failed: {str(e)}")
