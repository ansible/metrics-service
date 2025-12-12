"""
API utility functions for the metrics service.

This module provides reusable utility functions for API operations.
"""

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


def get_count_safely(queryset_or_manager: Any) -> int:
    """
    Safely get count from a queryset or manager.

    This function provides a safe way to get counts that handles
    potential errors, reducing duplication in count operations.

    Args:
        queryset_or_manager: QuerySet or Manager to count

    Returns:
        int: Count of objects, 0 if error
    """
    try:
        count_result = queryset_or_manager.count()
        return int(count_result)
    except Exception as e:
        logger.warning(f"Error getting count: {e}")
        return 0


def build_error_response(message: str, details: dict[str, Any] | None = None, status_code: int = 400) -> dict[str, Any]:
    """
    Build a standardized error response dictionary.

    This function provides a consistent format for error responses,
    reducing duplication across view error handling.

    Args:
        message (str): Main error message
        details (dict): Optional additional error details
        status_code (int): HTTP status code for the error

    Returns:
        dict: Standardized error response
    """
    error_response = {
        "error": message,
        "status_code": status_code,
        "timestamp": timezone.now().isoformat(),
    }

    if details:
        error_response["details"] = details

    return error_response
