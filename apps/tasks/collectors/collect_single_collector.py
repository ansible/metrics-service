"""
Unified task to collect data from a single collector with configurable output format.

This task consolidates all individual collector tasks into one parameterized function.
It can run any available collector and return data in either JSON or CSV format.
"""

import logging
from typing import Any

from ..utils import (
    create_task_result,
    csv_to_json,
    generate_salt,
    get_db_connection,
    log_task_execution,
    parse_datetime_string,
    task,
    task_execution_wrapper,
)
from .helpers import (
    DEFAULT_DB_NAME,
    METRICS_UTILITY_AVAILABLE,
    MSG_METRICS_UTILITY_NOT_AVAILABLE,
    _get_date_defaults,
    _run_anonymized_rollups,
    _run_config_collector,
    _run_job_host_summary_collector,
    _run_main_host_collector,
    _run_main_jobevent_collector,
)

logger = logging.getLogger(__name__)


def _run_single_collector(collector_name: str, db_connection, since: str, until: str, salt: str) -> dict[str, Any]:
    """Run a single collector and return its data."""
    since_dt = parse_datetime_string(since)
    until_dt = parse_datetime_string(until)
    since_dt, until_dt = _get_date_defaults(collector_name, since_dt, until_dt)

    # Call the appropriate collector function directly
    if collector_name == "anonymized_rollups":
        return _run_anonymized_rollups(db_connection, salt, since_dt, until_dt)
    elif collector_name == "config":
        return _run_config_collector(db_connection)
    elif collector_name == "job_host_summary":
        return _run_job_host_summary_collector(db_connection, since_dt, until_dt)
    elif collector_name == "main_host":
        return _run_main_host_collector(db_connection)
    elif collector_name == "main_jobevent":
        return _run_main_jobevent_collector(db_connection, since_dt, until_dt)
    else:
        raise ValueError(f"Unknown collector: {collector_name}")


def _run_single_collector_with_format(
    collector_name: str,
    db_connection,
    since: str,
    until: str,
    salt: str,
    output_format: str = "json",
) -> dict[str, Any]:
    """
    Run a single collector and return data in specified format.

    Args:
        collector_name: Name of the collector to run
        db_connection: Database connection
        since: Start date string (ISO format)
        until: End date string (ISO format)
        salt: Salt for anonymization
        output_format: 'json' (default) or 'csv'

    Returns:
        dict: Collected data in requested format
            JSON format: Converted JSON structure from CSV files
            CSV format: {'csv_files': [...paths...], 'file_count': N}
    """
    since_dt = parse_datetime_string(since)
    until_dt = parse_datetime_string(until)
    since_dt, until_dt = _get_date_defaults(collector_name, since_dt, until_dt)

    # Call the appropriate collector function directly
    # Collectors return CSV file paths
    if collector_name == "anonymized_rollups":
        csv_file_paths = _run_anonymized_rollups(db_connection, salt, since_dt, until_dt)
    elif collector_name == "config":
        csv_file_paths = _run_config_collector(db_connection)
    elif collector_name == "job_host_summary":
        csv_file_paths = _run_job_host_summary_collector(db_connection, since_dt, until_dt)
    elif collector_name == "main_host":
        csv_file_paths = _run_main_host_collector(db_connection)
    elif collector_name == "main_jobevent":
        csv_file_paths = _run_main_jobevent_collector(db_connection, since_dt, until_dt)
    else:
        raise ValueError(f"Unknown collector: {collector_name}")

    # Return based on output format
    if output_format == "csv":
        # Return raw CSV file paths without conversion
        csv_list = csv_file_paths if isinstance(csv_file_paths, list) else [csv_file_paths]
        return {"csv_files": csv_list, "file_count": len(csv_list)}
    else:  # 'json' (default)
        # Convert CSV to JSON
        return csv_to_json(csv_file_paths)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_single_collector")
def collect_single_collector(**kwargs) -> dict[str, Any]:
    """
    Unified task to collect data from a single collector with configurable output format.

    This task consolidates all individual collector tasks into one parameterized function.
    It can run any available collector and return data in either JSON or CSV format.

    Args:
        **kwargs: Task data containing collection parameters:
            - collector_type (str): Collector to run (required)
                Options: 'anonymized_rollups', 'config', 'job_host_summary', 'main_host', 'main_jobevent'
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (ISO format, optional)
            - until (str): End date for collection (ISO format, optional)
            - salt (str): Salt for anonymization (optional, auto-generated UUID4)
            - output_format (str): Output format - 'json' or 'csv' (default: 'json')
                'json' - Convert CSV to JSON (standard behavior)
                'csv' - Return CSV file paths without conversion

    Returns:
        dict: Task result with collected data
            When output_format='json': Returns {'status': 'success', 'collected_data': {...json...}}
            When output_format='csv': Returns {'status': 'success', 'csv_files': [...paths...], 'file_count': N}
    """
    # Validate required parameters first
    collector_type = kwargs.get("collector_type")
    if not collector_type:
        return create_task_result("error", error="collector_type parameter is required")

    # Check if metrics-utility is available
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_single_collector", "processing", f"Collecting metrics using {collector_type} collector")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        since = kwargs.get("since")
        until = kwargs.get("until")
        salt = kwargs.get("salt", generate_salt())
        output_format = kwargs.get("output_format", "json")

        # Validate output_format
        if output_format not in ["json", "csv"]:
            return create_task_result("error", error=f"Invalid output_format: {output_format}. Must be 'json' or 'csv'")

        # Get database connection
        db_connection = get_db_connection(db_name)

        # Run collector with specified output format
        collected_data = _run_single_collector_with_format(
            collector_type, db_connection, since, until, salt, output_format
        )

        # Build result based on output format
        if output_format == "csv":
            result_data = {
                "task_type": "collect_single_collector",
                "collector_type": collector_type,
                "csv_files": collected_data.get("csv_files", []),
                "file_count": collected_data.get("file_count", 0),
                "output_format": "csv",
                "parameters_used": {
                    "database": db_name,
                    "since": since,
                    "until": until,
                    "salt": salt,
                    "output_format": output_format,
                },
            }
        else:  # 'json'
            result_data = {
                "task_type": "collect_single_collector",
                "collector_type": collector_type,
                "collected_data": collected_data,
                "output_format": "json",
                "parameters_used": {
                    "database": db_name,
                    "since": since,
                    "until": until,
                    "salt": salt,
                    "output_format": output_format,
                },
            }

        return create_task_result("success", result_data)

    except ValueError as e:
        # Handle unknown collector type
        logger.error(f"Invalid collector_type in collect_single_collector: {str(e)}")
        return create_task_result("error", error=str(e))
    except Exception as e:
        logger.error(f"Error in collect_single_collector: {str(e)}")
        return create_task_result("error", error=f"Collection failed: {str(e)}")
