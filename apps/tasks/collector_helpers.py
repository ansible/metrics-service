"""
Collector helper functions for metrics collection tasks.

This module contains all the helper functions extracted from tasks_collector.py
for running individual metric collectors. This reduces duplication and makes
the collector infrastructure more maintainable.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from .datetime_utils import get_date_range_defaults, parse_iso_datetime

logger = logging.getLogger(__name__)

# Import metrics-utility collectors
try:
    from metrics_utility.library.anonymize import anonymized_rollups_processor
    from metrics_utility.library.collectors.controller import (
        config,
        job_host_summary,
        main_host,
        main_jobevent,
    )

    metrics_utility_available = True
except ImportError as e:
    logger.warning(f"metrics-utility not available in collector_helpers: {e}")
    metrics_utility_available = False

    # Provide fallback attributes
    anonymized_rollups_processor = None
    config = None
    job_host_summary = None
    main_host = None
    main_jobevent = None


def run_anonymized_rollups_collector(
    db_connection, salt: str, since_dt: datetime | None, until_dt: datetime | None
) -> dict[str, Any]:
    """
    Run the anonymized_rollups collector.

    Args:
        db_connection: Database connection object
        salt: Salt for anonymization
        since_dt: Start date for collection
        until_dt: End date for collection

    Returns:
        Collected anonymized metrics data

    Raises:
        ImportError: If metrics-utility is not available
    """
    if not metrics_utility_available:
        raise ImportError("metrics-utility is not available")

    return anonymized_rollups_processor(
        db=db_connection,
        salt=salt,
        since=since_dt,
        until=until_dt,
        ship_path=None,  # Don't save locally, will send to Segment
        save_rollups=False,
    )


def run_config_collector(db_connection) -> dict[str, Any]:
    """
    Run the config collector.

    Args:
        db_connection: Database connection object

    Returns:
        Collected configuration data

    Raises:
        ImportError: If metrics-utility is not available
    """
    if not metrics_utility_available:
        raise ImportError("metrics-utility is not available")

    collector_instance = config(db=db_connection)
    return collector_instance.gather()


def run_job_host_summary_collector(
    db_connection, since_dt: datetime | None, until_dt: datetime | None
) -> dict[str, Any]:
    """
    Run the job_host_summary collector.

    Args:
        db_connection: Database connection object
        since_dt: Start date for collection (optional)
        until_dt: End date for collection (optional)

    Returns:
        Collected job host summary data

    Raises:
        ImportError: If metrics-utility is not available
    """
    if not metrics_utility_available:
        raise ImportError("metrics-utility is not available")

    # Create collector with date parameters if provided
    if since_dt is not None and until_dt is not None:
        collector_instance = job_host_summary(db=db_connection, since=since_dt, until=until_dt)
    else:
        collector_instance = job_host_summary(db=db_connection)

    return collector_instance.gather()


def run_main_host_collector(db_connection) -> dict[str, Any]:
    """
    Run the main_host collector.

    Note: main_host collector doesn't accept date parameters,
    only database connection.

    Args:
        db_connection: Database connection object

    Returns:
        Collected main host data

    Raises:
        ImportError: If metrics-utility is not available
    """
    if not metrics_utility_available:
        raise ImportError("metrics-utility is not available")

    collector_instance = main_host(db=db_connection)
    return collector_instance.gather()


def run_main_jobevent_collector(
    db_connection, since_dt: datetime | None, until_dt: datetime | None = None
) -> dict[str, Any]:
    """
    Run the main_jobevent collector.

    Note: main_jobevent requires since and until dates. If not provided,
    defaults to last 30 days.

    Args:
        db_connection: Database connection object
        since_dt: Start date (defaults to 30 days ago if None)
        until_dt: End date (defaults to now if None)

    Returns:
        Collected job event data

    Raises:
        ImportError: If metrics-utility is not available
    """
    if not metrics_utility_available:
        raise ImportError("metrics-utility is not available")

    # Ensure we have date parameters (main_jobevent requires them)
    if since_dt is None:
        since_dt = datetime.now(UTC) - timedelta(days=30)

    if until_dt is None:
        until_dt = datetime.now(UTC)

    collector_instance = main_jobevent(db=db_connection, since=since_dt, until=until_dt)
    return collector_instance.gather()


def get_collector_function(collector_name: str):
    """
    Get the collector function for a given collector name.

    Args:
        collector_name: Name of the collector

    Returns:
        Collector function reference

    Raises:
        ValueError: If collector name is unknown

    Examples:
        >>> func = get_collector_function("config")
        >>> func
        <function run_config_collector at 0x...>
    """
    collector_map = {
        "anonymized_rollups": run_anonymized_rollups_collector,
        "config": run_config_collector,
        "job_host_summary": run_job_host_summary_collector,
        "main_host": run_main_host_collector,
        "main_jobevent": run_main_jobevent_collector,
    }

    if collector_name not in collector_map:
        raise ValueError(f"Unknown collector: {collector_name}")

    return collector_map[collector_name]


def run_single_collector(
    collector_name: str, db_connection, since: str | datetime | None, until: str | datetime | None, salt: str = ""
) -> dict[str, Any]:
    """
    Run a single collector with the specified parameters.

    This function handles:
    - Parsing string dates to datetime objects
    - Applying default date ranges for collectors that need them
    - Dispatching to the appropriate collector function
    - Error handling

    Args:
        collector_name: Name of the collector to run
        db_connection: Database connection object
        since: Start date (string or datetime, or None)
        until: End date (string or datetime, or None)
        salt: Salt for anonymization (required for anonymized_rollups)

    Returns:
        Collected data from the specified collector

    Raises:
        ValueError: If collector name is unknown
        ImportError: If metrics-utility is not available

    Examples:
        >>> from django.db import connections
        >>> db_conn = connections['awx']
        >>> data = run_single_collector("config", db_conn, None, None)
        >>> "config" in data
        True
    """
    # Convert string dates to datetime objects if needed
    since_dt = parse_iso_datetime(since) if isinstance(since, str) else since

    until_dt = parse_iso_datetime(until) if isinstance(until, str) else until

    # Apply defaults for date-sensitive collectors
    since_dt, until_dt = get_date_range_defaults(collector_name, since_dt, until_dt)

    # Build collector function arguments
    collector_kwargs = {
        "anonymized_rollups": {
            "db_connection": db_connection,
            "salt": salt,
            "since_dt": since_dt,
            "until_dt": until_dt,
        },
        "config": {"db_connection": db_connection},
        "job_host_summary": {"db_connection": db_connection, "since_dt": since_dt, "until_dt": until_dt},
        "main_host": {"db_connection": db_connection},
        "main_jobevent": {"db_connection": db_connection, "since_dt": since_dt, "until_dt": until_dt},
    }

    # Get collector function
    collector_func = get_collector_function(collector_name)

    # Get arguments for this collector
    kwargs = collector_kwargs.get(collector_name, {})

    # Run collector with appropriate arguments
    return collector_func(**kwargs)


def collect_from_multiple_collectors(
    collector_names: list[str],
    db_connection,
    since: str | datetime | None = None,
    until: str | datetime | None = None,
    salt: str = "",
) -> dict[str, Any]:
    """
    Collect data from multiple collectors.

    This function runs each collector in the list and aggregates results.
    Individual collector errors are logged but don't stop the overall collection.

    Args:
        collector_names: List of collector names to run
        db_connection: Database connection object
        since: Start date for collection (optional)
        until: End date for collection (optional)
        salt: Salt for anonymization (used by anonymized_rollups)

    Returns:
        Dictionary mapping collector names to their collected data
        {
            "collector1": {data...},
            "collector2": {data...},
            "collector3": {"error": "error message"}  # if collector failed
        }

    Examples:
        >>> from django.db import connections
        >>> db_conn = connections['awx']
        >>> collectors = ["config", "main_host"]
        >>> results = collect_from_multiple_collectors(collectors, db_conn)
        >>> len(results)
        2
        >>> "config" in results
        True
    """
    from .logging_utils import TaskLogger

    logger_instance = TaskLogger("collect_multiple_collectors")
    all_results = {}

    for collector_name in collector_names:
        try:
            logger_instance.log_progress(f"Running collector: {collector_name}")

            collector_data = run_single_collector(collector_name, db_connection, since, until, salt)
            all_results[collector_name] = collector_data

            logger_instance.log_progress(f"Successfully collected data from {collector_name}")

        except ValueError:
            # Unknown collector
            logger_instance.log_warning(f"Unknown collector: {collector_name}")
            all_results[collector_name] = {"error": f"Unknown collector: {collector_name}"}

        except ImportError:
            # metrics-utility not available
            logger_instance.log_warning(f"Cannot run {collector_name}: metrics-utility not available")
            all_results[collector_name] = {"error": "metrics-utility not available"}

        except Exception as e:
            # Other errors
            logger_instance.log_error(f"Error running collector {collector_name}: {str(e)}")
            all_results[collector_name] = {"error": str(e)}

    return all_results


def get_available_collectors() -> list[str]:
    """
    Get list of available collector names.

    Returns:
        List of collector names that can be used

    Examples:
        >>> collectors = get_available_collectors()
        >>> "config" in collectors
        True
        >>> "job_host_summary" in collectors
        True
    """
    return [
        "anonymized_rollups",
        "config",
        "job_host_summary",
        "main_host",
        "main_jobevent",
    ]


def is_collector_available(collector_name: str) -> bool:
    """
    Check if a collector is available.

    Args:
        collector_name: Name of the collector to check

    Returns:
        True if collector exists and metrics-utility is available

    Examples:
        >>> is_collector_available("config")
        True  # if metrics-utility is installed

        >>> is_collector_available("nonexistent")
        False
    """
    if not metrics_utility_available:
        return False

    return collector_name in get_available_collectors()
