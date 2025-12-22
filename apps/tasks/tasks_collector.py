"""
Metrics collection and anonymized data collection tasks for metrics_service.

This module provides tasks for collecting metrics and anonymized data using
the metrics-utility library. These tasks integrate with AWX/Automation Controller
for data collection and analysis.
"""

import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from .utils import (
    create_task_result,
    log_task_execution,
    task_execution_wrapper,
)

logger = logging.getLogger(__name__)

# Constants for repeated strings
MSG_METRICS_UTILITY_NOT_AVAILABLE = "metrics-utility is not available"
MSG_SEGMENT_NOT_AVAILABLE = "segment_not_available"
UTC_OFFSET_SUFFIX = "+00:00"
DEFAULT_DB_NAME = "awx"
DEFAULT_COLLECTORS = ["anonymized_rollups", "config", "job_host_summary", "main_host", "main_jobevent"]

# Import metrics-utility collectors
try:
    from metrics_utility.library.anonymize import anonymized_rollups_processor
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
    anonymized_rollups_processor = None
    config = None
    job_host_summary = None
    main_host = None
    main_jobevent = None

# Import segment.com integration from metrics-utility
try:
    from metrics_utility.library.storage.segment import SEGMENT_AVAILABLE
except ImportError as e:
    logger.warning(f"metrics-utility segment integration not available: {e}")
    SEGMENT_AVAILABLE = False

try:
    from dispatcherd.publish import task
except ImportError:

    def task():
        def decorator(func):
            return func

        return decorator


# =============================================================================
# Helper Functions
# =============================================================================


def _parse_datetime_string(date_str: str | None) -> datetime | None:
    """Parse an ISO datetime string, return None if invalid."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", UTC_OFFSET_SUFFIX))
    except (ValueError, AttributeError):
        return None


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


def _get_db_connection(db_name: str = DEFAULT_DB_NAME):
    """Get a Django database connection."""
    from django.db import connections

    return connections[db_name]


def _generate_salt() -> str:
    """Generate a unique UUID4 salt."""
    import uuid

    return str(uuid.uuid4())


def _send_to_segment(user_id: str, event_name: str, segment_data: dict) -> str:
    """
    Send data to Segment.com using direct analytics.track().

    Returns:
        str: "success" if sent, "segment_not_available" if Segment is not configured,
             or "error: <message>" if sending failed.
    """
    if not SEGMENT_AVAILABLE:
        return MSG_SEGMENT_NOT_AVAILABLE

    try:
        import json
        import uuid

        # Generate unique message ID for debugging
        message_id = str(uuid.uuid4())[:8]
        data_size = len(json.dumps(segment_data).encode("utf-8"))

        log_task_execution(
            "segment_send",
            "processing",
            f"Sending data to Segment.com (ID: {message_id}, Size: {data_size} bytes)",
        )

        # Import and configure Segment directly
        from django.conf import settings
        from segment import analytics

        analytics.write_key = getattr(settings, "SEGMENT_WRITE_KEY", None)

        # Send one simple track message
        analytics.track(
            user_id=user_id,
            event=event_name,
            properties={
                "artifact_name": f"metrics_collection_{user_id}",
                "data": segment_data,
                "upload_timestamp": datetime.now(UTC).isoformat(),
                "message_info": {
                    "message_id": message_id,
                    "data_size": data_size,
                    "source": "metrics-service",
                },
            },
        )

        # Flush to ensure the message is sent
        analytics.flush()

        logger.info(f"Successfully sent metrics to Segment.com (ID: {message_id}, Size: {data_size} bytes)")
        return "success"

    except Exception as e:
        logger.error(f"Error sending data to Segment.com: {str(e)}")
        return f"error: {str(e)}"


def _csv_to_json(csv_file_paths: list[str]) -> dict[str, Any]:
    """
    Convert CSV files returned by metrics-utility collectors to JSON format.

    Args:
        csv_file_paths: List of CSV file paths returned by collector.gather()

    Returns:
        dict: JSON representation of the CSV data with metadata
    """
    import csv
    import os

    if not csv_file_paths:
        return {"records": [], "file_count": 0, "total_records": 0}

    all_records = []
    file_count = 0

    for csv_path in csv_file_paths:
        if not os.path.exists(csv_path):
            logger.warning(f"CSV file not found: {csv_path}")
            continue

        try:
            with open(csv_path, encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                records = list(reader)
                all_records.extend(records)
                file_count += 1

            # Clean up CSV file after reading
            with contextlib.suppress(Exception):
                os.remove(csv_path)

        except Exception as e:
            logger.error(f"Error reading CSV file {csv_path}: {e}")
            continue

    return {
        "records": all_records,
        "file_count": file_count,
        "total_records": len(all_records),
    }


# =============================================================================
# Collector Helper Functions
# =============================================================================


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


def _run_single_collector(collector_name: str, db_connection, since: str, until: str, salt: str) -> dict[str, Any]:
    """Run a single collector and return its data."""
    since_dt = _parse_datetime_string(since)
    until_dt = _parse_datetime_string(until)
    since_dt, until_dt = _get_date_defaults(collector_name, since_dt, until_dt)

    collector_functions = {
        "anonymized_rollups": lambda: _run_anonymized_rollups(db_connection, salt, since_dt, until_dt),
        "config": lambda: _run_config_collector(db_connection),
        "job_host_summary": lambda: _run_job_host_summary_collector(db_connection, since_dt, until_dt),
        "main_host": lambda: _run_main_host_collector(db_connection),
        "main_jobevent": lambda: _run_main_jobevent_collector(db_connection, since_dt, until_dt),
    }

    collector_func = collector_functions.get(collector_name)
    if collector_func is None:
        raise ValueError(f"Unknown collector: {collector_name}")

    return collector_func()


def _collect_all_metrics(collectors_list: list, db_connection, since: str, until: str, salt: str) -> dict[str, Any]:
    """Collect data from all specified collectors."""
    all_results = {}

    for collector_name in collectors_list:
        try:
            collector_data = _run_single_collector(collector_name, db_connection, since, until, salt)
            all_results[collector_name] = collector_data
            logger.info(f"Successfully collected data from {collector_name}")
        except ValueError:
            logger.warning(f"Unknown collector: {collector_name}")
            continue
        except Exception as e:
            logger.error(f"Error running collector {collector_name}: {str(e)}")
            all_results[collector_name] = {"error": str(e)}

    return all_results


def _prepare_segment_data(
    collectors_list: list, all_results: dict, db_name: str, since: str, until: str, salt: str
) -> dict[str, Any]:
    """Prepare anonymized data for Segment.com."""
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


# =============================================================================
# Aggregation Helpers (for daily rollups)
# =============================================================================


def _aggregate_collector_data(collections: list) -> dict:
    """
    Aggregate metrics from hourly collections.

    This is a generic aggregator that works for all collector types.

    Args:
        collections: List of HourlyMetricsCollection objects

    Returns:
        dict: Aggregated metrics with hourly snapshots
    """
    aggregated = {
        "total_records": 0,
        "hourly_snapshots": [],
    }

    for collection in collections:
        data = collection.raw_data
        record_count = len(data) if isinstance(data, list) else 1

        aggregated["total_records"] += record_count
        aggregated["hourly_snapshots"].append(
            {
                "hour": collection.collection_timestamp.hour,
                "collection_id": collection.id,
                "record_count": record_count,
                "timestamp": collection.collection_timestamp.isoformat(),
            }
        )

    return aggregated


def _is_sensitive_field(field_name: str) -> bool:
    """Check if field contains sensitive data that should be hashed."""
    sensitive_fields = {"name", "hostname", "username", "email", "ip_address", "host", "user"}
    return any(sensitive in field_name.lower() for sensitive in sensitive_fields)


def _anonymize_dict(data: dict, salt: str) -> dict:
    """Apply anonymization to dictionary values."""
    import hashlib

    anonymized = {}
    # Fields that should not be anonymized
    structural_fields = {"hourly_snapshots", "collection_id", "hour", "timestamp", "record_count", "total_records"}

    for key, value in data.items():
        if key in structural_fields:
            anonymized[key] = value
        elif isinstance(value, str) and _is_sensitive_field(key):
            anonymized[key] = hashlib.sha256(f"{value}{salt}".encode()).hexdigest()[:16]
        elif isinstance(value, dict):
            anonymized[key] = _anonymize_dict(value, salt)
        elif isinstance(value, list):
            anonymized[key] = [_anonymize_dict(item, salt) if isinstance(item, dict) else item for item in value]
        else:
            anonymized[key] = value

    return anonymized


def _anonymize_daily_summary(aggregated_metrics: dict, config_data: dict, salt: str) -> dict:
    """Apply anonymization to daily summary using metrics-utility patterns."""
    return {
        "job_host_summary": _anonymize_dict(aggregated_metrics.get("job_host_summary", {}), salt),
        "main_jobevent": _anonymize_dict(aggregated_metrics.get("main_jobevent", {}), salt),
        "main_host": _anonymize_dict(aggregated_metrics.get("main_host", {}), salt),
        "config": _anonymize_dict(config_data, salt),
    }


# =============================================================================
# Hourly Collection Helper
# =============================================================================


def _collect_hourly_metrics(
    collector_name: str,
    collector_func,
    task_name: str,
    uses_date_range: bool = True,
    **kwargs,
) -> dict[str, Any]:
    """
    Generic helper for hourly metrics collection tasks.

    Args:
        collector_name: Name of the collector type (e.g., "job_host_summary")
        collector_func: The collector class/function to instantiate
        task_name: Name of the task for logging
        uses_date_range: Whether the collector accepts since/until parameters
        **kwargs: Task parameters

    Returns:
        dict: Task result with collection status
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    from django.utils import timezone

    from apps.tasks.models import HourlyMetricsCollection

    # Determine collection hour (default to previous hour)
    hour_timestamp_str = kwargs.get("hour_timestamp")
    collection_hour = None
    if hour_timestamp_str:
        collection_hour = _parse_datetime_string(hour_timestamp_str)
    # Fallback to previous hour if no timestamp provided or parsing failed
    if collection_hour is None:
        now = timezone.now()
        collection_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    log_task_execution(task_name, "processing", f"Collecting {collector_name} for hour: {collection_hour.isoformat()}")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        db_connection = _get_db_connection(db_name)

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
        collected_data = _csv_to_json(csv_file_paths)

        # Store in HourlyMetricsCollection
        hourly_collection = HourlyMetricsCollection.objects.create(
            collector_type=collector_name,
            collection_timestamp=collection_hour,
            raw_data=collected_data,
            status="collected",
            collection_parameters=collection_params,
            task_execution_id=kwargs.get("execution_id"),
        )

        log_task_execution(task_name, "completed", f"Stored hourly collection ID: {hourly_collection.id}")

        return create_task_result(
            "success",
            {
                "task_type": task_name,
                "collector_type": collector_name,
                "collection_id": hourly_collection.id,
                "collection_timestamp": collection_hour.isoformat(),
                "data_size_bytes": hourly_collection.data_size_bytes,
                "records_collected": collected_data.get("total_records", 0),
            },
        )

    except Exception as e:
        logger.error(f"Error in {task_name}: {str(e)}")

        # Store failed collection
        with contextlib.suppress(Exception):
            HourlyMetricsCollection.objects.create(
                collector_type=collector_name,
                collection_timestamp=collection_hour,
                raw_data={},
                status="failed",
                error_message=str(e),
                collection_parameters={"database": kwargs.get("database", DEFAULT_DB_NAME)},
            )

        return create_task_result("error", error=f"Collection failed: {str(e)}")


# =============================================================================
# Task Functions
# =============================================================================


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_anonymous_metrics")
def collect_anonymous_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect anonymous metrics using metrics-utility library.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)
            - salt (str): Salt for anonymization (optional, auto-generated UUID4)
            - ship_path (str): Path for shipping data (optional)
            - save_rollups (bool): Whether to save rollups (optional, default: True)

    Returns:
        dict: Task result with collected metrics data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_anonymous_metrics", "processing", "Collecting anonymous metrics")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        since = kwargs.get("since")
        until = kwargs.get("until")
        salt = kwargs.get("salt", _generate_salt())
        ship_path = kwargs.get("ship_path")
        save_rollups = kwargs.get("save_rollups", True)

        db_connection = _get_db_connection(db_name)

        metrics_data = anonymized_rollups_processor(
            db=db_connection, salt=salt, since=since, until=until, ship_path=ship_path, save_rollups=save_rollups
        )

        return create_task_result(
            "success",
            {
                "task_type": "collect_anonymous_metrics",
                "metrics_data": metrics_data,
                "collector_type": "anonymized_rollups",
                "parameters_used": {
                    "database": db_name,
                    "since": since,
                    "until": until,
                    "salt": salt,
                    "ship_path": ship_path,
                    "save_rollups": save_rollups,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_anonymous_metrics: {str(e)}")
        # Include parameters_used even on error for debugging
        return create_task_result(
            "error",
            error=f"Collection failed: {str(e)}",
            data={
                "parameters_used": {
                    "database": kwargs.get("database", DEFAULT_DB_NAME),
                    "since": kwargs.get("since"),
                    "until": kwargs.get("until"),
                    "salt": kwargs.get("salt"),
                    "ship_path": kwargs.get("ship_path"),
                    "save_rollups": kwargs.get("save_rollups", True),
                },
            },
        )


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_config_metrics")
def collect_config_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect configuration metrics using metrics-utility library.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')

    Returns:
        dict: Task result with collected configuration data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_config_metrics", "processing", "Collecting configuration metrics")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        db_connection = _get_db_connection(db_name)

        collector = config(db=db_connection)
        config_data = collector.gather()

        return create_task_result(
            "success",
            {
                "task_type": "collect_config_metrics",
                "config_data": config_data,
                "collector_type": "config",
                "parameters_used": {"database": db_name},
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_config_metrics: {str(e)}")
        return create_task_result("error", error=f"Collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_job_host_summary")
def collect_job_host_summary(**kwargs) -> dict[str, Any]:
    """
    Collect job host summary metrics using metrics-utility library.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)

    Returns:
        dict: Task result with collected job host summary data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_job_host_summary", "processing", "Collecting job host summary metrics")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        since_dt = _parse_datetime_string(kwargs.get("since"))
        until_dt = _parse_datetime_string(kwargs.get("until"))

        db_connection = _get_db_connection(db_name)

        if since_dt is not None and until_dt is not None:
            collector = job_host_summary(db=db_connection, since=since_dt, until=until_dt)
        else:
            collector = job_host_summary(db=db_connection)

        summary_data = collector.gather()

        return create_task_result(
            "success",
            {
                "task_type": "collect_job_host_summary",
                "summary_data": summary_data,
                "collector_type": "job_host_summary",
                "parameters_used": {
                    "database": db_name,
                    "since": kwargs.get("since"),
                    "until": kwargs.get("until"),
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_job_host_summary: {str(e)}")
        return create_task_result("error", error=f"Collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_host_metrics")
def collect_host_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect host metrics using metrics-utility library.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)

    Returns:
        dict: Task result with collected host metrics data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_host_metrics", "processing", "Collecting host metrics")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        since_dt = _parse_datetime_string(kwargs.get("since"))

        db_connection = _get_db_connection(db_name)

        if since_dt is not None:
            collector = main_jobevent(db=db_connection, since=since_dt)
        else:
            collector = main_jobevent(db=db_connection)

        host_data = collector.gather()

        return create_task_result(
            "success",
            {
                "task_type": "collect_host_metrics",
                "host_data": host_data,
                "collector_type": "main_jobevent",
                "parameters_used": {"database": db_name, "since": kwargs.get("since")},
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_host_metrics: {str(e)}")
        return create_task_result("error", error=f"Collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_all_metrics")
def collect_all_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect all available metrics using multiple collectors.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)
            - salt (str): Salt for anonymization (optional)
            - collectors (list): List of specific collectors to run (optional)

    Returns:
        dict: Task result with all collected metrics data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_all_metrics", "processing", "Collecting all metrics")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        db_connection = _get_db_connection(db_name)
        since = kwargs.get("since")
        until = kwargs.get("until")
        salt = kwargs.get("salt", "default-salt")
        collectors_list = kwargs.get("collectors", ["anonymized_rollups", "config", "main_jobevent"])

        all_results = {}
        for collector_name in collectors_list:
            try:
                collector_data = _run_single_collector(collector_name, db_connection, since, until, salt)
                all_results[collector_name] = collector_data
            except Exception as e:
                logger.error(f"Error running collector {collector_name}: {str(e)}")
                all_results[collector_name] = {"error": str(e)}

        return create_task_result(
            "success",
            {
                "task_type": "collect_all_metrics",
                "all_results": all_results,
                "collectors_run": collectors_list,
                "parameters_used": {
                    "database": db_name,
                    "since": since,
                    "until": until,
                    "salt": salt,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_all_metrics: {str(e)}")
        return create_task_result("error", error=f"Collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("full_process")
def full_process(**kwargs) -> dict[str, Any]:
    """
    Collect, anonymize, and send metrics data to Segment.com.

    Args:
        **kwargs: Task data containing collection and sending parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)
            - salt (str): Salt for anonymization (optional, auto-generated UUID4)
            - user_id (str): User ID for Segment tracking (optional)
            - event_name (str): Event name for Segment tracking (default: 'metrics_collected')
            - collectors (list): List of specific collectors to run (optional)
            - send_to_segment (bool): Whether to send data to Segment (default: True)

    Returns:
        dict: Task result with collection, anonymization, and sending status
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("full_process", "processing", "Starting full metrics collection and Segment.com upload")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        db_connection = _get_db_connection(db_name)
        since = kwargs.get("since")
        until = kwargs.get("until")
        salt = kwargs.get("salt", _generate_salt())
        user_id = kwargs.get("user_id", _generate_salt())
        event_name = kwargs.get("event_name", "metrics_collected")
        collectors_list = kwargs.get("collectors", ["anonymized_rollups", "config", "job_host_summary"])
        send_to_segment = kwargs.get("send_to_segment", True)

        # Step 1: Collect metrics
        log_task_execution("full_process", "processing", "Collecting metrics data")
        all_results = _collect_all_metrics(collectors_list, db_connection, since, until, salt)

        # Step 2: Prepare anonymized data
        log_task_execution("full_process", "processing", "Preparing anonymized data for Segment.com")
        segment_data = _prepare_segment_data(collectors_list, all_results, db_name, since, until, salt)

        # Step 3: Send to Segment.com if enabled
        segment_status = "skipped"
        if send_to_segment:
            segment_status = _send_to_segment(user_id, event_name, segment_data)

        return create_task_result(
            "success",
            {
                "task_type": "full_process",
                "collection_results": {
                    "segment_data": segment_data,
                    "collectors_run": collectors_list,
                    "successful_collections": len([k for k, v in all_results.items() if "error" not in v]),
                    "failed_collections": len([k for k, v in all_results.items() if "error" in v]),
                    "collection_errors": {k: v.get("error") for k, v in all_results.items() if "error" in v},
                },
                "anonymization_status": "completed",
                "segment_status": segment_status,
                "parameters_used": {
                    "database": db_name,
                    "since": since,
                    "until": until,
                    "salt": salt,
                    "collectors": collectors_list,
                    "send_to_segment": send_to_segment,
                    "event_name": event_name,
                    "user_id": user_id,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in full_process: {str(e)}")
        return create_task_result("error", error=f"Full process failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_metrics")
def collect_metrics(**kwargs) -> dict[str, Any]:
    """
    Unified task to collect metrics using multiple collectors.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)
            - collectors (list): List of specific collectors to run (default: all available)

    Returns:
        dict: Task result with collected metrics data from all collectors
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_metrics", "processing", "Collecting metrics from all collectors")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        db_connection = _get_db_connection(db_name)
        since = kwargs.get("since")
        until = kwargs.get("until")
        collectors_list = kwargs.get("collectors", DEFAULT_COLLECTORS)

        all_results = _collect_all_metrics(collectors_list, db_connection, since, until, "default-salt")

        return create_task_result(
            "success",
            {
                "task_type": "collect_metrics",
                "collection_results": {
                    "collectors_run": collectors_list,
                    "successful_collections": len([k for k, v in all_results.items() if "error" not in v]),
                    "failed_collections": len([k for k, v in all_results.items() if "error" in v]),
                    "collection_errors": {k: v.get("error") for k, v in all_results.items() if "error" in v},
                    "collected_data": all_results,
                },
                "parameters_used": {
                    "database": db_name,
                    "since": since,
                    "until": until,
                    "collectors": collectors_list,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_metrics: {str(e)}")
        return create_task_result("error", error=f"Metrics collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("anonymize_data")
def anonymize_data(**kwargs) -> dict[str, Any]:
    """
    Dedicated task to anonymize collected metrics data.

    Args:
        **kwargs: Task data containing anonymization parameters:
            - data (dict): Raw metrics data to anonymize (required)
            - salt (str): Salt for anonymization (auto-generated UUID4 if not provided)

    Returns:
        dict: Task result with anonymized data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("anonymize_data", "processing", "Anonymizing collected metrics data")

    try:
        raw_data = kwargs.get("data")
        if not raw_data:
            return create_task_result("error", error="No data provided for anonymization")

        salt = kwargs.get("salt", _generate_salt())
        output_format = kwargs.get("output_format", "segment_ready")

        anonymized_data = _prepare_segment_data(
            raw_data.get("collectors_run", []),
            raw_data.get("collected_data", {}),
            raw_data.get("database", "unknown"),
            raw_data.get("since"),
            raw_data.get("until"),
            salt,
        )

        return create_task_result(
            "success",
            {
                "task_type": "anonymize_data",
                "anonymized_data": anonymized_data,
                "anonymization_status": "completed",
                "parameters_used": {
                    "salt": salt,
                    "output_format": output_format,
                    "input_data_size": len(str(raw_data)),
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in anonymize_data: {str(e)}")
        return create_task_result("error", error=f"Anonymization failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("full_process_anonymize")
def full_process_anonymize(**kwargs) -> dict[str, Any]:
    """
    Collect anonymized metrics and send directly to Segment.com.

    Args:
        **kwargs: Task data containing collection and sending parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)
            - salt (str): Salt for anonymization (optional, auto-generated UUID4)
            - user_id (str): User ID for Segment tracking (default: 'anonymous-user')
            - event_name (str): Event name for Segment (default: 'anonymized_metrics_collected')
            - send_to_segment (bool): Whether to send data to Segment (default: True)

    Returns:
        dict: Task result with collection and transmission status
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution(
        "full_process_anonymize", "processing", "Starting anonymized metrics collection and Segment.com upload"
    )

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        db_connection = _get_db_connection(db_name)
        since = kwargs.get("since")
        until = kwargs.get("until")
        salt = kwargs.get("salt", _generate_salt())
        user_id = kwargs.get("user_id", "anonymous-user")
        event_name = kwargs.get("event_name", "anonymized_metrics_collected")
        send_to_segment = kwargs.get("send_to_segment", True)

        # Parse and apply defaults for dates
        since_dt = _parse_datetime_string(since)
        until_dt = _parse_datetime_string(until)
        since_dt, until_dt = _get_date_defaults("anonymized_rollups", since_dt, until_dt)

        # Step 1: Collect anonymized metrics
        log_task_execution("full_process_anonymize", "processing", "Collecting anonymized metrics data")
        anonymized_data = anonymized_rollups_processor(
            db=db_connection,
            salt=salt,
            since=since_dt,
            until=until_dt,
            ship_path=None,
            save_rollups=False,
        )

        # Step 2: Send to Segment.com if enabled
        segment_status = "skipped"
        if send_to_segment:
            segment_data = {
                "anonymized_rollups": anonymized_data,
                "collection_metadata": {
                    "database": db_name,
                    "since": since,
                    "until": until,
                    "salt": salt,
                    "collection_timestamp": datetime.now(UTC).isoformat(),
                },
            }
            segment_status = _send_to_segment(user_id, event_name, segment_data)

        return create_task_result(
            "success",
            {
                "task_type": "full_process_anonymize",
                "collection_status": "completed",
                "anonymized_data_size": len(str(anonymized_data)),
                "segment_status": segment_status,
                "parameters_used": {
                    "database": db_name,
                    "since": since,
                    "until": until,
                    "salt": salt,
                    "send_to_segment": send_to_segment,
                    "event_name": event_name,
                    "user_id": user_id,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in full_process_anonymize: {str(e)}")
        return create_task_result("error", error=f"Anonymized process failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("send_to_segment")
def send_to_segment(**kwargs) -> dict[str, Any]:
    """
    Dedicated task to send anonymized data to Segment.com.

    Args:
        **kwargs: Task data containing transmission parameters:
            - data (dict): Anonymized data to send (required)
            - user_id (str): User ID for tracking (default: 'anonymous-user')
            - event_name (str): Event name (default: 'metrics_sent')

    Returns:
        dict: Task result with transmission status
    """
    log_task_execution("send_to_segment", "processing", "Sending anonymized data to Segment.com")

    try:
        anonymized_data = kwargs.get("data")
        if not anonymized_data:
            return create_task_result("error", error="No data provided for transmission")

        user_id = kwargs.get("user_id", "anonymous-user")
        event_name = kwargs.get("event_name", "metrics_sent")

        segment_status = _send_to_segment(user_id, event_name, anonymized_data)

        return create_task_result(
            "success",
            {
                "task_type": "send_to_segment",
                "segment_status": segment_status,
                "transmission_completed": segment_status == "success",
                "parameters_used": {
                    "user_id": user_id,
                    "event_name": event_name,
                    "data_size": len(str(anonymized_data)),
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in send_to_segment: {str(e)}")
        return create_task_result("error", error=f"Segment transmission failed: {str(e)}")


# =============================================================================
# Hourly Collection Tasks
# =============================================================================


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_job_host_summary_hourly")
def collect_job_host_summary_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect job host summary metrics hourly and store in HourlyMetricsCollection.

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    return _collect_hourly_metrics(
        collector_name="job_host_summary",
        collector_func=job_host_summary,
        task_name="collect_job_host_summary_hourly",
        uses_date_range=True,
        **kwargs,
    )


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_host_metrics_hourly")
def collect_host_metrics_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect host metrics (main_jobevent) hourly and store in HourlyMetricsCollection.

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    return _collect_hourly_metrics(
        collector_name="main_jobevent",
        collector_func=main_jobevent,
        task_name="collect_host_metrics_hourly",
        uses_date_range=True,
        **kwargs,
    )


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_main_host_hourly")
def collect_main_host_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect main_host metrics hourly and store in HourlyMetricsCollection.

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    return _collect_hourly_metrics(
        collector_name="main_host",
        collector_func=main_host,
        task_name="collect_main_host_hourly",
        uses_date_range=False,
        **kwargs,
    )


# =============================================================================
# Daily Rollup Task
# =============================================================================


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("daily_metrics_rollup")
def daily_metrics_rollup(**kwargs) -> dict[str, Any]:
    """
    Create daily summary from hourly collections.

    This task:
    1. Queries all hourly collections for the previous day
    2. Aggregates metrics (sums, averages, counts)
    3. Stores references to all 24 hourly snapshots
    4. Collects config data (once per day)
    5. Creates DailyMetricsSummary record

    Args:
        **kwargs: Task data containing:
            - summary_date (str): Date to summarize (YYYY-MM-DD, defaults to yesterday)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with summary ID and statistics
    """
    from datetime import date

    from django.utils import timezone

    from apps.tasks.models import DailyMetricsSummary, HourlyMetricsCollection

    # Determine summary date (default to yesterday)
    summary_date_str = kwargs.get("summary_date")
    if summary_date_str:
        summary_date = date.fromisoformat(summary_date_str)
    else:
        summary_date = timezone.now().date() - timedelta(days=1)

    log_task_execution("daily_metrics_rollup", "processing", f"Creating daily summary for: {summary_date}")

    try:
        # Query all hourly collections for this date
        start_datetime = timezone.make_aware(datetime.combine(summary_date, datetime.min.time()))
        end_datetime = start_datetime + timedelta(days=1)

        hourly_collections = HourlyMetricsCollection.objects.filter(
            collection_timestamp__gte=start_datetime, collection_timestamp__lt=end_datetime, status="collected"
        ).order_by("collector_type", "collection_timestamp")

        # Group by collector type
        collections_by_type: dict[str, list] = {}
        for collection in hourly_collections:
            if collection.collector_type not in collections_by_type:
                collections_by_type[collection.collector_type] = []
            collections_by_type[collection.collector_type].append(collection)

        # Build hourly collection IDs map
        hourly_collection_ids = {
            collector_type: [c.id for c in collections] for collector_type, collections in collections_by_type.items()
        }

        # Aggregate metrics for each collector type
        aggregated_metrics = {}
        missing_hours = []
        collector_types = ["job_host_summary", "main_host", "main_jobevent"]

        for collector_type in collector_types:
            collections = collections_by_type.get(collector_type, [])

            # Check for missing hours (should have 24 collections)
            if len(collections) < 24:
                collected_hours = {c.collection_timestamp.hour for c in collections}
                missing_hours.extend([f"{collector_type}:{hour}" for hour in range(24) if hour not in collected_hours])

            # Use the generic aggregator
            aggregated_metrics[collector_type] = _aggregate_collector_data(collections)

        # Collect config data (once per day)
        config_data = {}
        if METRICS_UTILITY_AVAILABLE:
            try:
                db_name = kwargs.get("database", DEFAULT_DB_NAME)
                db_connection = _get_db_connection(db_name)
                config_collector = config(db=db_connection)
                config_data = config_collector.gather()
            except Exception as e:
                logger.error(f"Failed to collect config data: {str(e)}")
                config_data = {"error": str(e)}

        # Create DailyMetricsSummary
        daily_summary = DailyMetricsSummary.objects.create(
            summary_date=summary_date,
            aggregated_metrics=aggregated_metrics,
            hourly_collection_ids=hourly_collection_ids,
            config_data=config_data,
            status="aggregated",
            hourly_collections_count=hourly_collections.count(),
            missing_hours=missing_hours,
            aggregation_completed_at=timezone.now(),
            rollup_task_execution_id=kwargs.get("execution_id"),
        )

        # Mark hourly collections as processed
        hourly_collections.update(status="processed")

        log_task_execution(
            "daily_metrics_rollup",
            "completed",
            f"Created daily summary ID: {daily_summary.id} with {hourly_collections.count()} hourly collections",
        )

        return create_task_result(
            "success",
            {
                "task_type": "daily_metrics_rollup",
                "summary_id": daily_summary.id,
                "summary_date": str(summary_date),
                "hourly_collections_count": hourly_collections.count(),
                "missing_hours": missing_hours,
                "aggregated_collectors": list(aggregated_metrics.keys()),
            },
        )

    except Exception as e:
        logger.error(f"Error in daily_metrics_rollup: {str(e)}")
        return create_task_result("error", error=f"Rollup failed: {str(e)}")


# =============================================================================
# Anonymization and Sending Tasks
# =============================================================================


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("daily_anonymize_and_prepare")
def daily_anonymize_and_prepare(**kwargs) -> dict[str, Any]:
    """
    Anonymize daily summary and prepare payload for Segment.

    This task:
    1. Fetches DailyMetricsSummary for specified date
    2. Applies anonymization using hash functions
    3. Creates AnonymizedMetricsPayload record
    4. Does NOT send (separate task handles sending)

    Args:
        **kwargs: Task data containing:
            - summary_date (str): Date to anonymize (YYYY-MM-DD, defaults to yesterday)
            - salt (str): Anonymization salt (auto-generated if not provided)

    Returns:
        dict: Task result with payload ID
    """
    from datetime import date

    from django.utils import timezone

    from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

    # Determine summary date
    summary_date_str = kwargs.get("summary_date")
    if summary_date_str:
        summary_date = date.fromisoformat(summary_date_str)
    else:
        summary_date = timezone.now().date() - timedelta(days=1)

    log_task_execution("daily_anonymize_and_prepare", "processing", f"Anonymizing daily summary for: {summary_date}")

    try:
        # Get daily summary
        daily_summary = DailyMetricsSummary.objects.get(summary_date=summary_date, status="aggregated")

        # Generate or use provided salt
        salt = kwargs.get("salt", _generate_salt())

        # Apply anonymization
        anonymized_data = _anonymize_daily_summary(daily_summary.aggregated_metrics, daily_summary.config_data, salt)

        # Add metadata
        aggregation_timestamp = (
            daily_summary.aggregation_completed_at.isoformat() if daily_summary.aggregation_completed_at else None
        )
        anonymized_data["summary_metadata"] = {
            "summary_date": str(summary_date),
            "hourly_collections_count": daily_summary.hourly_collections_count,
            "missing_hours": daily_summary.missing_hours,
            "aggregation_timestamp": aggregation_timestamp,
        }

        # Create AnonymizedMetricsPayload
        payload = AnonymizedMetricsPayload.objects.create(
            summary_date=summary_date,
            anonymized_data=anonymized_data,
            status="pending",
            daily_summary=daily_summary,
            anonymization_task_execution_id=kwargs.get("execution_id"),
            segment_event_name=kwargs.get("event_name", "daily_metrics_rollup"),
            segment_user_id=kwargs.get("user_id", _generate_salt()),
        )

        # Update daily summary status
        daily_summary.status = "anonymized"
        daily_summary.save()

        log_task_execution("daily_anonymize_and_prepare", "completed", f"Created anonymized payload ID: {payload.id}")

        return create_task_result(
            "success",
            {
                "task_type": "daily_anonymize_and_prepare",
                "payload_id": payload.id,
                "summary_date": str(summary_date),
                "payload_size_bytes": payload.payload_size_bytes,
            },
        )

    except DailyMetricsSummary.DoesNotExist:
        error_msg = f"No daily summary found for {summary_date} with status=aggregated"
        logger.error(error_msg)
        return create_task_result("error", error=error_msg)

    except Exception as e:
        logger.error(f"Error in daily_anonymize_and_prepare: {str(e)}")
        return create_task_result("error", error=f"Anonymization failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("send_anonymized_to_segment")
def send_anonymized_to_segment(**kwargs) -> dict[str, Any]:
    """
    Send anonymized payload to Segment.

    This task:
    1. Fetches AnonymizedMetricsPayload records with status=pending
    2. Sends to Segment using _send_to_segment helper
    3. Updates payload status based on result
    4. Handles retries for failed sends

    Args:
        **kwargs: Task data containing:
            - payload_id (int): Specific payload ID to send (optional)
            - max_payloads (int): Maximum number of payloads to send (default: 5)

    Returns:
        dict: Task result with send statistics
    """
    from django.utils import timezone

    from apps.tasks.models import AnonymizedMetricsPayload

    max_payloads = kwargs.get("max_payloads", 5)
    payload_id = kwargs.get("payload_id")

    log_task_execution("send_anonymized_to_segment", "processing", "Sending anonymized payloads to Segment")

    try:
        # Get payloads to send
        if payload_id:
            payloads = AnonymizedMetricsPayload.objects.filter(id=payload_id, status__in=["pending", "retry"])
        else:
            payloads = AnonymizedMetricsPayload.objects.filter(status__in=["pending", "retry"]).order_by("created")[
                :max_payloads
            ]

        results = {"sent": 0, "failed": 0, "skipped": 0}

        for payload in payloads:
            # Check retry limit
            if payload.status == "retry" and not payload.can_retry():
                payload.status = "failed"
                payload.error_message = "Max retries exceeded"
                payload.save()
                results["skipped"] += 1
                continue

            # Update status to sending
            payload.status = "sending"
            payload.save()

            try:
                segment_status = _send_to_segment(
                    user_id=payload.segment_user_id,
                    event_name=payload.segment_event_name,
                    segment_data=payload.anonymized_data,
                )

                if segment_status == "success":
                    payload.status = "sent"
                    payload.sent_at = timezone.now()
                    payload.error_message = ""
                    results["sent"] += 1

                    # Update daily summary status
                    payload.daily_summary.status = "sent"
                    payload.daily_summary.save()
                else:
                    payload.status = "retry"
                    payload.retry_count += 1
                    payload.error_message = f"Send failed: {segment_status}"
                    results["failed"] += 1

                payload.save()

            except Exception as e:
                logger.error(f"Error sending payload {payload.id}: {str(e)}")
                payload.status = "retry"
                payload.retry_count += 1
                payload.error_message = str(e)
                payload.save()
                results["failed"] += 1

        log_task_execution(
            "send_anonymized_to_segment",
            "completed",
            f"Sent: {results['sent']}, Failed: {results['failed']}, Skipped: {results['skipped']}",
        )

        return create_task_result(
            "success",
            {
                "task_type": "send_anonymized_to_segment",
                "results": results,
                "total_processed": sum(results.values()),
            },
        )

    except Exception as e:
        logger.error(f"Error in send_anonymized_to_segment: {str(e)}")
        return create_task_result("error", error=f"Send task failed: {str(e)}")
