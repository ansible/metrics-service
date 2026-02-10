"""
Collect, anonymize, and send metrics data to Segment.com.

This task provides a complete end-to-end workflow for metrics collection,
anonymization, and transmission to Segment.com.
"""

import logging
from typing import Any

from ..utils import (
    create_task_result,
    generate_salt,
    get_db_connection,
    log_task_execution,
    send_to_segment,
    task,
    task_execution_wrapper,
)
from .helpers import (
    DEFAULT_DB_NAME,
    METRICS_UTILITY_AVAILABLE,
    MSG_METRICS_UTILITY_NOT_AVAILABLE,
    _collect_all_metrics,
    _prepare_segment_data,
)

logger = logging.getLogger(__name__)


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
            - send_to_segment_option (bool): Whether to send data to Segment (default: True)

    Returns:
        dict: Task result with collection, anonymization, and sending status
    """
    if not METRICS_UTILITY_AVAILABLE:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    log_task_execution("full_process", "processing", "Starting full metrics collection and Segment.com upload")

    try:
        db_name = kwargs.get("database", DEFAULT_DB_NAME)
        db_connection = get_db_connection(db_name)
        since = kwargs.get("since")
        until = kwargs.get("until")
        salt = kwargs.get("salt", generate_salt())
        user_id = kwargs.get("user_id", generate_salt())
        event_name = kwargs.get("event_name", "metrics_collected")
        collectors_list = kwargs.get("collectors", ["anonymized_rollups", "config", "job_host_summary"])
        send_to_segment_option = kwargs.get("send_to_segment_option", True)

        # Step 1: Collect metrics
        log_task_execution("full_process", "processing", "Collecting metrics data")
        all_results = _collect_all_metrics(collectors_list, db_connection, since, until, salt)

        # Step 2: Prepare anonymized data
        log_task_execution("full_process", "processing", "Preparing anonymized data for Segment.com")
        segment_data = _prepare_segment_data(collectors_list, all_results, db_name, since, until, salt)

        # Step 3: Send to Segment.com if enabled
        segment_status = "skipped"
        if send_to_segment_option:
            segment_status = send_to_segment(user_id, event_name, segment_data)

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
                    "send_to_segment": send_to_segment_option,
                    "event_name": event_name,
                    "user_id": user_id,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in full_process: {str(e)}")
        return create_task_result("error", error=f"Full process failed: {str(e)}")
