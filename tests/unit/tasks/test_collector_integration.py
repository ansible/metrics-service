"""
Test collector integration with AWX database.

This module tests that collectors from metrics-utility can properly
connect to and query the AWX database configured in Django settings.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.tasks.tasks import collect_config_metrics


@pytest.mark.unit
class TestCollectorDatabaseIntegration:
    """Test that collectors properly use Django database connections."""

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.config")
    @patch("django.db.connections")
    def test_collect_config_metrics_uses_django_connection(self, mock_connections, mock_config_collector):
        """Test that collect_config_metrics uses Django database connection."""
        # Setup mock database connection
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        # Setup mock collector return value
        mock_collector_instance = MagicMock()
        mock_collector_instance.gather.return_value = {
            "controller_version": "4.5.0",
            "install_uuid": "test-uuid",
        }
        mock_config_collector.return_value = mock_collector_instance

        # Call the task function
        result = collect_config_metrics(database="awx")

        # Verify Django connections was accessed with 'awx'
        mock_connections.__getitem__.assert_called_once_with("awx")

        # Verify collector was called with the Django connection
        mock_config_collector.assert_called_once_with(db=mock_db_connection)

        # Verify collector.gather() was called
        mock_collector_instance.gather.assert_called_once()

        # Verify result is successful
        assert result["status"] == "success"
        assert result["collector_type"] == "config"
        assert result["parameters_used"]["database"] == "awx"
        assert "config_data" in result

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.config")
    @patch("django.db.connections")
    def test_collect_config_metrics_defaults_to_awx_database(self, mock_connections, mock_config_collector):
        """Test that collect_config_metrics defaults to 'awx' database."""
        # Setup mocks
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        mock_collector_instance = MagicMock()
        mock_collector_instance.gather.return_value = {}
        mock_config_collector.return_value = mock_collector_instance

        # Call without specifying database
        result = collect_config_metrics()

        # Verify 'awx' was used as default
        mock_connections.__getitem__.assert_called_once_with("awx")
        assert result["parameters_used"]["database"] == "awx"

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.config")
    @patch("django.db.connections")
    def test_collect_config_metrics_handles_collector_error(self, mock_connections, mock_config_collector):
        """Test that collect_config_metrics handles errors from collector."""
        # Setup mock to raise an exception
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        mock_collector_instance = MagicMock()
        mock_collector_instance.gather.side_effect = Exception("Database connection failed")
        mock_config_collector.return_value = mock_collector_instance

        # Call the task function
        result = collect_config_metrics()

        # Verify error is handled
        assert result["status"] == "error"
        assert "Collection failed" in result["error"]
        assert "Database connection failed" in result["error"]

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_config_metrics_handles_missing_metrics_utility(self):
        """Test that collect_config_metrics handles missing metrics-utility."""
        # Call the task function
        result = collect_config_metrics()

        # Verify appropriate error is returned
        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]
