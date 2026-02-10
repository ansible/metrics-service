"""
Unified task to collect metrics from multiple collectors.

This task merges functionality from the former collect_all_metrics and collect_metrics tasks,
providing a single entry point for multi-collector metrics collection.
"""

import logging
from typing import Any

from ..utils import (
    create_task_result,
    get_db_connection,
    log_task_execution,
    task,
    task_execution_wrapper,
)
from .helpers import (
    DEFAULT_COLLECTORS,
    DEFAULT_DB_NAME,
    METRICS_UTILITY_AVAILABLE,
    MSG_METRICS_UTILITY_NOT_AVAILABLE,
    _collect_all_metrics,
)

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("collect_metrics")
def collect_metrics(**kwargs) -> dict[str, Any]:
    """
    Unified task to collect metrics from multiple collectors.

    This task merges functionality from the former collect_all_metrics and collect_metrics tasks,
    providing a single entry point for multi-collector metrics collection.

    Args:
        **kwargs: Task data containing collection parameters:
            - database (str): Database name from Django settings (default: 'awx')
            - since (str): Start date for collection (ISO format, optional)
            - until (str): End date for collection (ISO format, optional)
            - salt (str): Salt for anonymization (default: 'default-salt')
            - collectors (list): List of specific collectors to run
                (default: DEFAULT_COLLECTORS = all available collectors)
                Options: ['anonymized_rollups', 'config', 'job_host_summary', 'main_host', 'main_jobevent']

    Returns:
        dict: Task result with collected metrics data from all collectors
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("collect_metrics", "processing", "Collecting metrics from multiple collectors")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        db_connection = get_db_connection(db_name)
        since = kwargs.get("since")
        until = kwargs.get("until")
        salt = kwargs.get("salt", "default-salt")  # Added from collect_all_metrics
        collectors_list = kwargs.get("collectors", DEFAULT_COLLECTORS)  # From collect_metrics

        # Use shared helper function to collect from all specified collectors
        all_results = _collect_all_metrics(collectors_list, db_connection, since, until, salt)

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
                    "salt": salt,  # Now included in parameters
                    "collectors": collectors_list,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in collect_metrics: {str(e)}")
        return create_task_result("error", error=f"Metrics collection failed: {str(e)}")
