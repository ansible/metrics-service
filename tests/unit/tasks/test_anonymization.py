"""
Test anonymization feature integration.

This module tests that the anonymize_collected_data task properly integrates
with metrics-utility's anonymization processor.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.tasks.tasks import anonymize_collected_data


@pytest.mark.unit
class TestAnonymizationIntegration:
    """Test that anonymization task properly uses metrics-utility."""

    @patch("apps.tasks.tasks.anonymized_rollups_processor")
    @patch("django.db.connections")
    @patch("django.conf.settings")
    def test_anonymize_collected_data_success(self, mock_settings, mock_connections, mock_processor):
        """Test successful anonymization."""
        # Setup mock settings
        mock_settings.MEDIA_ROOT = "/tmp/media"  # noqa: S108

        # Setup mock database connection
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        # Setup mock anonymization processor return value
        mock_anonymized_data = {
            "statistics": {
                "jobs_total": 100,
                "total_unique_hosts": 50,
            },
            "modules_used_per_playbook": [],
            "module_stats": [],
            "collection_name_stats": [],
            "jobs_by_template": [],
            "job_host_summary": [],
        }
        mock_processor.return_value = mock_anonymized_data

        # Call the task function
        result = anonymize_collected_data(
            database="awx",
            since="2024-01-01T00:00:00Z",
            until="2024-01-02T00:00:00Z",
            save_rollups=False,
        )

        # Verify Django connections was accessed with 'awx'
        mock_connections.__getitem__.assert_called_once_with("awx")

        # Verify processor was called with correct parameters
        mock_processor.assert_called_once()
        call_args = mock_processor.call_args
        assert call_args.kwargs["db"] == mock_db_connection
        # Verify salt was auto-generated and is a valid UUID string
        assert "salt" in call_args.kwargs
        assert isinstance(call_args.kwargs["salt"], str)
        assert len(call_args.kwargs["salt"]) == 36
        assert call_args.kwargs["save_rollups"] is False
        # Verify dates were converted to datetime objects
        assert isinstance(call_args.kwargs["since"], datetime)
        assert isinstance(call_args.kwargs["until"], datetime)

        # Verify result is successful
        assert result["status"] == "success"
        assert result["task_type"] == "anonymize_collected_data"
        assert "anonymized_data" in result
        assert result["anonymized_data"] == mock_anonymized_data
        assert result["parameters_used"]["database"] == "awx"
        assert result["parameters_used"]["save_rollups"] is False
        assert isinstance(result["parameters_used"]["since"], str)
        assert isinstance(result["parameters_used"]["until"], str)
        assert result["parameters_used"]["since"].startswith("2024-01-01")
        assert result["parameters_used"]["until"].startswith("2024-01-02")

    @patch("apps.tasks.tasks.anonymized_rollups_processor")
    @patch("django.db.connections")
    @patch("django.conf.settings")
    def test_anonymize_collected_data_defaults_to_awx(self, mock_settings, mock_connections, mock_processor):
        """Test that anonymize_collected_data defaults to 'awx' database."""
        # Setup mocks
        mock_settings.MEDIA_ROOT = "/tmp/media"  # noqa: S108
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection
        mock_processor.return_value = {}

        # Call without specifying database
        result = anonymize_collected_data()

        # Verify 'awx' was used as default
        mock_connections.__getitem__.assert_called_once_with("awx")
        assert result["parameters_used"]["database"] == "awx"

    @patch("apps.tasks.tasks.anonymized_rollups_processor")
    @patch("django.db.connections")
    @patch("django.conf.settings")
    def test_anonymize_collected_data_uses_media_root(self, mock_settings, mock_connections, mock_processor):
        """Test that anonymize_collected_data uses MEDIA_ROOT as default ship_path."""
        # Setup mocks
        mock_settings.MEDIA_ROOT = "/custom/media/path"  # noqa: S108
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection
        mock_processor.return_value = {}

        # Call without specifying ship_path
        anonymize_collected_data()

        # Verify MEDIA_ROOT was used
        call_args = mock_processor.call_args
        assert call_args.kwargs["ship_path"] == "/custom/media/path"

    @patch("apps.tasks.tasks.anonymized_rollups_processor")
    @patch("django.db.connections")
    @patch("django.conf.settings")
    def test_anonymize_collected_data_custom_ship_path(self, mock_settings, mock_connections, mock_processor):
        """Test that anonymize_collected_data accepts custom ship_path."""
        # Setup mocks
        mock_settings.MEDIA_ROOT = "/tmp/media"  # noqa: S108
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection
        mock_processor.return_value = {}

        # Call with custom ship_path
        anonymize_collected_data(ship_path="/custom/path")

        # Verify custom path was used
        call_args = mock_processor.call_args
        assert call_args.kwargs["ship_path"] == "/custom/path"

    @patch("apps.tasks.tasks.anonymized_rollups_processor")
    @patch("django.db.connections")
    @patch("django.conf.settings")
    def test_anonymize_collected_data_handles_processor_error(self, mock_settings, mock_connections, mock_processor):
        """Test that anonymize_collected_data handles errors from processor."""
        # Setup mocks
        mock_settings.MEDIA_ROOT = "/tmp/media"  # noqa: S108
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        # Setup processor to raise an exception
        mock_processor.side_effect = Exception("Database connection failed")

        # Call the task function
        result = anonymize_collected_data()

        # Verify error is handled
        assert result["status"] == "error"
        assert "Anonymization failed" in result["error"]
        assert "Database connection failed" in result["error"]

    @patch("apps.tasks.tasks.anonymized_rollups_processor")
    @patch("django.db.connections")
    @patch("django.conf.settings")
    def test_anonymize_collected_data_converts_date_strings(self, mock_settings, mock_connections, mock_processor):
        """Test that anonymize_collected_data converts string dates to datetime objects for processor."""
        # Setup mocks
        mock_settings.MEDIA_ROOT = "/tmp/media"  # noqa: S108
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection
        mock_processor.return_value = {}

        # Call with string dates
        result = anonymize_collected_data(
            since="2024-01-01T00:00:00Z",
            until="2024-01-02T00:00:00Z",
        )

        # Verify dates were converted to datetime objects for processor
        call_args = mock_processor.call_args
        assert isinstance(call_args.kwargs["since"], datetime)
        assert isinstance(call_args.kwargs["until"], datetime)
        assert call_args.kwargs["since"].isoformat().startswith("2024-01-01")
        assert call_args.kwargs["until"].isoformat().startswith("2024-01-02")

        # Verify dates are returned as ISO strings in result
        assert isinstance(result["parameters_used"]["since"], str)
        assert isinstance(result["parameters_used"]["until"], str)
        assert result["parameters_used"]["since"].startswith("2024-01-01")
        assert result["parameters_used"]["until"].startswith("2024-01-02")

    @patch("apps.tasks.tasks.anonymized_rollups_processor")
    @patch("django.db.connections")
    @patch("django.conf.settings")
    def test_anonymize_collected_data_invalid_date_format(self, mock_settings, mock_connections, mock_processor):
        """Test that anonymize_collected_data handles invalid date formats."""
        # Setup mocks
        mock_settings.MEDIA_ROOT = "/tmp/media"  # noqa: S108
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection

        # Call with invalid date format
        result = anonymize_collected_data(since="invalid-date")

        # Verify error is returned
        assert result["status"] == "error"
        assert "Invalid date format" in result["error"]

    @patch("apps.tasks.tasks.METRICS_UTILITY_AVAILABLE", False)
    def test_anonymize_collected_data_handles_missing_metrics_utility(self):
        """Test that anonymize_collected_data handles missing metrics-utility."""
        # Call the task function
        result = anonymize_collected_data()

        # Verify appropriate error is returned
        assert result["status"] == "error"
        assert "metrics-utility is not available" in result["error"]

    @patch("apps.tasks.tasks.anonymized_rollups_processor")
    @patch("django.db.connections")
    @patch("django.conf.settings")
    def test_anonymize_collected_data_save_rollups_default(self, mock_settings, mock_connections, mock_processor):
        """Test that save_rollups defaults to True."""
        # Setup mocks
        mock_settings.MEDIA_ROOT = "/tmp/media"  # noqa: S108
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection
        mock_processor.return_value = {}

        # Call without specifying save_rollups
        anonymize_collected_data()

        # Verify save_rollups defaults to True
        call_args = mock_processor.call_args
        assert call_args.kwargs["save_rollups"] is True

    @patch("apps.tasks.tasks.anonymized_rollups_processor")
    @patch("django.db.connections")
    @patch("django.conf.settings")
    def test_anonymize_collected_data_without_dates(self, mock_settings, mock_connections, mock_processor):
        """Test that anonymize_collected_data works without date parameters."""
        # Setup mocks
        mock_settings.MEDIA_ROOT = "/tmp/media"  # noqa: S108
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection
        mock_processor.return_value = {}

        # Call without dates
        result = anonymize_collected_data()

        # Verify it works
        assert result["status"] == "success"
        call_args = mock_processor.call_args
        assert call_args.kwargs["since"] is None
        assert call_args.kwargs["until"] is None
        assert result["parameters_used"]["since"] is None
        assert result["parameters_used"]["until"] is None

    @patch("apps.tasks.tasks.anonymized_rollups_processor")
    @patch("django.db.connections")
    @patch("django.conf.settings")
    def test_anonymize_collected_data_auto_generates_salt(self, mock_settings, mock_connections, mock_processor):
        """Test that anonymize_collected_data auto-generates a valid UUID salt."""
        # Setup mocks
        mock_settings.MEDIA_ROOT = "/tmp/media"  # noqa: S108
        mock_db_connection = MagicMock()
        mock_connections.__getitem__.return_value = mock_db_connection
        mock_processor.return_value = {}

        # Call the function
        result = anonymize_collected_data()

        # Verify salt was auto-generated
        assert result["status"] == "success"
        call_args = mock_processor.call_args

        # Verify salt exists and is a valid UUID format
        assert "salt" in call_args.kwargs
        salt = call_args.kwargs["salt"]
        assert isinstance(salt, str)
        assert len(salt) == 36

        # Verify salt has UUID structure (8-4-4-4-12 with dashes)
        parts = salt.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

        # Verify salt is masked in returned parameters
        assert result["parameters_used"]["salt"] == "******"
