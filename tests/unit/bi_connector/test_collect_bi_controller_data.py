"""
Tests for apps/bi_connector/collectors/collect_bi_controller_data.py
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.bi_connector.collectors.collect_bi_controller_data import collect_bi_controller_data

_HOURLY_COLLECTORS_PATCH = "apps.bi_connector.collectors.collect_bi_controller_data.get_hourly_collectors"
_DB_PATCH = "apps.bi_connector.collectors.collect_bi_controller_data.get_db_connection"
_PARSE_DT_PATCH = "apps.bi_connector.collectors.collect_bi_controller_data.parse_datetime_string"

VALID_SINCE = "2025-03-01T00:00:00Z"
VALID_UNTIL = "2025-03-07T23:59:59Z"


@pytest.mark.unit
class TestCollectBiControllerData:
    """Unit tests for the collect_bi_controller_data task function."""

    def test_missing_task_data_returns_error(self):
        result = collect_bi_controller_data(None)
        assert result["status"] == "error"
        assert "task_data must contain" in result["error"]

    def test_missing_collector_key_returns_error(self):
        result = collect_bi_controller_data({"since": VALID_SINCE, "until": VALID_UNTIL})
        assert result["status"] == "error"
        assert "task_data must contain" in result["error"]

    def test_missing_since_returns_error(self):
        result = collect_bi_controller_data({"collector_key": "unified_jobs", "until": VALID_UNTIL})
        assert result["status"] == "error"
        assert "task_data must contain" in result["error"]

    def test_missing_until_returns_error(self):
        result = collect_bi_controller_data({"collector_key": "unified_jobs", "since": VALID_SINCE})
        assert result["status"] == "error"
        assert "task_data must contain" in result["error"]

    def test_invalid_since_datetime_returns_error(self):
        result = collect_bi_controller_data(
            {"collector_key": "unified_jobs", "since": "not-a-date", "until": VALID_UNTIL}
        )
        assert result["status"] == "error"
        assert "Invalid datetime" in result["error"]

    def test_invalid_until_datetime_returns_error(self):
        result = collect_bi_controller_data(
            {"collector_key": "unified_jobs", "since": VALID_SINCE, "until": "not-a-date"}
        )
        assert result["status"] == "error"
        assert "Invalid datetime" in result["error"]

    def test_awx_db_unavailable_returns_error(self):
        with patch(_DB_PATCH, side_effect=Exception("connection refused")):
            result = collect_bi_controller_data(
                {"collector_key": "unified_jobs", "since": VALID_SINCE, "until": VALID_UNTIL}
            )
        assert result["status"] == "error"
        assert result["error"] == "AWX database unavailable"

    def test_unknown_collector_key_returns_error(self):
        with (
            patch(_DB_PATCH, return_value=MagicMock()),
            patch(_HOURLY_COLLECTORS_PATCH, return_value={}),
        ):
            result = collect_bi_controller_data(
                {"collector_key": "nonexistent_collector", "since": VALID_SINCE, "until": VALID_UNTIL}
            )
        assert result["status"] == "error"
        assert "Unknown collector_key" in result["error"]

    def test_collector_gather_exception_returns_error(self):
        mock_collector = MagicMock()
        mock_collector.gather.side_effect = RuntimeError("query timeout")
        mock_collectors = {
            "unified_jobs": {"collector_func": lambda **kw: mock_collector},
        }
        with (
            patch(_DB_PATCH, return_value=MagicMock()),
            patch(_HOURLY_COLLECTORS_PATCH, return_value=mock_collectors),
        ):
            result = collect_bi_controller_data(
                {"collector_key": "unified_jobs", "since": VALID_SINCE, "until": VALID_UNTIL}
            )
        assert result["status"] == "error"
        assert result["error"] == "Collection failed"

    def test_successful_collection_returns_success(self):
        expected_data = [{"id": 1, "name": "job1"}, {"id": 2, "name": "job2"}]
        mock_collector = MagicMock()
        mock_collector.gather.return_value = expected_data
        mock_collectors = {
            "unified_jobs": {"collector_func": lambda **kw: mock_collector},
        }
        with (
            patch(_DB_PATCH, return_value=MagicMock()),
            patch(_HOURLY_COLLECTORS_PATCH, return_value=mock_collectors),
        ):
            result = collect_bi_controller_data(
                {"collector_key": "unified_jobs", "since": VALID_SINCE, "until": VALID_UNTIL}
            )
        assert result["status"] == "success"
        assert result["collector_type"] == "unified_jobs"
        assert result["since"] == VALID_SINCE
        assert result["until"] == VALID_UNTIL
        assert result["data"] == expected_data

    def test_successful_collection_includes_all_required_keys(self):
        mock_collector = MagicMock()
        mock_collector.gather.return_value = []
        mock_collectors = {
            "job_host_summary_service": {"collector_func": lambda **kw: mock_collector},
        }
        with (
            patch(_DB_PATCH, return_value=MagicMock()),
            patch(_HOURLY_COLLECTORS_PATCH, return_value=mock_collectors),
        ):
            result = collect_bi_controller_data(
                {
                    "collector_key": "job_host_summary_service",
                    "since": VALID_SINCE,
                    "until": VALID_UNTIL,
                }
            )
        assert "status" in result
        assert "collector_type" in result
        assert "since" in result
        assert "until" in result
        assert "data" in result

    def test_collector_func_receives_db_since_until(self):
        mock_collector = MagicMock()
        mock_collector.gather.return_value = []
        captured_kwargs = {}

        def capturing_collector_func(**kw):
            captured_kwargs.update(kw)
            return mock_collector

        mock_collectors = {
            "unified_jobs": {"collector_func": capturing_collector_func},
        }
        mock_conn = MagicMock()
        with (
            patch(_DB_PATCH, return_value=mock_conn),
            patch(_HOURLY_COLLECTORS_PATCH, return_value=mock_collectors),
        ):
            collect_bi_controller_data({"collector_key": "unified_jobs", "since": VALID_SINCE, "until": VALID_UNTIL})
        assert "db" in captured_kwargs
        assert captured_kwargs["db"] is mock_conn
