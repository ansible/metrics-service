"""
Simple hello world task for testing.

This task prints "Hello World" and completes successfully.
Used for testing the dispatcherd integration.
"""

import logging
from typing import Any

from ..utils import create_task_result

logger = logging.getLogger(__name__)


def hello_world(**kwargs) -> dict[str, Any]:
    """
    Simple hello world task for testing.

    This task prints "Hello World" and completes successfully.
    Used for testing the dispatcherd integration.

    Args:
        **kwargs: Any keyword arguments (ignored)

    Returns:
        dict: Task result dictionary with success status
    """
    # Simple task that just prints hello world
    message = "Hello World from dispatcherd!"
    logger.info(f"Task executing: {message}")

    return create_task_result(
        "success",
        {
            "message": message,
            "task_type": "hello_world",
            "completed": True,
        },
    )
