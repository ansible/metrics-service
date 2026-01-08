"""
Test collector integration with AWX database.

This module tests that collectors from metrics-utility can properly
connect to and query the AWX database configured in Django settings.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.tasks.tasks import collect_single_collector


@pytest.mark.unit
class TestCollectorDatabaseIntegration:
    """Test that collectors properly use Django database connections."""

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.config")
    @patch("apps.tasks.tasks_collector.csv_to_json")
    @patch("django.db.connections")
    def test_collect_single_collector_uses_django_connection(
        self, mock_connections, mock_csv_to_json, mock_config_collector
    ):
        """Test that collect_single_collector uses Django database connection."""
        # Setup mock database connection with .connection attribute
        # get_db_connection returns django_connection.connection (raw psycopg2 connection)
        mock_raw_connection = MagicMock()
        mock_db_connection = MagicMock()
        mock_db_connection.connection = mock_raw_connection
        mock_connections.__getitem__.return_value = mock_db_connection

        # Setup mock collector return value
        mock_collector_instance = MagicMock()
        mock_collector_instance.gather.return_value = ["/tmp/config.csv"]  # noqa: S108
        mock_config_collector.return_value = mock_collector_instance

        # Setup CSV to JSON conversion
        mock_csv_to_json.return_value = {
            "controller_version": "4.5.0",
            "install_uuid": "test-uuid",
        }

        # Call the task function
        result = collect_single_collector(collector_type="config", database="awx")

        # Verify Django connections was accessed with 'awx'
        mock_connections.__getitem__.assert_called_once_with("awx")

        # Verify collector was called with the raw connection (.connection attribute)
        mock_config_collector.assert_called_once_with(db=mock_raw_connection)

        # Verify collector.gather() was called
        mock_collector_instance.gather.assert_called_once()

        # Verify result is successful
        assert result["status"] == "success"
        assert result["collector_type"] == "config"
        assert result["parameters_used"]["database"] == "awx"
        assert "collected_data" in result

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.config")
    @patch("django.db.connections")
    def test_collect_single_collector_csv_output(self, mock_connections, mock_config_collector):
        """Test that collect_single_collector can return CSV file paths."""
        # Setup mocks with .connection attribute
        mock_raw_connection = MagicMock()
        mock_db_connection = MagicMock()
        mock_db_connection.connection = mock_raw_connection
        mock_connections.__getitem__.return_value = mock_db_connection

        mock_collector_instance = MagicMock()
        mock_collector_instance.gather.return_value = ["/tmp/config.csv"]  # noqa: S108
        mock_config_collector.return_value = mock_collector_instance

        # Call with CSV output format
        result = collect_single_collector(collector_type="config", output_format="csv")

        # Verify CSV output
        assert result["status"] == "success"
        assert "csv_files" in result
        assert result["csv_files"] == ["/tmp/config.csv"]  # noqa: S108
        assert result["file_count"] == 1

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.config")
    @patch("apps.tasks.tasks_collector.csv_to_json")
    @patch("django.db.connections")
    def test_collect_single_collector_handles_collector_error(
        self, mock_connections, mock_csv_to_json, mock_config_collector
    ):
        """Test that collect_single_collector handles errors from collector."""
        # Setup mock with .connection attribute to raise an exception
        mock_raw_connection = MagicMock()
        mock_db_connection = MagicMock()
        mock_db_connection.connection = mock_raw_connection
        mock_connections.__getitem__.return_value = mock_db_connection

        mock_collector_instance = MagicMock()
        mock_collector_instance.gather.side_effect = Exception("Database connection failed")
        mock_config_collector.return_value = mock_collector_instance

        # Call the task function
        result = collect_single_collector(collector_type="config")

        # Verify error is handled
        assert result["status"] == "error"
        assert "Collection failed" in result["error"]
        assert "Database connection failed" in result["error"]

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_single_collector_handles_missing_metrics_utility(self):
        """Test that collect_single_collector handles missing metrics-utility."""
        # Call the task function
        result = collect_single_collector(collector_type="config")

        # Verify appropriate error is returned
        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]

    def test_collect_single_collector_requires_collector_type(self):
        """Test that collect_single_collector requires collector_type parameter."""
        # Call without collector_type
        result = collect_single_collector()

        # Verify error is returned
        assert result["status"] == "error"
        assert "collector_type parameter is required" in result["error"]
