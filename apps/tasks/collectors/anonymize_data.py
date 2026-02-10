"""
Dedicated task to anonymize collected metrics data.

This task applies anonymization to raw metrics data using the
prepare_segment_data helper function.
"""

import logging
from typing import Any

from ..utils import (
    create_task_result,
    generate_salt,
    log_task_execution,
    task,
    task_execution_wrapper,
)
from .helpers import (
    METRICS_UTILITY_AVAILABLE,
    MSG_METRICS_UTILITY_NOT_AVAILABLE,
    _prepare_segment_data,
)

logger = logging.getLogger(__name__)


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

        salt = kwargs.get("salt", generate_salt())
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
