"""
Conftest for dashboard_reports integration tests.

Mocks AWX database connection for all tests in this directory.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_awx_db_connection():
    """Mock get_db_connection so tests don't require a real AWX database."""
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.description = []
    mock_cursor.fetchall.return_value = []
    # COUNT(*) subquery must return an integer 0, not a MagicMock, so that
    # range(total) in the paginator receives a real int and produces count=0.
    mock_cursor.fetchone.return_value = (0,)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch(
        "apps.dashboard_reports.viewsets.filter_options.get_db_connection",
        return_value=mock_conn,
    ):
        yield
