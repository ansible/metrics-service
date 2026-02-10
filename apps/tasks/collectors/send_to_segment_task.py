"""
Dedicated task to send anonymized data to Segment.com.

This task takes already-anonymized data and transmits it to Segment.com
for analytics and tracking purposes.
"""

import logging
from typing import Any

from ..utils import (
    create_task_result,
    log_task_execution,
    send_to_segment,
    task,
    task_execution_wrapper,
)

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("send_to_segment_task")
def send_to_segment_task(**kwargs) -> dict[str, Any]:
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
    log_task_execution("send_to_segment_task", "processing", "Sending anonymized data to Segment.com")

    try:
        anonymized_data = kwargs.get("data")
        if not anonymized_data:
            return create_task_result("error", error="No data provided for transmission")

        user_id = kwargs.get("user_id", "anonymous-user")
        event_name = kwargs.get("event_name", "metrics_sent")

        segment_status = send_to_segment(user_id, event_name, anonymized_data)

        return create_task_result(
            "success",
            {
                "task_type": "send_to_segment_task",
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
        logger.error(f"Error in send_to_segment_task: {str(e)}")
        return create_task_result("error", error=f"Segment transmission failed: {str(e)}")
