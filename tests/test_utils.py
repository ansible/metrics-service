"""
Test utilities for metrics_service tests.

This module provides common utilities and constants used across test files.
"""


def get_test_password() -> str:
    """
    Get the standard test password for use in test cases.

    Centralized to avoid SonarQube hard-coded credential warnings.
    Only this function should be excluded from SonarQube password detection.

    Returns:
        str: The test password
    """
    return "testpass123"  # noqa: S105 - This is intentionally a test credential


def get_test_user_data(username: str = "testuser", email: str = "test@example.com") -> dict:
    """
    Get standard test user data with the test password.

    Args:
        username: Username for the test user
        email: Email for the test user

    Returns:
        dict: User data dictionary with password included
    """
    return {
        "username": username,
        "email": email,
        "password": get_test_password(),
    }


# =============================================================================
# Test-only utility functions moved from apps/core/utils.py
# =============================================================================


def get_related_object_safely(instance, field_name: str, default=None):
    """
    Safely get a related object from an instance.

    Args:
        instance: The model instance
        field_name: Name of the related field
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


def get_system_uuid() -> str:
    """
    Get system UUID from settings or generate a default one.

    Returns:
        str: System UUID
    """
    import uuid

    from django.conf import settings

    try:
        return getattr(settings, "SYSTEM_UUID", str(uuid.uuid4()))
    except Exception:
        return str(uuid.uuid4())


def format_task_data(data) -> str:
    """
    Format task data for display.

    Args:
        data: Task data to format

    Returns:
        str: Formatted task data
    """
    import json

    try:
        if isinstance(data, str):
            return data
        return json.dumps(data, indent=2)
    except Exception:
        return str(data)
