"""
Metrics collection and anonymized data collection tasks for metrics_service.

This module provides tasks for collecting metrics and anonymized data using
the metrics-utility library. These tasks integrate with AWX/Automation Controller
for data collection and analysis.
"""

import logging
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

# Import metrics-utility collectors
try:
    from metrics_utility.library.anonymize.anonymized_rollups_processor import (
        anonymized_rollups_processor,
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
        from django.db import connections

        db_name = kwargs.get("database", "awx")
        since = kwargs.get("since")
        until = kwargs.get("until")
        salt = kwargs.get("salt", "default-salt")
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
        return create_task_result("error", error=f"Collection failed: {str(e)}")


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
        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        since = kwargs.get("since")
        until = kwargs.get("until")

        db_connection = connections[db_name]
        # Create collector instance
        collector = job_host_summary(db=db_connection, since=since, until=until)

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
        from django.db import connections

        # Get parameters from kwargs
        db_name = kwargs.get("database", "awx")
        since = kwargs.get("since")

        db_connection = connections[db_name]
        # Create collector instance
        collector = main_jobevent(db=db_connection, since=since)

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

        # Run each requested collector
        for collector_name in collectors_list:
            try:
                if collector_name == "anonymized_rollups":
                    collector_data = anonymized_rollups_processor(
                        db=db_connection,
                        salt=salt,
                        since=since,
                        until=until,
                        ship_path=ship_path,
                        save_rollups=save_rollups,
                    )
                elif collector_name == "config":
                    collector_instance = config(db=db_connection)
                    collector_data = collector_instance.gather()
                elif collector_name == "job_host_summary":
                    collector_instance = job_host_summary(db=db_connection, since=since, until=until)
                    collector_data = collector_instance.gather()
                elif collector_name == "main_host":
                    collector_instance = main_host(db=db_connection, since=since, until=until)
                    collector_data = collector_instance.gather()
                elif collector_name == "main_jobevent":
                    collector_instance = main_jobevent(db=db_connection, since=since)
                    collector_data = collector_instance.gather()
                else:
                    logger.warning(f"Unknown collector: {collector_name}")
                    continue

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
