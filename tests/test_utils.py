"""
Test utilities for metrics_service tests.

This module provides common utilities and constants used across test files.
"""

from datetime import UTC, datetime
from io import StringIO
from unittest.mock import MagicMock

from apps.tasks.models import Task


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


def get_cmd():
    from apps.tasks.management.commands.metrics_service import Command
    from apps.tasks.services.output_formatter import OutputFormatter

    cmd = Command()
    cmd.stdout = StringIO()
    mock_style = MagicMock()
    mock_style.SUCCESS.side_effect = lambda msg: msg
    mock_style.ERROR.side_effect = lambda msg: msg
    mock_style.WARNING.side_effect = lambda msg: msg
    cmd.style = mock_style
    cmd.output = OutputFormatter(stdout=cmd.stdout, style=cmd.style)
    return cmd


def _times():
    started = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)
    finished = datetime(2026, 8, 17, 10, 1, tzinfo=UTC)
    return started, finished


def _create_task_safely(**kwargs):
    """Create a task without triggering signals."""
    task = Task(**kwargs)
    task.save()
    return task
