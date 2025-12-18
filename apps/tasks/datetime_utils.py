"""
DateTime utilities for task management and metrics collection.

This module provides centralized datetime parsing and validation functions,
eliminating duplicated logic in tasks_collector.py and other task modules.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

# Constant for UTC offset suffix used in ISO format conversions
UTC_OFFSET_SUFFIX = "+00:00"

# Collectors that require date ranges
DATE_RANGE_COLLECTORS = ["job_host_summary", "main_jobevent", "anonymized_rollups"]

# Default date range (30 days)
DEFAULT_DATE_RANGE_DAYS = 30


def parse_iso_datetime(date_str: str | None) -> datetime | None:
    """
    Parse an ISO 8601 datetime string.

    This function handles timezone-aware ISO format strings, including
    those with 'Z' suffix (UTC), and returns None for invalid input.

    Args:
        date_str: ISO 8601 datetime string (e.g., "2024-01-01T00:00:00Z")

    Returns:
        Parsed datetime object, or None if invalid/empty

    Examples:
        >>> parse_iso_datetime("2024-01-01T00:00:00Z")
        datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=...)

        >>> parse_iso_datetime(None)
        None

        >>> parse_iso_datetime("invalid")
        None
    """
    if not date_str:
        return None

    try:
        # Replace 'Z' with explicit UTC offset for fromisoformat compatibility
        normalized_str = date_str.replace("Z", UTC_OFFSET_SUFFIX)
        return datetime.fromisoformat(normalized_str)
    except (ValueError, AttributeError):
        return None


def get_date_range_defaults(
    collector_name: str, since: datetime | None = None, until: datetime | None = None
) -> tuple[datetime, datetime]:
    """
    Provide sensible default date ranges for collectors that require them.

    For collectors that operate on date ranges (job_host_summary, main_jobevent,
    anonymized_rollups), this function provides default values if none are specified:
    - since: 30 days ago (if collector requires it and none provided)
    - until: now (if collector requires it and none provided)

    Args:
        collector_name: Name of the collector function
        since: Optional start date (defaults to 30 days ago for date-range collectors)
        until: Optional end date (defaults to now for date-range collectors)

    Returns:
        Tuple of (since, until) datetime objects with defaults applied

    Examples:
        >>> get_date_range_defaults("job_host_summary")
        (datetime.datetime(...), datetime.datetime(...))  # 30 days ago, now

        >>> get_date_range_defaults("config")
        (None, None)  # No defaults for collectors that don't need dates

        >>> custom_since = datetime(2024, 1, 1, tzinfo=UTC)
        >>> get_date_range_defaults("job_host_summary", since=custom_since)
        (datetime.datetime(2024, 1, 1, ...), datetime.datetime(...))  # Custom since, default until
    """
    # Apply defaults only for collectors that require date ranges
    if collector_name in DATE_RANGE_COLLECTORS:
        if since is None:
            since = datetime.now(UTC) - timedelta(days=DEFAULT_DATE_RANGE_DAYS)
        if until is None:
            until = datetime.now(UTC)

    return since, until


def validate_date_range(since: datetime | None, until: datetime | None) -> str | None:
    """
    Validate that a date range is logically correct.

    Checks that:
    - If both dates are provided, 'since' is before 'until'
    - Dates are not in the far future (more than 1 day ahead)

    Args:
        since: Start date of range
        until: End date of range

    Returns:
        Error message string if validation fails, None if valid

    Examples:
        >>> validate_date_range(
        ...     datetime(2024, 1, 1, tzinfo=UTC),
        ...     datetime(2024, 1, 31, tzinfo=UTC)
        ... )
        None

        >>> validate_date_range(
        ...     datetime(2024, 1, 31, tzinfo=UTC),
        ...     datetime(2024, 1, 1, tzinfo=UTC)
        ... )
        "'since' date must be before 'until' date"

        >>> future = datetime.now(UTC) + timedelta(days=10)
        >>> validate_date_range(future, None)
        "'since' date cannot be more than 1 day in the future"
    """
    # If both dates provided, ensure since is before until
    if since is not None and until is not None and since >= until:
        return "'since' date must be before 'until' date"

    # Check for dates in the far future (likely errors)
    now = datetime.now(UTC)
    future_limit = now + timedelta(days=1)

    if since is not None and since > future_limit:
        return "'since' date cannot be more than 1 day in the future"

    if until is not None and until > future_limit:
        return "'until' date cannot be more than 1 day in the future"

    return None


def format_datetime_for_display(dt: datetime | None) -> str:
    """
    Format a datetime object for display in logs or UI.

    Args:
        dt: Datetime object to format

    Returns:
        Formatted datetime string, or "None" if dt is None

    Examples:
        >>> dt = datetime(2024, 1, 15, 14, 30, tzinfo=UTC)
        >>> format_datetime_for_display(dt)
        '2024-01-15 14:30:00 UTC'

        >>> format_datetime_for_display(None)
        'None'
    """
    if dt is None:
        return "None"

    # Format as human-readable string with timezone
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z") if dt.tzinfo else dt.strftime("%Y-%m-%d %H:%M:%S")


def ensure_timezone_aware(dt: datetime) -> datetime:
    """
    Ensure a datetime object is timezone-aware (UTC if naive).

    Args:
        dt: Datetime object (may be naive or aware)

    Returns:
        Timezone-aware datetime (original if already aware, UTC-localized if naive)

    Examples:
        >>> naive = datetime(2024, 1, 1, 12, 0)
        >>> ensure_timezone_aware(naive)
        datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)

        >>> aware = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        >>> ensure_timezone_aware(aware) == aware
        True
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def parse_date_range_params(kwargs: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    """
    Extract and parse 'since' and 'until' parameters from task kwargs.

    This is a convenience function for task functions that accept date range
    parameters as strings in their kwargs.

    Args:
        kwargs: Task parameters dictionary containing optional 'since' and 'until' keys

    Returns:
        Tuple of (since, until) datetime objects (may be None)

    Examples:
        >>> params = {"since": "2024-01-01T00:00:00Z", "until": "2024-01-31T23:59:59Z"}
        >>> parse_date_range_params(params)
        (datetime.datetime(...), datetime.datetime(...))

        >>> parse_date_range_params({})
        (None, None)
    """
    since_str = kwargs.get("since")
    until_str = kwargs.get("until")

    since = parse_iso_datetime(since_str)
    until = parse_iso_datetime(until_str)

    return since, until
