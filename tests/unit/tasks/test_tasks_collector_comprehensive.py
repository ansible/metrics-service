"""
Comprehensive tests for apps/tasks/tasks_collector.py

This module provides extensive test coverage for all collector functions,
error conditions, and edge cases in the metrics collection system.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from apps.tasks.tasks_collector import (
    collect_all_metrics,
    collect_anonymous_metrics,
    collect_config_metrics,
    collect_host_metrics,
    collect_job_host_summary,
)


@pytest.mark.unit
class TestCollectAnonymousMetrics(TestCase):
    """Test collect_anonymous_metrics function."""

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.anonymized_rollups_processor")
    @patch("django.db.connections")
    def test_collect_anonymous_metrics_success(self, mock_connections, mock_processor):
        """Test successful anonymous metrics collection."""
        # Setup mocks
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        mock_metrics_data = {"rollups": [{"metric": "value"}], "count": 1, "processed_at": "2024-01-01T00:00:00Z"}
        mock_processor.return_value = mock_metrics_data

        # Test with default parameters
        result = collect_anonymous_metrics()

        # Verify database connection
        mock_connections.__getitem__.assert_called_once_with("awx")

        # Verify processor was called with correct parameters
        mock_processor.assert_called_once()
        call_args = mock_processor.call_args[1]
        assert call_args["db"] == mock_db_connection
        assert call_args["since"] is None
        assert call_args["until"] is None
        assert call_args["ship_path"] is None
        assert call_args["save_rollups"] is True
        assert "salt" in call_args

        # Verify result
        assert result["status"] == "success"
        assert result["task_type"] == "collect_anonymous_metrics"
        assert result["metrics_data"] == mock_metrics_data
        assert result["collector_type"] == "anonymized_rollups"

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.anonymized_rollups_processor")
    @patch("django.db.connections")
    def test_collect_anonymous_metrics_with_custom_parameters(self, mock_connections, mock_processor):
        """Test anonymous metrics collection with custom parameters."""
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection
        mock_processor.return_value = {"test": "data"}

        # Test with custom parameters
        test_ship_path = str(Path(tempfile.gettempdir()) / "test_metrics")
        kwargs = {
            "database": "custom_db",
            "since": "2024-01-01T00:00:00Z",
            "until": "2024-12-31T23:59:59Z",
            "salt": "custom-salt",
            "ship_path": test_ship_path,
            "save_rollups": False,
        }

        result = collect_anonymous_metrics(**kwargs)

        # Verify database connection with custom name
        mock_connections.__getitem__.assert_called_once_with("custom_db")

        # Verify processor was called with custom parameters
        call_args = mock_processor.call_args[1]
        assert call_args["since"] == "2024-01-01T00:00:00Z"
        assert call_args["until"] == "2024-12-31T23:59:59Z"
        assert call_args["salt"] == "custom-salt"
        assert call_args["ship_path"] == test_ship_path
        assert call_args["save_rollups"] is False

        # Verify parameters are included in result
        params = result["parameters_used"]
        assert params["database"] == "custom_db"
        assert params["since"] == "2024-01-01T00:00:00Z"
        assert params["salt"] == "custom-salt"

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_anonymous_metrics_utility_not_available(self):
        """Test when metrics-utility is not available."""
        result = collect_anonymous_metrics()

        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.anonymized_rollups_processor")
    @patch("django.db.connections")
    def test_collect_anonymous_metrics_database_error(self, mock_connections, mock_processor):
        """Test handling of database connection errors."""
        mock_connections.__getitem__.side_effect = Exception("Database not found")

        result = collect_anonymous_metrics(database="nonexistent")

        assert result["status"] == "error"
        assert "Collection failed" in result["error"]
        assert "Database not found" in result["error"]

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.anonymized_rollups_processor")
    @patch("django.db.connections")
    def test_collect_anonymous_metrics_processor_error(self, mock_connections, mock_processor):
        """Test handling of processor errors."""
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection
        mock_processor.side_effect = Exception("Processing failed")

        result = collect_anonymous_metrics()

        assert result["status"] == "error"
        assert "Collection failed" in result["error"]
        assert "Processing failed" in result["error"]


@pytest.mark.unit
class TestCollectConfigMetrics(TestCase):
    """Test collect_config_metrics function."""

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.config")
    @patch("django.db.connections")
    def test_collect_config_metrics_success(self, mock_connections, mock_config):
        """Test successful config metrics collection."""
        # Setup mocks
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        mock_collector = MagicMock()
        mock_config_data = {
            "controller_version": "4.5.0",
            "install_uuid": "test-uuid-123",
            "license_info": {"type": "open"},
        }
        mock_collector.gather.return_value = mock_config_data
        mock_config.return_value = mock_collector

        result = collect_config_metrics()

        # Verify collector instantiation and call
        mock_config.assert_called_once_with(db=mock_db_connection)
        mock_collector.gather.assert_called_once()

        # Verify result structure
        assert result["status"] == "success"
        assert result["task_type"] == "collect_config_metrics"
        assert result["config_data"] == mock_config_data
        assert result["collector_type"] == "config"

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.config")
    @patch("django.db.connections")
    def test_collect_config_metrics_with_custom_database(self, mock_connections, mock_config):
        """Test config metrics collection with custom database."""
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        mock_collector = MagicMock()
        mock_collector.gather.return_value = {}
        mock_config.return_value = mock_collector

        result = collect_config_metrics(database="test_db")

        mock_connections.__getitem__.assert_called_once_with("test_db")
        assert result["parameters_used"]["database"] == "test_db"

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_config_metrics_utility_not_available(self):
        """Test when metrics-utility is not available."""
        result = collect_config_metrics()

        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]


@pytest.mark.unit
class TestCollectHostMetrics(TestCase):
    """Test collect_host_metrics function."""

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.main_host")
    @patch("django.db.connections")
    def test_collect_host_metrics_success(self, mock_connections, mock_main_host):
        """Test successful host metrics collection."""
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        mock_collector = MagicMock()
        mock_host_data = {
            "hosts": [
                {"hostname": "host1", "last_job": "2024-01-01T00:00:00Z"},
                {"hostname": "host2", "last_job": "2024-01-02T00:00:00Z"},
            ],
            "total_count": 2,
        }
        mock_collector.gather.return_value = mock_host_data
        mock_main_host.return_value = mock_collector

        result = collect_host_metrics()

        # Verify collector usage
        mock_main_host.assert_called_once_with(db=mock_db_connection)
        mock_collector.gather.assert_called_once()

        # Verify result
        assert result["status"] == "success"
        assert result["task_type"] == "collect_host_metrics"
        assert result["host_data"] == mock_host_data
        assert result["collector_type"] == "main_host"

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.main_host")
    @patch("django.db.connections")
    def test_collect_host_metrics_with_date_range(self, mock_connections, mock_main_host):
        """Test host metrics collection with date range."""
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        mock_collector = MagicMock()
        mock_collector.gather.return_value = {"filtered_hosts": []}
        mock_main_host.return_value = mock_collector

        kwargs = {"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-01-31T23:59:59Z"}

        result = collect_host_metrics(**kwargs)

        # Verify parameters are passed through
        assert result["parameters_used"]["start_date"] == "2024-01-01T00:00:00Z"
        assert result["parameters_used"]["end_date"] == "2024-01-31T23:59:59Z"

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_host_metrics_utility_not_available(self):
        """Test when metrics-utility is not available."""
        result = collect_host_metrics()

        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]


@pytest.mark.unit
class TestCollectJobHostSummary(TestCase):
    """Test collect_job_host_summary function."""

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", True)
    @patch("apps.tasks.tasks_collector.job_host_summary")
    @patch("django.db.connections")
    def test_collect_job_host_summary_success(self, mock_connections, mock_job_host_summary):
        """Test successful job host summary collection."""
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        mock_collector = MagicMock()
        mock_summary_data = {
            "job_summaries": [
                {"job_id": 1, "host_count": 5, "success_count": 5},
                {"job_id": 2, "host_count": 3, "success_count": 2},
            ],
            "total_jobs": 2,
        }
        mock_collector.gather.return_value = mock_summary_data
        mock_job_host_summary.return_value = mock_collector

        result = collect_job_host_summary()

        # Verify collector usage
        mock_job_host_summary.assert_called_once_with(db=mock_db_connection)
        mock_collector.gather.assert_called_once()

        # Verify result structure
        assert result["status"] == "success"
        assert result["task_type"] == "collect_job_host_summary"
        assert result["summary_data"] == mock_summary_data
        assert result["collector_type"] == "job_host_summary"

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", False)
    def test_collect_job_host_summary_utility_not_available(self):
        """Test when metrics-utility is not available."""
        result = collect_job_host_summary()

        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]


@pytest.mark.unit
class TestCollectAllMetrics(TestCase):
    """Test collect_all_metrics function."""

    @patch("apps.tasks.tasks_collector.collect_config_metrics")
    @patch("apps.tasks.tasks_collector.collect_host_metrics")
    @patch("apps.tasks.tasks_collector.collect_job_host_summary")
    def test_collect_all_metrics_success(self, mock_job_summary, mock_host, mock_config):
        """Test successful collection of all metrics."""
        # Setup mock responses
        mock_config.return_value = {"status": "success", "config_data": {}}
        mock_host.return_value = {"status": "success", "host_data": {}}
        mock_job_summary.return_value = {"status": "success", "summary_data": {}}

        result = collect_all_metrics()

        # Verify all collectors were called
        mock_config.assert_called_once()
        mock_host.assert_called_once()
        mock_job_summary.assert_called_once()

        # Verify result structure
        assert result["status"] == "success"
        assert result["task_type"] == "collect_all_metrics"
        assert "config_result" in result["results"]
        assert "host_result" in result["results"]
        assert "job_host_summary_result" in result["results"]
        assert result["results"]["config_result"]["status"] == "success"

    @patch("apps.tasks.tasks_collector.collect_config_metrics")
    @patch("apps.tasks.tasks_collector.collect_host_metrics")
    @patch("apps.tasks.tasks_collector.collect_job_host_summary")
    def test_collect_all_metrics_with_database_parameter(self, mock_job_summary, mock_host, mock_config):
        """Test collect_all_metrics with custom database parameter."""
        mock_config.return_value = {"status": "success"}
        mock_host.return_value = {"status": "success"}
        mock_job_summary.return_value = {"status": "success"}

        result = collect_all_metrics(database="custom_db")

        # Verify all collectors were called with database parameter
        mock_config.assert_called_once_with(database="custom_db")
        mock_host.assert_called_once_with(database="custom_db")
        mock_job_summary.assert_called_once_with(database="custom_db")

        assert result["parameters_used"]["database"] == "custom_db"

    @patch("apps.tasks.tasks_collector.collect_config_metrics")
    @patch("apps.tasks.tasks_collector.collect_host_metrics")
    @patch("apps.tasks.tasks_collector.collect_job_host_summary")
    def test_collect_all_metrics_partial_failure(self, mock_job_summary, mock_host, mock_config):
        """Test collect_all_metrics when some collectors fail."""
        # Setup mixed success/failure responses
        mock_config.return_value = {"status": "success", "config_data": {}}
        mock_host.return_value = {"status": "error", "error": "Host collection failed"}
        mock_job_summary.return_value = {"status": "success", "summary_data": {}}

        result = collect_all_metrics()

        # Should still succeed overall but include failure details
        assert result["status"] == "success"
        assert result["results"]["config_result"]["status"] == "success"
        assert result["results"]["host_result"]["status"] == "error"
        assert result["results"]["job_host_summary_result"]["status"] == "success"

    @patch("apps.tasks.tasks_collector.collect_config_metrics")
    @patch("apps.tasks.tasks_collector.collect_host_metrics")
    @patch("apps.tasks.tasks_collector.collect_job_host_summary")
    def test_collect_all_metrics_all_failures(self, mock_job_summary, mock_host, mock_config):
        """Test collect_all_metrics when all collectors fail."""
        # Setup all failure responses
        mock_config.return_value = {"status": "error", "error": "Config failed"}
        mock_host.return_value = {"status": "error", "error": "Host failed"}
        mock_job_summary.return_value = {"status": "error", "error": "Summary failed"}

        result = collect_all_metrics()

        # Should still have success status but with error details
        assert result["status"] == "success"  # Wrapper succeeds even if collectors fail
        assert result["results"]["config_result"]["status"] == "error"
        assert result["results"]["host_result"]["status"] == "error"
        assert result["results"]["job_host_summary_result"]["status"] == "error"


@pytest.mark.unit
class TestCollectorModuleImports(TestCase):
    """Test module import handling and fallbacks."""

    def test_constants_defined(self):
        """Test that required constants are defined."""
        from apps.tasks.tasks_collector import (
            EXAMPLE_START_DATE,
            LABEL_DB_CONNECTION,
            LABEL_END_DATE,
            LABEL_METRICS_COLLECTION,
            LABEL_START_DATE,
            MSG_METRICS_UTILITY_NOT_AVAILABLE,
        )

        assert MSG_METRICS_UTILITY_NOT_AVAILABLE == "metrics-utility is not available"
        assert LABEL_METRICS_COLLECTION == "Metrics Collection"
        assert LABEL_DB_CONNECTION == "Database name from Django settings (default: 'awx')"
        assert EXAMPLE_START_DATE == "2024-01-01T00:00:00Z"
        assert LABEL_START_DATE == "Start date for collection (ISO format)"
        assert LABEL_END_DATE == "End date for collection (ISO format)"

    @patch("apps.tasks.tasks_collector.METRICS_UTILITY_AVAILABLE", False)
    def test_fallback_attributes_when_import_fails(self):
        """Test that fallback attributes are set when metrics-utility import fails."""
        from apps.tasks.tasks_collector import (
            anonymized_rollups_processor,
            config,
            job_host_summary,
            main_host,
            main_jobevent,
        )

        # When METRICS_UTILITY_AVAILABLE is False, these should be None
        assert anonymized_rollups_processor is None
        assert config is None
        assert job_host_summary is None
        assert main_host is None
        assert main_jobevent is None
