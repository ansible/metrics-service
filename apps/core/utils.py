"""
Utility functions to reduce code duplication across the application.
"""

import json
import logging
import uuid
from typing import Any

from django.conf import settings
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


def get_system_uuid() -> str:
    """
    Get system UUID from settings or generate a default one.

    Returns:
        str: System UUID
    """
    try:
        return getattr(settings, "SYSTEM_UUID", str(uuid.uuid4()))
    except Exception:
        return str(uuid.uuid4())


def is_system_auditor_user(user: Any) -> bool:
    """
    Check if user is a system auditor.

    Args:
        user: User instance to check

    Returns:
        bool: True if user is system auditor
    """
    try:
        if hasattr(user, "is_system_auditor_user") and callable(user.is_system_auditor_user):
            return user.is_system_auditor_user()
        return False
    except Exception:
        return False


def format_task_data(data: Any) -> str:
    """
    Format task data for display.

    Args:
        data: Task data to format

    Returns:
        str: Formatted task data
    """
    try:
        if isinstance(data, str):
            return data
        return json.dumps(data, indent=2)
    except Exception:
        return str(data)
