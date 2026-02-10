"""
Shared helper functions for metrics collection tasks.

This module contains helper functions used by multiple collector tasks.
Single-use helpers remain with their respective task implementations.
"""

import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Constants for repeated strings
MSG_METRICS_UTILITY_NOT_AVAILABLE = "metrics-utility is not available"
MSG_SEGMENT_NOT_AVAILABLE = "segment_not_available"
UTC_OFFSET_SUFFIX = "+00:00"
DEFAULT_DB_NAME = "awx"
DEFAULT_COLLECTORS = ["anonymized_rollups", "config", "job_host_summary", "main_host", "main_jobevent"]

# Import metrics-utility collectors and anonymization functions
try:
    from metrics_utility.anonymized_rollups.anonymized_rollups import (
        anonymize_data as anonymize_rollup_data,
    )
    from metrics_utility.library.anonymize import (
        anonymized_rollups_processor,
        compute_anonymized_rollup_from_raw_data,
    )
    from metrics_utility.library.collectors.controller import (
        config,
        job_host_summary,
        main_host,
        main_jobevent,
    )

    METRICS_UTILITY_AVAILABLE = True
except ImportError as e:
    logger.warning(f"metrics-utility not available: {e}")
    METRICS_UTILITY_AVAILABLE = False

    # Provide fallback attributes for testing when metrics-utility is not available
    anonymize_rollup_data = None
    anonymized_rollups_processor = None
    compute_anonymized_rollup_from_raw_data = None
    config = None
    job_host_summary = None
    main_host = None
    main_jobevent = None


# =============================================================================
# Shared Helper Functions
# =============================================================================


def _get_date_defaults(
    collector_name: str, since_dt: datetime | None, until_dt: datetime | None
) -> tuple[datetime | None, datetime | None]:
    """Get default date values for collectors that require them."""
    # For collectors that require date ranges, provide sensible defaults if none given
    collectors_needing_dates = {"job_host_summary", "main_jobevent", "anonymized_rollups"}

    if collector_name in collectors_needing_dates:
        if since_dt is None:
            since_dt = datetime.now(UTC) - timedelta(days=30)
        if until_dt is None:
            until_dt = datetime.now(UTC)

    return since_dt, until_dt


def _run_anonymized_rollups(
    db_connection, salt: str, since_dt: datetime | None, until_dt: datetime | None
) -> dict[str, Any]:
    """Run the anonymized_rollups collector."""
    return anonymized_rollups_processor(
        db=db_connection,
        salt=salt,
        since=since_dt,
        until=until_dt,
        ship_path=None,
        save_rollups=False,
    )


def _run_config_collector(db_connection) -> dict[str, Any]:
    """Run the config collector."""
    collector_instance = config(db=db_connection)
    return collector_instance.gather()


def _run_job_host_summary_collector(
    db_connection, since_dt: datetime | None, until_dt: datetime | None
) -> dict[str, Any]:
    """Run the job_host_summary collector."""
    if since_dt is not None and until_dt is not None:
        collector_instance = job_host_summary(db=db_connection, since=since_dt, until=until_dt)
    else:
        collector_instance = job_host_summary(db=db_connection)
    return collector_instance.gather()


def _run_main_host_collector(db_connection) -> dict[str, Any]:
    """Run the main_host collector."""
    collector_instance = main_host(db=db_connection)
    return collector_instance.gather()


def _run_main_jobevent_collector(
    db_connection, since_dt: datetime | None, until_dt: datetime | None = None
) -> dict[str, Any]:
    """Run the main_jobevent collector."""
    # Ensure we have valid dates
    if since_dt is None:
        since_dt = datetime.now(UTC) - timedelta(days=30)
    if until_dt is None:
        until_dt = datetime.now(UTC)

    collector_instance = main_jobevent(db=db_connection, since=since_dt, until=until_dt)
    return collector_instance.gather()


def _collect_all_metrics(collectors_list: list, db_connection, since: str, until: str, salt: str) -> dict[str, Any]:
    """
    Collect data from all specified collectors.

    Used by: full_process, collect_metrics
    """
    from ..utils import parse_datetime_string

    all_results = {}

    for collector_name in collectors_list:
        try:
            since_dt = parse_datetime_string(since)
            until_dt = parse_datetime_string(until)
            since_dt, until_dt = _get_date_defaults(collector_name, since_dt, until_dt)

            # Call the appropriate collector function directly
            if collector_name == "anonymized_rollups":
                collector_data = _run_anonymized_rollups(db_connection, salt, since_dt, until_dt)
            elif collector_name == "config":
                collector_data = _run_config_collector(db_connection)
            elif collector_name == "job_host_summary":
                collector_data = _run_job_host_summary_collector(db_connection, since_dt, until_dt)
            elif collector_name == "main_host":
                collector_data = _run_main_host_collector(db_connection)
            elif collector_name == "main_jobevent":
                collector_data = _run_main_jobevent_collector(db_connection, since_dt, until_dt)
            else:
                logger.warning(f"Unknown collector: {collector_name}")
                continue
            all_results[collector_name] = collector_data
            logger.info(f"Successfully collected data from {collector_name}")
        except Exception as e:
            logger.error(f"Error running collector {collector_name}: {str(e)}")
            all_results[collector_name] = {"error": str(e)}

    return all_results


def _prepare_segment_data(
    collectors_list: list, all_results: dict, db_name: str, since: str, until: str, salt: str
) -> dict[str, Any]:
    """
    Prepare anonymized data for Segment.com.

    Used by: full_process, anonymize_data
    """
    segment_data = {
        "collectors_run": collectors_list,
        "collection_summary": {
            "total_collectors": len(collectors_list),
            "successful_collectors": len([k for k, v in all_results.items() if "error" not in v]),
            "failed_collectors": len([k for k, v in all_results.items() if "error" in v]),
            "collection_parameters": {
                "database": db_name,
                "since": since,
                "until": until,
                "salt_used": bool(salt),
            },
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Add the actual anonymized collector results
    for collector_name, data in all_results.items():
        if "error" not in data:
            segment_data[collector_name] = data

    return segment_data


def _collect_hourly_metrics(
    collector_name: str,
    collector_func,
    task_name: str,
    uses_date_range: bool = True,
    **kwargs,
) -> dict[str, Any]:
    """
    Generic helper for hourly metrics collection tasks.

    Used by: collect_job_host_summary_hourly, collect_host_metrics_hourly, collect_main_host_hourly

    Args:
        collector_name: Name of the collector type (e.g., "job_host_summary")
        collector_func: The collector class/function to instantiate
        task_name: Name of the task for logging
        uses_date_range: Whether the collector accepts since/until parameters
        **kwargs: Task parameters

    Returns:
        dict: Task result with collection status
    """
    from ..utils import (
        create_task_result,
        csv_to_json,
        get_db_connection,
        log_task_execution,
        parse_datetime_string,
    )

    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    from django.utils import timezone

    from apps.tasks.models import HourlyMetricsCollection

    # Determine collection hour (default to previous hour)
    hour_timestamp_str = kwargs.get("hour_timestamp")
    collection_hour = None
    if hour_timestamp_str:
        collection_hour = parse_datetime_string(hour_timestamp_str)
    # Fallback to previous hour if no timestamp provided or parsing failed
    if collection_hour is None:
        now = timezone.now()
        collection_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    log_task_execution(task_name, "processing", f"Collecting {collector_name} for hour: {collection_hour.isoformat()}")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        db_connection = get_db_connection(db_name)

        # Build collector parameters
        if uses_date_range:
            since = collection_hour
            until = collection_hour + timedelta(hours=1)
            collector = collector_func(db=db_connection, since=since, until=until)
            collection_params = {
                "database": db_name,
                "since": since.isoformat(),
                "until": until.isoformat(),
            }
        else:
            collector = collector_func(db=db_connection)
            collection_params = {
                "database": db_name,
                "collection_time": collection_hour.isoformat(),
            }

        # Gather and convert data
        csv_file_paths = collector.gather()
        collected_data = csv_to_json(csv_file_paths)

        # Store in HourlyMetricsCollection
        # Use update_or_create to handle retries and scheduler double-triggers
        # The unique_together constraint on (collector_type, collection_timestamp)
        # would cause IntegrityError if we used create() and a record already exists
        hourly_collection, created = HourlyMetricsCollection.objects.update_or_create(
            collector_type=collector_name,
            collection_timestamp=collection_hour,
            defaults={
                "raw_data": collected_data,
                "status": "collected",
                "collection_parameters": collection_params,
                "task_execution_id": kwargs.get("execution_id"),
                "error_message": "",  # Clear any previous error
            },
        )

        action = "Created" if created else "Updated"
        log_task_execution(task_name, "completed", f"{action} hourly collection ID: {hourly_collection.id}")

        return create_task_result(
            "success",
            {
                "task_type": task_name,
                "collector_type": collector_name,
                "collection_id": hourly_collection.id,
                "collection_timestamp": collection_hour.isoformat(),
                "data_size_bytes": hourly_collection.data_size_bytes,
                "records_collected": collected_data.get("total_records", 0),
                "was_retry": not created,
            },
        )

    except Exception as e:
        logger.error(f"Error in {task_name}: {str(e)}")

        # Store failed collection
        # Use update_or_create to handle cases where a record already exists
        # (e.g., a previous attempt created a record, or scheduler double-trigger)
        with contextlib.suppress(Exception):
            HourlyMetricsCollection.objects.update_or_create(
                collector_type=collector_name,
                collection_timestamp=collection_hour,
                defaults={
                    "raw_data": {},
                    "status": "failed",
                    "error_message": str(e),
                    "collection_parameters": {"database": kwargs.get("database", DEFAULT_DB_NAME)},
                },
            )

        return create_task_result("error", error=f"Collection failed: {str(e)}")
