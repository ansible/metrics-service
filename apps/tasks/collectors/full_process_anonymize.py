"""
Collect anonymized metrics and send directly to Segment.com.

This task uses the anonymized_rollups_processor to collect already-anonymized
data and optionally send it to Segment.com.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from ..utils import (
    create_task_result,
    generate_salt,
    get_db_connection,
    log_task_execution,
    parse_datetime_string,
    send_to_segment,
    task,
    task_execution_wrapper,
)
from .helpers import (
    DEFAULT_DB_NAME,
    METRICS_UTILITY_AVAILABLE,
    MSG_METRICS_UTILITY_NOT_AVAILABLE,
    _get_date_defaults,
    anonymized_rollups_processor,
)

logger = logging.getLogger(__name__)


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
        db_connection = get_db_connection(db_name)
        since = kwargs.get("since")
        until = kwargs.get("until")
        salt = kwargs.get("salt", generate_salt())
        user_id = kwargs.get("user_id", "anonymous-user")
        event_name = kwargs.get("event_name", "anonymized_metrics_collected")
        should_send_to_segment = kwargs.get("send_to_segment", True)

        # Parse and apply defaults for dates
        since_dt = parse_datetime_string(since)
        until_dt = parse_datetime_string(until)
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
        if should_send_to_segment:
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
            segment_status = send_to_segment(user_id, event_name, segment_data)

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
                    "send_to_segment": should_send_to_segment,
                    "event_name": event_name,
                    "user_id": user_id,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error in full_process_anonymize: {str(e)}")
        return create_task_result("error", error=f"Anonymized process failed: {str(e)}")
