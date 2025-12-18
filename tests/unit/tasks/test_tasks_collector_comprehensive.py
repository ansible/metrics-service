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
    collect_anonymous_metrics,
    collect_config_metrics,
    collect_host_metrics,
    collect_job_host_summary,
)


@pytest.mark.unit
class TestCollectAnonymousMetrics(TestCase):
    """Test collect_anonymous_metrics function."""

    @patch("apps.tasks.tasks_collector.metrics_utility_available", True)
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

    @patch("apps.tasks.tasks_collector.metrics_utility_available", True)
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

    @patch("apps.tasks.tasks_collector.metrics_utility_available", False)
    def test_collect_anonymous_metrics_utility_not_available(self):
        """Test when metrics-utility is not available."""
        result = collect_anonymous_metrics()

        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]

    @patch("apps.tasks.tasks_collector.metrics_utility_available", True)
    @patch("apps.tasks.tasks_collector.anonymized_rollups_processor")
    @patch("django.db.connections")
    def test_collect_anonymous_metrics_database_error(self, mock_connections, mock_processor):
        """Test handling of database connection errors."""
        mock_connections.__getitem__.side_effect = Exception("Database not found")

        result = collect_anonymous_metrics(database="nonexistent")

        assert result["status"] == "error"
        assert "Collection failed" in result["error"]
        assert "Database not found" in result["error"]

    @patch("apps.tasks.tasks_collector.metrics_utility_available", True)
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

    @patch("apps.tasks.tasks_collector.metrics_utility_available", True)
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

    @patch("apps.tasks.tasks_collector.metrics_utility_available", True)
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

    @patch("apps.tasks.tasks_collector.metrics_utility_available", False)
    def test_collect_config_metrics_utility_not_available(self):
        """Test when metrics-utility is not available."""
        result = collect_config_metrics()

        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]


@pytest.mark.unit
class TestCollectHostMetrics(TestCase):
    """Test collect_host_metrics function."""

    @patch("apps.tasks.tasks_collector.metrics_utility_available", True)
    @patch("apps.tasks.tasks_collector.main_jobevent")
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
        assert result["collector_type"] == "main_jobevent"

    @patch("apps.tasks.tasks_collector.metrics_utility_available", False)
    def test_collect_host_metrics_utility_not_available(self):
        """Test when metrics-utility is not available."""
        result = collect_host_metrics()

        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]


@pytest.mark.unit
class TestCollectJobHostSummary(TestCase):
    """Test collect_job_host_summary function."""

    @patch("apps.tasks.tasks_collector.metrics_utility_available", True)
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

    @patch("apps.tasks.tasks_collector.metrics_utility_available", False)
    def test_collect_job_host_summary_utility_not_available(self):
        """Test when metrics-utility is not available."""
        result = collect_job_host_summary()

        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]


@pytest.mark.unit
class TestCollectAllMetrics(TestCase):
    """Test collect_all_metrics function."""

    @patch("apps.tasks.tasks_collector.metrics_utility_available", True)
    @patch("apps.tasks.tasks_collector.connections")
    @patch("apps.tasks.tasks_collector.collect_from_multiple_collectors")
    def test_collect_all_metrics_success(self, mock_collect_multiple, mock_connections):
        """Test successful collection from all collectors."""
        from apps.tasks.tasks_collector import collect_all_metrics

        # Mock the return value from collect_from_multiple_collectors
        mock_collect_multiple.return_value = {
            "anonymized_rollups": {"data": "test_anonymized"},
            "config": {"data": "test_config"},
            "main_jobevent": {"data": "test_jobevent"},
        }

        # Mock database connection
        mock_connections.__getitem__.return_value = MagicMock()

        result = collect_all_metrics(database="awx", since="2024-01-01", until="2024-01-31")

        assert result["status"] == "success"
        assert result["task_type"] == "collect_all_metrics"
        assert "all_results" in result
        assert result["collectors_run"] == ["anonymized_rollups", "config", "main_jobevent"]

    @patch("apps.tasks.tasks_collector.metrics_utility_available", False)
    def test_collect_all_metrics_no_utility(self):
        """Test behavior when metrics-utility not available."""
        from apps.tasks.tasks_collector import collect_all_metrics

        result = collect_all_metrics()

        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]

    @patch("apps.tasks.tasks_collector.metrics_utility_available", True)
    @patch("apps.tasks.tasks_collector.connections")
    @patch("apps.tasks.tasks_collector.collect_from_multiple_collectors")
    def test_collect_all_metrics_with_custom_collectors(self, mock_collect_multiple, mock_connections):
        """Test collection with custom collector list."""
        from apps.tasks.tasks_collector import collect_all_metrics

        mock_collect_multiple.return_value = {
            "config": {"data": "test_config"},
            "main_jobevent": {"data": "test_jobevent"},
        }

        mock_connections.__getitem__.return_value = MagicMock()

        result = collect_all_metrics(
            database="awx",
            collectors=["config", "main_jobevent"],
        )

        assert result["status"] == "success"
        assert result["collectors_run"] == ["config", "main_jobevent"]
        mock_collect_multiple.assert_called_once()


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

    def test_fallback_attributes_when_import_fails(self):
        """Test that fallback attributes are set when metrics-utility import fails."""
        import apps.tasks.tasks_collector as collector_module

        # Check the current state of metrics_utility_available
        if collector_module.metrics_utility_available:
            # If metrics-utility is available, the imports should be functions/classes
            assert collector_module.anonymized_rollups_processor is not None
            assert collector_module.config is not None
            assert collector_module.job_host_summary is not None
            assert collector_module.main_host is not None
            assert collector_module.main_jobevent is not None
        else:
            # If metrics-utility is not available, these should be None (fallback values)
            assert collector_module.anonymized_rollups_processor is None
            assert collector_module.config is None
            assert collector_module.job_host_summary is None
            assert collector_module.main_host is None
            assert collector_module.main_jobevent is None
