"""
Conftest for dashboard_reports integration tests.

Mocks AWX database connection for all tests in this directory.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_awx_db_connection():
    """Mock get_db_connection so tests don't require a real AWX database."""
    with patch(
        "apps.dashboard_reports.viewsets.filter_options.get_db_connection",
        return_value=MagicMock(),
    ):
        yield
