"""
Utility functions to reduce code duplication across the application.
"""

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


def get_related_object_safely(instance: Any, field_name: str, default: Any = None) -> Any:
    """
    Safely get a related object from an instance.

    This function provides a safe way to access related objects that might
    not exist, reducing try/except duplication across the codebase.

    Args:
        instance: The model instance
        field_name (str): Name of the related field
        default: Default value to return if the relation doesn't exist

    Returns:
        The related object or the default value
    """
    try:
        return getattr(instance, field_name)
    except AttributeError:
        return default
    except instance.DoesNotExist:
        return default


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
        return queryset_or_manager.count()
    except Exception as e:
        logger.warning(f"Error getting count: {e}")
        return 0


def build_error_response(message: str, details: dict[str, Any] = None, status_code: int = 400) -> dict[str, Any]:
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
