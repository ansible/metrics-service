"""
Utility functions for the core app.
"""

import logging
from typing import Any

from django.db import models
from django.utils import timezone


def get_count_safely(queryset_or_manager: models.QuerySet | models.Manager) -> int:
    """
    Safely get count from a queryset or manager.

    Args:
        queryset_or_manager: Django queryset or manager to count

    Returns:
        int: Count of objects, 0 if error occurs
    """
    try:
        return queryset_or_manager.count()
    except Exception:
        return 0


def build_error_response(message: str, details: Any | None = None, status_code: int = 400) -> dict:
    """
    Build a standardized error response dictionary.

    Args:
        message: Error message
        details: Optional error details
        status_code: HTTP status code

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


def log_task_execution(task_name: str, operation: str, details: str = "", level: str = "info") -> None:
    """
    Log task execution events with standardized format.

    Args:
        task_name: Name of the task or operation
        operation: Type of operation (start, complete, error, etc.)
        details: Additional details to log
        level: Log level (info, warning, error, debug)
    """
    logger = logging.getLogger(__name__)

    log_message = f"Task: {task_name} | Operation: {operation}"
    if details:
        log_message += f" | Details: {details}"

    log_method = getattr(logger, level.lower(), logger.info)
    log_method(log_message)


def validate_cron_expression(cron_expression: str) -> bool:
    """
    Validate a cron expression format.

    Args:
        cron_expression: Cron expression to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        from croniter import croniter

        return croniter.is_valid(cron_expression)
    except ImportError:
        # croniter not available, basic validation
        parts = cron_expression.split()
        return len(parts) == 5
    except Exception:
        return False


def get_next_cron_time(cron_expression: str, base_time: timezone.datetime | None = None) -> timezone.datetime | None:
    """
    Get the next execution time for a cron expression.

    Args:
        cron_expression: Cron expression
        base_time: Base time to calculate from (defaults to now)

    Returns:
        datetime or None: Next execution time, None if invalid
    """
    try:
        from croniter import croniter

        if base_time is None:
            base_time = timezone.now()

        cron = croniter(cron_expression, base_time)
        return cron.get_next(timezone.datetime)
    except ImportError:
        # croniter not available
        return None
    except Exception:
        return None
