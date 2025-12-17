"""
Metrics collection and anonymized data collection tasks for metrics_service.

This module provides tasks for collecting metrics and anonymized data using
the metrics-utility library. These tasks integrate with AWX/Automation Controller
for data collection and analysis.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from .utils import (
    create_task_result,
    log_task_execution,
    task_execution_wrapper,
)

logger = logging.getLogger(__name__)

# Constants for repeated strings
MSG_METRICS_UTILITY_NOT_AVAILABLE = "metrics-utility is not available"
LABEL_METRICS_COLLECTION = "Metrics Collection"
LABEL_DB_CONNECTION = "Database name from Django settings (default: 'awx')"
LABEL_START_DATE = "Start date for collection (ISO format)"
LABEL_END_DATE = "End date for collection (ISO format)"
EXAMPLE_START_DATE = "2024-01-01T00:00:00Z"
UTC_OFFSET_SUFFIX = "+00:00"

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
    from metrics_utility.library.storage import StorageSegment
    from metrics_utility.library.storage.segment import SEGMENT_AVAILABLE
except ImportError as e:
    logger.warning(f"metrics-utility segment integration not available: {e}")
    SEGMENT_AVAILABLE = False
    StorageSegment = None

try:
    from dispatcherd.publish import task
except ImportError:

    def task():
        def decorator(func):
            return func

        return decorator


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_anonymous_metrics")
def collect_anonymous_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect anonymous metrics using metrics-utility library.

    This task uses the anonymized_rollups_processor from metrics-utility to gather
    anonymous system metrics without exposing sensitive information.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)
            - salt (str): Salt for anonymization (optional, default: 'default-salt')
            - ship_path (str): Path for shipping data (optional, default: None)
            - save_rollups (bool): Whether to save rollups (optional, default: True)

    Returns:
        dict: Task result with collected metrics data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_anonymous_metrics", "processing", "Collecting anonymous metrics")

    try:
        # Get parameters from kwargs
        import uuid

        from django.db import connections

        db_name = kwargs.get("database", "awx")
        since = kwargs.get("since")
        until = kwargs.get("until")
        # Generate a unique UUID4 salt if not provided
        salt = kwargs.get("salt", str(uuid.uuid4()))
        ship_path = kwargs.get("ship_path")
        save_rollups = kwargs.get("save_rollups", True)

        # Get the Django db connection
        db_connection = connections[db_name]

        # Call anonymized_rollups_processor
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
        return create_task_result(
            "error",
            error=f"Collection failed: {str(e)}",
            data={
                "parameters_used": {
                    "database": locals().get("db_name", "unknown"),
                    "since": locals().get("since"),
                    "until": locals().get("until"),
                    "salt": locals().get("salt", "not-generated"),
                    "ship_path": locals().get("ship_path"),
                    "save_rollups": locals().get("save_rollups", True),
                }
            },
        )


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_config_metrics")
def collect_config_metrics(**kwargs) -> dict[str, Any]:
    """
    Collect configuration metrics using metrics-utility library.

    This task uses the config collector from metrics-utility to gather
    system configuration information from the AWX database.

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
        from django.db import connections

        # Get db name from kwargs, default to 'awx' (defined in defaults.py)
        db_name = kwargs.get("database", "awx")

        # Get the Django db connection for the AWX database
        db_connection = connections[db_name]

        # Create collector instance with Django database connection
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

    This task uses the job_host_summary collector from metrics-utility to gather
    job execution statistics and host performance data.

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
        from datetime import datetime

        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        since = kwargs.get("since")
        until = kwargs.get("until")

        # Convert string dates to datetime objects if provided (ISO format support)
        since_dt = None
        until_dt = None

        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", UTC_OFFSET_SUFFIX))
            except (ValueError, AttributeError):
                since_dt = None

        if until:
            try:
                until_dt = datetime.fromisoformat(until.replace("Z", UTC_OFFSET_SUFFIX))
            except (ValueError, AttributeError):
                until_dt = None

        db_connection = connections[db_name]
        # Create collector instance with parsed datetime objects (only if not None)
        if since_dt is not None and until_dt is not None:
            collector = job_host_summary(db=db_connection, since=since_dt, until=until_dt)
        else:
            collector = job_host_summary(db=db_connection)

        # Gather data
        summary_data = collector.gather()

        return create_task_result(
            "success",
            {
                "task_type": "collect_job_host_summary",
                "summary_data": summary_data,
                "collector_type": "job_host_summary",
                "parameters_used": {"database": db_name, "since": since, "until": until},
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

    This task uses the main_jobevent collector from metrics-utility to gather
    host performance and system metrics.

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
        from datetime import datetime

        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        since = kwargs.get("since")

        # Convert string date to datetime object if provided (ISO format support)
        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", UTC_OFFSET_SUFFIX))
            except (ValueError, AttributeError):
                since_dt = None

        db_connection = connections[db_name]
        # Create collector instance with parsed datetime object (only if not None)
        if since_dt is not None:
            collector = main_jobevent(db=db_connection, since=since_dt)
        else:
            collector = main_jobevent(db=db_connection)

        # Gather data
        host_data = collector.gather()

        return create_task_result(
            "success",
            {
                "task_type": "collect_host_metrics",
                "host_data": host_data,
                "collector_type": "main_jobevent",
                "parameters_used": {"database": db_name, "since": since},
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

    This task runs multiple collectors in sequence to gather comprehensive
    metrics data from the system.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)
            - salt (str): Salt for anonymization (optional, default: 'default-salt')
            - ship_path (str): Path for shipping data (optional, default: None)
            - save_rollups (bool): Whether to save rollups (optional, default: True)
            - collectors (list): List of specific collectors to run (optional)

    Returns:
        dict: Task result with all collected metrics data
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_all_metrics", "processing", "Collecting all metrics")

    try:
        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        db_connection = connections[db_name]
        since = kwargs.get("since")
        until = kwargs.get("until")
        salt = kwargs.get("salt", "default-salt")
        ship_path = kwargs.get("ship_path")
        save_rollups = kwargs.get("save_rollups", True)
        collectors_list = kwargs.get("collectors", ["anonymized_rollups", "config", "main_jobevent"])

        all_results = {}

        # Run each requested collector using the helper function with ISO timestamp support
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
                    "ship_path": ship_path,
                    "save_rollups": save_rollups,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_all_metrics: {str(e)}")
        return create_task_result("error", error=f"Collection failed: {str(e)}")


def _parse_datetime_string(date_str: str | None) -> datetime | None:
    """Parse an ISO datetime string, return None if invalid."""
    from datetime import datetime

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
    from datetime import datetime, timedelta

    # For collectors that require date ranges, provide sensible defaults if none given
    if since_dt is None and collector_name in ["job_host_summary", "main_jobevent", "anonymized_rollups"]:
        since_dt = datetime.now(UTC) - timedelta(days=30)

    if until_dt is None and collector_name in ["job_host_summary", "main_jobevent", "anonymized_rollups"]:
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
        ship_path=None,  # Don't save locally, will send to Segment
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
    # main_host collector doesn't accept date parameters, only db connection
    collector_instance = main_host(db=db_connection)
    return collector_instance.gather()


def _run_main_jobevent_collector(
    db_connection, since_dt: datetime | None, until_dt: datetime | None = None
) -> dict[str, Any]:
    """Run the main_jobevent collector."""
    # main_jobevent requires since and until dates, so ensure we have them
    if since_dt is None:
        from datetime import datetime, timedelta

        since_dt = datetime.now(UTC) - timedelta(days=30)

    if until_dt is None:
        from datetime import datetime

        until_dt = datetime.now(UTC)

    collector_instance = main_jobevent(db=db_connection, since=since_dt, until=until_dt)
    return collector_instance.gather()


def _run_single_collector(collector_name: str, db_connection, since: str, until: str, salt: str) -> dict[str, Any]:
    """Run a single collector and return its data."""
    # Convert string dates to datetime objects if provided
    since_dt = _parse_datetime_string(since)
    until_dt = _parse_datetime_string(until)

    # Get defaults for date-sensitive collectors
    since_dt, until_dt = _get_date_defaults(collector_name, since_dt, until_dt)

    # Dispatch to appropriate collector function
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
    from datetime import datetime

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


def _send_to_segment(segment_write_key: str, user_id: str, event_name: str, segment_data: dict) -> str:
    """Send data to Segment.com using direct analytics.track() for guaranteed single message."""
    try:
        import json
        import uuid
        from datetime import datetime

        # Generate unique message ID for debugging
        message_id = str(uuid.uuid4())[:8]
        data_size = len(json.dumps(segment_data).encode("utf-8"))

        log_task_execution(
            "full_process",
            "processing",
            f"Sending anonymized data to Segment.com (ID: {message_id}, Size: {data_size} bytes)",
        )

        # Create simple direct Segment.com track message (bypassing StorageSegment complexity)
        if not SEGMENT_AVAILABLE:
            return "segment_not_available"

        # Import and configure Segment directly
        from segment import analytics

        analytics.write_key = segment_write_key

        # Send one simple track message
        analytics.track(
            user_id=user_id,
            event=event_name,
            properties={
                "artifact_name": f"metrics_collection_{user_id}",
                "data": segment_data,
                "upload_timestamp": datetime.now(UTC).isoformat(),
                "message_info": {
                    "message_type": "simple_direct",
                    "message_id": message_id,
                    "data_size": data_size,
                    "source": "metrics-service",
                    "function": "_send_to_segment",
                },
            },
        )

        # Flush to ensure the message is sent
        analytics.flush()

        logger.info(
            f"Successfully sent anonymized metrics to Segment.com using direct analytics.track() "
            f"(ID: {message_id}, Size: {data_size} bytes)"
        )
        return "success"

    except Exception as e:
        logger.error(f"Error sending data to Segment.com: {str(e)}")
        return f"error: {str(e)}"


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("full_process")
def full_process(**kwargs) -> dict[str, Any]:
    """
    Collect, anonymize, and send metrics data to Segment.com using metrics-utility library.

    This task performs a complete end-to-end process:
    1. Collects metrics using multiple collectors
    2. Anonymizes the collected data
    3. Sends the anonymized data to Segment.com

    Args:
        **kwargs: Task data containing collection and sending parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)
            - salt (str): Salt for anonymization (optional, default: 'default-salt')
            - segment_write_key (str): Segment.com write key for analytics (required)
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
        import uuid

        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        db_connection = connections[db_name]
        since = kwargs.get("since")
        until = kwargs.get("until")
        # Generate a unique UUID4 salt if not provided
        salt = kwargs.get("salt", str(uuid.uuid4()))
        segment_write_key = kwargs.get("segment_write_key", "NA")
        user_id = kwargs.get("user_id", str(uuid.uuid4()))
        event_name = kwargs.get("event_name", "metrics_collected")
        collectors_list = kwargs.get("collectors", ["anonymized_rollups", "config", "job_host_summary"])
        send_to_segment = kwargs.get("send_to_segment", True)

        # segment_write_key now has a default value, but still validate it's present
        if send_to_segment and not segment_write_key:
            return create_task_result("error", error="segment_write_key is required when send_to_segment is True")

        # Step 1: Collect metrics using multiple collectors
        log_task_execution("full_process", "processing", "Collecting metrics data")
        all_results = _collect_all_metrics(collectors_list, db_connection, since, until, salt)

        # Step 2: Prepare anonymized data for Segment
        log_task_execution("full_process", "processing", "Preparing anonymized data for Segment.com")
        segment_data = _prepare_segment_data(collectors_list, all_results, db_name, since, until, salt)

        # Step 3: Send to Segment.com if enabled
        segment_status = "skipped"
        if send_to_segment and SEGMENT_AVAILABLE:
            segment_status = _send_to_segment(segment_write_key, user_id, event_name, segment_data)

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

    This task consolidates all metrics collection functionality into a single
    unified interface, replacing individual collector tasks.

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
        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        db_connection = connections[db_name]
        since = kwargs.get("since")
        until = kwargs.get("until")
        collectors_list = kwargs.get(
            "collectors", ["anonymized_rollups", "config", "job_host_summary", "main_host", "main_jobevent"]
        )

        # Collect data from all specified collectors
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

    This task takes raw metrics data and applies anonymization techniques
    to protect sensitive information while preserving analytical value.

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
        import uuid

        # Get parameters from kwargs
        raw_data = kwargs.get("data")
        if not raw_data:
            return create_task_result("error", error="No data provided for anonymization")

        # Generate a unique UUID4 salt if not provided
        salt = kwargs.get("salt", str(uuid.uuid4()))
        output_format = kwargs.get("output_format", "segment_ready")

        # Prepare anonymized data for output
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

    This task performs a focused anonymized data collection process:
    1. Runs anonymized_rollups_processor to collect anonymized metrics
    2. Sends the anonymized data directly to Segment.com

    Args:
        **kwargs: Task data containing collection and sending parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (optional)
            - until (str): End date for collection (optional)
            - salt (str): Salt for anonymization (optional, auto-generated UUID4)
            - segment_write_key (str): Segment.com write key for analytics (has default)
            - user_id (str): User ID for Segment tracking (default: 'anonymous-user')
            - event_name (str): Event name for Segment tracking (default: 'anonymized_metrics_collected')
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
        import uuid

        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        db_connection = connections[db_name]
        since = kwargs.get("since")
        until = kwargs.get("until")
        # Generate a unique UUID4 salt if not provided
        salt = kwargs.get("salt", str(uuid.uuid4()))
        segment_write_key = kwargs.get("segment_write_key", "NA")
        user_id = kwargs.get("user_id", "anonymous-user")
        event_name = kwargs.get("event_name", "anonymized_metrics_collected")
        send_to_segment = kwargs.get("send_to_segment", True)

        # Convert string dates to datetime objects if provided
        from datetime import datetime

        since_dt = None
        until_dt = None

        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", UTC_OFFSET_SUFFIX))
            except (ValueError, AttributeError):
                since_dt = None

        if until:
            try:
                until_dt = datetime.fromisoformat(until.replace("Z", UTC_OFFSET_SUFFIX))
            except (ValueError, AttributeError):
                until_dt = None

        # Apply default date ranges if None (required by anonymized_rollups_processor)
        since_dt, until_dt = _get_date_defaults("anonymized_rollups", since_dt, until_dt)

        # Step 1: Collect anonymized metrics using anonymized_rollups_processor
        log_task_execution("full_process_anonymize", "processing", "Collecting anonymized metrics data")

        anonymized_data = anonymized_rollups_processor(
            db=db_connection,
            salt=salt,
            since=since_dt,
            until=until_dt,
            ship_path=None,  # Don't save locally, will send to Segment
            save_rollups=False,
        )

        # Step 2: Send to Segment.com if enabled
        segment_status = "skipped"
        if send_to_segment and SEGMENT_AVAILABLE:
            # Prepare anonymized data for Segment transmission
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
            # Send actual anonymized data to Segment
            segment_status = _send_to_segment(segment_write_key, user_id, event_name, segment_data)

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
@task_execution_wrapper("debug_segment_messages")
def debug_segment_messages(**kwargs) -> dict[str, Any]:
    """
    Debug helper to trace exactly what Segment messages are being sent.

    This task helps identify why multiple messages might be appearing by
    logging detailed information about each message send operation.
    """
    log_task_execution("debug_segment_messages", "processing", "Starting Segment.com debugging")

    try:
        # Test with small known data
        debug_data = {
            "debug_test": True,
            "timestamp": "2024-01-01T12:00:00Z",
            "test_size": "small",
            "message": "Debug test - this should be ONE message only",
        }

        segment_write_key = kwargs.get("segment_write_key", "NA")
        user_id = kwargs.get("user_id", "debug-user")
        event_name = kwargs.get("event_name", "debug_segment_test")

        # Call _send_to_segment directly with debug data
        result = _send_to_segment(segment_write_key, user_id, event_name, debug_data)

        return create_task_result(
            "success",
            {
                "task_type": "debug_segment_messages",
                "debug_message": "Check logs for message ID and size - should see exactly ONE message",
                "segment_status": result,
                "debug_data_size": len(str(debug_data)),
                "instructions": "Look in Segment.com for exactly one event with message_type='simple_direct'",
            },
        )

    except Exception as e:
        logger.error(f"Error in debug_segment_messages: {str(e)}")
        return create_task_result("error", error=f"Debug failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("test_segment_track")
def test_segment_track(**kwargs) -> dict[str, Any]:
    """
    Send a simple test track message to Segment.com to verify consolidated messaging.

    This task sends a minimal test message to verify that the consolidated
    messaging feature is working correctly and sends only one message.

    Args:
        **kwargs: Task data containing test parameters:
            - message (str): Test message content (default: 'Test message from metrics-service')
            - segment_write_key (str): Segment.com write key (has default)
            - user_id (str): User ID for tracking (default: 'test-user')
            - event_name (str): Event name (default: 'test_track_message')

    Returns:
        dict: Task result with transmission status
    """
    log_task_execution("test_segment_track", "processing", "Sending test track message to Segment.com")

    try:
        # Get parameters from kwargs
        test_message = kwargs.get("message", "Test message from metrics-service")
        segment_write_key = kwargs.get("segment_write_key", "NA")
        user_id = kwargs.get("user_id", "test-user")
        event_name = kwargs.get("event_name", "test_track_message")

        # Prepare simple test data
        test_data = {
            "test_message": test_message,
            "test_info": {
                "source": "metrics-service",
                "function": "test_segment_track",
                "consolidated_messaging": True,
                "timestamp": "2024-01-01T12:00:00Z",
            },
            "test_metadata": {"user_id": user_id, "event_name": event_name, "message_size": len(test_message)},
        }

        # Send to Segment.com if available
        if SEGMENT_AVAILABLE:
            segment_status = _send_to_segment(segment_write_key, user_id, event_name, test_data)
        else:
            segment_status = "segment_not_available"

        return create_task_result(
            "success",
            {
                "task_type": "test_segment_track",
                "test_message": test_message,
                "segment_status": segment_status,
                "transmission_completed": segment_status == "success",
                "consolidated_messaging_used": True,
                "parameters_used": {
                    "user_id": user_id,
                    "event_name": event_name,
                    "message": test_message,
                    "data_size": len(str(test_data)),
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in test_segment_track: {str(e)}")
        return create_task_result("error", error=f"Test track message failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("send_to_segment")
def send_to_segment(**kwargs) -> dict[str, Any]:
    """
    Dedicated task to send anonymized data to Segment.com.

    This task handles the transmission of anonymized metrics data
    to Segment.com for analytics purposes.

    Args:
        **kwargs: Task data containing transmission parameters:
            - data (dict): Anonymized data to send (required)
            - segment_write_key (str): Segment.com write key (has default)
            - user_id (str): User ID for tracking (default: 'anonymous-user')
            - event_name (str): Event name (default: 'metrics_sent')

    Returns:
        dict: Task result with transmission status
    """
    log_task_execution("send_to_segment", "processing", "Sending anonymized data to Segment.com")

    try:
        # Get parameters from kwargs
        anonymized_data = kwargs.get("data")
        if not anonymized_data:
            return create_task_result("error", error="No data provided for transmission")

        segment_write_key = kwargs.get("segment_write_key", "NA")
        user_id = kwargs.get("user_id", "anonymous-user")
        event_name = kwargs.get("event_name", "metrics_sent")

        # Send to Segment.com if available
        if SEGMENT_AVAILABLE:
            segment_status = _send_to_segment(segment_write_key, user_id, event_name, anonymized_data)
        else:
            segment_status = "segment_not_available"

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


# Hourly Collection Tasks


def _csv_to_json(csv_file_paths: list[str]) -> dict[str, Any]:
    """
    Convert CSV files returned by metrics-utility collectors to JSON format.

    The metrics-utility collectors return CSV file paths. This function reads
    those CSV files and converts them to JSON for storage in the database.

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
            with open(csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                records = list(reader)
                all_records.extend(records)
                file_count += 1

            # Clean up CSV file after reading
            try:
                os.remove(csv_path)
            except Exception as e:
                logger.warning(f"Could not remove CSV file {csv_path}: {e}")

        except Exception as e:
            logger.error(f"Error reading CSV file {csv_path}: {e}")
            continue

    return {
        "records": all_records,
        "file_count": file_count,
        "total_records": len(all_records),
    }


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_job_host_summary_hourly")
def collect_job_host_summary_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect job host summary metrics hourly and store in HourlyMetricsCollection.

    This task collects metrics for the previous hour and persists raw data
    for later daily aggregation and anonymization.

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional, defaults to previous hour)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    from datetime import datetime, timedelta

    from django.db import connections
    from django.utils import timezone

    from apps.tasks.models import HourlyMetricsCollection

    # Determine collection hour (default to previous hour)
    hour_timestamp_str = kwargs.get("hour_timestamp")
    if hour_timestamp_str:
        collection_hour = datetime.fromisoformat(hour_timestamp_str.replace("Z", "+00:00"))
    else:
        now = timezone.now()
        collection_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    # Calculate time range for this hour
    since = collection_hour
    until = collection_hour + timedelta(hours=1)

    collection_hour_str = collection_hour.isoformat()
    log_task_execution(
        "collect_job_host_summary_hourly", "processing", f"Collecting job host summary for hour: {collection_hour_str}"
    )

    try:
        db_name = kwargs.get("database", "awx")
        db_connection = connections[db_name]

        # Call metrics-utility collector (returns CSV file paths)
        collector = job_host_summary(db=db_connection, since=since, until=until)
        csv_file_paths = collector.gather()

        # Convert CSV to JSON for database storage
        summary_data = _csv_to_json(csv_file_paths)

        # Store in HourlyMetricsCollection
        hourly_collection = HourlyMetricsCollection.objects.create(
            collector_type="job_host_summary",
            collection_timestamp=collection_hour,
            raw_data=summary_data,
            status="collected",
            collection_parameters={
                "database": db_name,
                "since": since.isoformat(),
                "until": until.isoformat(),
            },
            task_execution_id=kwargs.get("execution_id"),  # Link to TaskExecution if available
        )

        log_task_execution(
            "collect_job_host_summary_hourly", "completed", f"Stored hourly collection ID: {hourly_collection.id}"
        )

        return create_task_result(
            "success",
            {
                "task_type": "collect_job_host_summary_hourly",
                "collector_type": "job_host_summary",
                "collection_id": hourly_collection.id,
                "collection_timestamp": collection_hour.isoformat(),
                "data_size_bytes": hourly_collection.data_size_bytes,
                "records_collected": len(summary_data) if isinstance(summary_data, list) else 1,
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_job_host_summary_hourly: {str(e)}")

        # Store failed collection
        try:
            HourlyMetricsCollection.objects.create(
                collector_type="job_host_summary",
                collection_timestamp=collection_hour,
                raw_data={},
                status="failed",
                error_message=str(e),
                collection_parameters={
                    "database": kwargs.get("database", "awx"),
                    "since": since.isoformat(),
                    "until": until.isoformat(),
                },
            )
        except Exception:
            # If even creating the failed record fails, just log it
            pass

        return create_task_result("error", error=f"Collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_host_metrics_hourly")
def collect_host_metrics_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect host metrics (main_jobevent) hourly and store in HourlyMetricsCollection.

    This task collects job event metrics for the previous hour and persists raw data
    for later daily aggregation and anonymization.

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional, defaults to previous hour)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    from datetime import datetime, timedelta

    from django.db import connections
    from django.utils import timezone

    from apps.tasks.models import HourlyMetricsCollection

    # Determine collection hour (default to previous hour)
    hour_timestamp_str = kwargs.get("hour_timestamp")
    if hour_timestamp_str:
        collection_hour = datetime.fromisoformat(hour_timestamp_str.replace("Z", "+00:00"))
    else:
        now = timezone.now()
        collection_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    # Calculate time range for this hour
    since = collection_hour
    until = collection_hour + timedelta(hours=1)

    collection_hour_str = collection_hour.isoformat()
    log_task_execution(
        "collect_host_metrics_hourly", "processing", f"Collecting host metrics for hour: {collection_hour_str}"
    )

    try:
        db_name = kwargs.get("database", "awx")
        db_connection = connections[db_name]

        # Call metrics-utility collector (main_jobevent) - returns CSV file paths
        collector = main_jobevent(db=db_connection, since=since, until=until)
        csv_file_paths = collector.gather()

        # Convert CSV to JSON for database storage
        host_data = _csv_to_json(csv_file_paths)

        # Store in HourlyMetricsCollection
        hourly_collection = HourlyMetricsCollection.objects.create(
            collector_type="main_jobevent",
            collection_timestamp=collection_hour,
            raw_data=host_data,
            status="collected",
            collection_parameters={
                "database": db_name,
                "since": since.isoformat(),
                "until": until.isoformat(),
            },
            task_execution_id=kwargs.get("execution_id"),
        )

        log_task_execution(
            "collect_host_metrics_hourly", "completed", f"Stored hourly collection ID: {hourly_collection.id}"
        )

        return create_task_result(
            "success",
            {
                "task_type": "collect_host_metrics_hourly",
                "collector_type": "main_jobevent",
                "collection_id": hourly_collection.id,
                "collection_timestamp": collection_hour.isoformat(),
                "data_size_bytes": hourly_collection.data_size_bytes,
                "records_collected": len(host_data) if isinstance(host_data, list) else 1,
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_host_metrics_hourly: {str(e)}")

        # Store failed collection
        try:
            HourlyMetricsCollection.objects.create(
                collector_type="main_jobevent",
                collection_timestamp=collection_hour,
                raw_data={},
                status="failed",
                error_message=str(e),
                collection_parameters={
                    "database": kwargs.get("database", "awx"),
                    "since": since.isoformat(),
                    "until": until.isoformat(),
                },
            )
        except Exception:
            pass

        return create_task_result("error", error=f"Collection failed: {str(e)}")


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_main_host_hourly")
def collect_main_host_hourly(**kwargs) -> dict[str, Any]:
    """
    Collect main_host metrics hourly and store in HourlyMetricsCollection.

    This task collects host inventory metrics for the previous hour and persists raw data
    for later daily aggregation and anonymization.

    Args:
        **kwargs: Task data containing:
            - hour_timestamp (str): ISO timestamp for the hour to collect (optional, defaults to previous hour)
            - database (str): Database name (default: 'awx')

    Returns:
        dict: Task result with collection status and record ID
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    from datetime import datetime, timedelta

    from django.db import connections
    from django.utils import timezone

    from apps.tasks.models import HourlyMetricsCollection

    # Determine collection hour (default to previous hour)
    hour_timestamp_str = kwargs.get("hour_timestamp")
    if hour_timestamp_str:
        collection_hour = datetime.fromisoformat(hour_timestamp_str.replace("Z", "+00:00"))
    else:
        now = timezone.now()
        collection_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    collection_hour_str = collection_hour.isoformat()
    log_task_execution(
        "collect_main_host_hourly", "processing", f"Collecting main_host metrics for hour: {collection_hour_str}"
    )

    try:
        db_name = kwargs.get("database", "awx")
        db_connection = connections[db_name]

        # Call metrics-utility collector (main_host) - returns CSV file paths
        # Note: main_host doesn't accept since/until parameters
        collector = main_host(db=db_connection)
        csv_file_paths = collector.gather()

        # Convert CSV to JSON for database storage
        host_data = _csv_to_json(csv_file_paths)

        # Store in HourlyMetricsCollection
        hourly_collection = HourlyMetricsCollection.objects.create(
            collector_type="main_host",
            collection_timestamp=collection_hour,
            raw_data=host_data,
            status="collected",
            collection_parameters={
                "database": db_name,
                "collection_time": collection_hour.isoformat(),
            },
            task_execution_id=kwargs.get("execution_id"),
        )

        log_task_execution(
            "collect_main_host_hourly", "completed", f"Stored hourly collection ID: {hourly_collection.id}"
        )

        return create_task_result(
            "success",
            {
                "task_type": "collect_main_host_hourly",
                "collector_type": "main_host",
                "collection_id": hourly_collection.id,
                "collection_timestamp": collection_hour.isoformat(),
                "data_size_bytes": hourly_collection.data_size_bytes,
                "records_collected": len(host_data) if isinstance(host_data, list) else 1,
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_main_host_hourly: {str(e)}")

        # Store failed collection
        try:
            HourlyMetricsCollection.objects.create(
                collector_type="main_host",
                collection_timestamp=collection_hour,
                raw_data={},
                status="failed",
                error_message=str(e),
                collection_parameters={
                    "database": kwargs.get("database", "awx"),
                    "collection_time": collection_hour.isoformat(),
                },
            )
        except Exception:
            pass

        return create_task_result("error", error=f"Collection failed: {str(e)}")


# Daily Rollup Task


def _aggregate_job_host_summary(collections: list) -> dict:
    """
    Aggregate job_host_summary metrics from hourly collections.

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

        # Count total records
        if isinstance(data, list):
            aggregated["total_records"] += len(data)
        elif isinstance(data, dict):
            aggregated["total_records"] += 1

        # Store hourly snapshot reference
        aggregated["hourly_snapshots"].append(
            {
                "hour": collection.collection_timestamp.hour,
                "collection_id": collection.id,
                "record_count": len(data) if isinstance(data, list) else 1,
                "timestamp": collection.collection_timestamp.isoformat(),
            }
        )

    return aggregated


def _aggregate_main_jobevent(collections: list) -> dict:
    """
    Aggregate main_jobevent metrics from hourly collections.

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

        # Count total records
        if isinstance(data, list):
            aggregated["total_records"] += len(data)
        elif isinstance(data, dict):
            aggregated["total_records"] += 1

        # Store hourly snapshot reference
        aggregated["hourly_snapshots"].append(
            {
                "hour": collection.collection_timestamp.hour,
                "collection_id": collection.id,
                "record_count": len(data) if isinstance(data, list) else 1,
                "timestamp": collection.collection_timestamp.isoformat(),
            }
        )

    return aggregated


def _aggregate_main_host(collections: list) -> dict:
    """
    Aggregate main_host metrics from hourly collections.

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

        # Count total records
        if isinstance(data, list):
            aggregated["total_records"] += len(data)
        elif isinstance(data, dict):
            aggregated["total_records"] += 1

        # Store hourly snapshot reference
        aggregated["hourly_snapshots"].append(
            {
                "hour": collection.collection_timestamp.hour,
                "collection_id": collection.id,
                "record_count": len(data) if isinstance(data, list) else 1,
                "timestamp": collection.collection_timestamp.isoformat(),
            }
        )

    return aggregated


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
    from datetime import date, datetime, timedelta

    from django.db import connections
    from django.utils import timezone

    from apps.tasks.models import DailyMetricsSummary, HourlyMetricsCollection

    # Determine summary date (default to yesterday)
    summary_date_str = kwargs.get("summary_date")
    if summary_date_str:
        summary_date = date.fromisoformat(summary_date_str)
    else:
        summary_date = (timezone.now().date() - timedelta(days=1))

    log_task_execution("daily_metrics_rollup", "processing", f"Creating daily summary for: {summary_date}")

    try:
        # Query all hourly collections for this date
        start_datetime = timezone.make_aware(datetime.combine(summary_date, datetime.min.time()))
        end_datetime = start_datetime + timedelta(days=1)

        hourly_collections = HourlyMetricsCollection.objects.filter(
            collection_timestamp__gte=start_datetime, collection_timestamp__lt=end_datetime, status="collected"
        ).order_by("collector_type", "collection_timestamp")

        # Group by collector type
        collections_by_type = {}
        for collection in hourly_collections:
            if collection.collector_type not in collections_by_type:
                collections_by_type[collection.collector_type] = []
            collections_by_type[collection.collector_type].append(collection)

        # Build hourly collection IDs map
        hourly_collection_ids = {}
        for collector_type, collections in collections_by_type.items():
            hourly_collection_ids[collector_type] = [c.id for c in collections]

        # Aggregate metrics for each collector type
        aggregated_metrics = {}
        missing_hours = []

        for collector_type in ["job_host_summary", "main_host", "main_jobevent"]:
            collections = collections_by_type.get(collector_type, [])

            # Check for missing hours (should have 24 collections)
            if len(collections) < 24:
                collected_hours = {c.collection_timestamp.hour for c in collections}
                missing_hours.extend([f"{collector_type}:{hour}" for hour in range(24) if hour not in collected_hours])

            # Aggregate metrics based on collector type
            if collector_type == "job_host_summary":
                aggregated_metrics[collector_type] = _aggregate_job_host_summary(collections)
            elif collector_type == "main_jobevent":
                aggregated_metrics[collector_type] = _aggregate_main_jobevent(collections)
            elif collector_type == "main_host":
                aggregated_metrics[collector_type] = _aggregate_main_host(collections)

        # Collect config data (once per day)
        config_data = {}
        if METRICS_UTILITY_AVAILABLE:
            try:
                db_name = kwargs.get("database", "awx")
                db_connection = connections[db_name]
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


# Anonymization and Sending Tasks


def _is_sensitive_field(field_name: str) -> bool:
    """
    Check if field contains sensitive data that should be hashed.

    Args:
        field_name: Field name to check

    Returns:
        bool: True if field is sensitive, False otherwise
    """
    sensitive_fields = ["name", "hostname", "username", "email", "ip_address", "host", "user"]
    return any(sensitive in field_name.lower() for sensitive in sensitive_fields)


def _anonymize_dict(data: dict, salt: str) -> dict:
    """
    Apply anonymization to dictionary values.

    Args:
        data: Dictionary to anonymize
        salt: Salt for hashing

    Returns:
        dict: Anonymized dictionary
    """
    import hashlib

    anonymized = {}

    for key, value in data.items():
        if key in ["hourly_snapshots", "collection_id", "hour", "timestamp", "record_count", "total_records"]:
            # Don't anonymize structural/metadata fields
            anonymized[key] = value
        elif isinstance(value, str) and _is_sensitive_field(key):
            # Hash sensitive string fields
            anonymized[key] = hashlib.sha256(f"{value}{salt}".encode()).hexdigest()[:16]
        elif isinstance(value, dict):
            # Recursively anonymize nested dicts
            anonymized[key] = _anonymize_dict(value, salt)
        elif isinstance(value, list):
            # Anonymize list items if they're dicts
            anonymized[key] = [_anonymize_dict(item, salt) if isinstance(item, dict) else item for item in value]
        else:
            # Keep numeric/aggregate values as-is
            anonymized[key] = value

    return anonymized


def _anonymize_daily_summary(aggregated_metrics: dict, config_data: dict, salt: str) -> dict:
    """
    Apply anonymization to daily summary using metrics-utility patterns.

    Args:
        aggregated_metrics: Aggregated metrics from daily rollup
        config_data: Configuration data
        salt: Salt for anonymization

    Returns:
        dict: Anonymized data
    """
    anonymized = {
        "job_host_summary": _anonymize_dict(aggregated_metrics.get("job_host_summary", {}), salt),
        "main_jobevent": _anonymize_dict(aggregated_metrics.get("main_jobevent", {}), salt),
        "main_host": _anonymize_dict(aggregated_metrics.get("main_host", {}), salt),
        "config": _anonymize_dict(config_data, salt),
    }

    return anonymized


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
    import uuid
    from datetime import date, timedelta

    from django.utils import timezone

    from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

    # Determine summary date
    summary_date_str = kwargs.get("summary_date")
    if summary_date_str:
        summary_date = date.fromisoformat(summary_date_str)
    else:
        summary_date = (timezone.now().date() - timedelta(days=1))

    log_task_execution("daily_anonymize_and_prepare", "processing", f"Anonymizing daily summary for: {summary_date}")

    try:
        # Get daily summary
        daily_summary = DailyMetricsSummary.objects.get(summary_date=summary_date, status="aggregated")

        # Generate or use provided salt
        salt = kwargs.get("salt", str(uuid.uuid4()))

        # Apply anonymization to aggregated metrics
        anonymized_data = _anonymize_daily_summary(daily_summary.aggregated_metrics, daily_summary.config_data, salt)

        # Add metadata
        anonymized_data["summary_metadata"] = {
            "summary_date": str(summary_date),
            "hourly_collections_count": daily_summary.hourly_collections_count,
            "missing_hours": daily_summary.missing_hours,
            "aggregation_timestamp": daily_summary.aggregation_completed_at.isoformat(),
        }

        # Create AnonymizedMetricsPayload
        payload = AnonymizedMetricsPayload.objects.create(
            summary_date=summary_date,
            anonymized_data=anonymized_data,
            status="pending",
            daily_summary=daily_summary,
            anonymization_task_execution_id=kwargs.get("execution_id"),
            segment_event_name=kwargs.get("event_name", "daily_metrics_rollup"),
            segment_user_id=kwargs.get("user_id", str(uuid.uuid4())),
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
    2. Sends to Segment using existing _send_to_segment helper
    3. Updates payload status based on result
    4. Handles retries for failed sends

    Args:
        **kwargs: Task data containing:
            - payload_id (int): Specific payload ID to send (optional)
            - segment_write_key (str): Segment write key (required)
            - max_payloads (int): Maximum number of payloads to send in one run (default: 5)

    Returns:
        dict: Task result with send statistics
    """
    from django.utils import timezone

    from apps.tasks.models import AnonymizedMetricsPayload

    segment_write_key = kwargs.get("segment_write_key", "NA")
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

        results = {
            "sent": 0,
            "failed": 0,
            "skipped": 0,
        }

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
                # Send to Segment
                if SEGMENT_AVAILABLE:
                    segment_status = _send_to_segment(
                        segment_write_key=segment_write_key,
                        user_id=payload.segment_user_id,
                        event_name=payload.segment_event_name,
                        segment_data=payload.anonymized_data,
                    )
                else:
                    segment_status = "segment_not_available"

                if segment_status == "success":
                    payload.status = "sent"
                    payload.sent_at = timezone.now()
                    payload.error_message = ""
                    results["sent"] += 1

                    # Update daily summary status
                    payload.daily_summary.status = "sent"
                    payload.daily_summary.save()
                else:
                    # Failed, schedule retry
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
