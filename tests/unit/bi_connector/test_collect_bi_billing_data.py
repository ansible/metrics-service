"""
Tests for apps/bi_connector/collectors/collect_bi_billing_data.py
"""

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from apps.bi_connector.collectors.collect_bi_billing_data import (
    _flush,
    _safe_dt,
    collect_bi_billing_data,
)
from apps.bi_connector.models import CollectionBatch

_DB_PATCH = "apps.bi_connector.collectors.collect_bi_billing_data.get_db_connection"
_REGISTRY_PATCH = "apps.bi_connector.collectors.collect_bi_billing_data._COLLECTOR_REGISTRY"


@pytest.mark.unit
class TestSafeDt:
    """Tests for _safe_dt() — the datetime coercion helper."""

    def test_none_returns_none(self):
        assert _safe_dt(None) is None

    def test_nat_returns_none(self):
        assert _safe_dt(pd.NaT) is None

    def test_naive_datetime_becomes_utc_aware(self):
        naive = datetime(2025, 3, 1, 12, 0, 0)
        result = _safe_dt(naive)
        assert result is not None
        assert result.tzinfo is not None
        assert result.tzinfo == UTC

    def test_aware_datetime_passes_through(self):
        aware = datetime(2025, 3, 1, 12, 0, 0, tzinfo=UTC)
        result = _safe_dt(aware)
        assert result == aware
        assert result.tzinfo is not None

    def test_aware_datetime_non_utc_passes_through(self):
        from datetime import timedelta

        tz = timezone(timedelta(hours=5))
        aware = datetime(2025, 3, 1, 12, 0, 0, tzinfo=tz)
        result = _safe_dt(aware)
        assert result == aware

    def test_pandas_timestamp_naive_becomes_utc(self):
        ts = pd.Timestamp("2025-03-01 12:00:00")
        result = _safe_dt(ts)
        assert result is not None
        assert result.tzinfo is not None

    def test_pandas_timestamp_aware_passes_through(self):
        ts = pd.Timestamp("2025-03-01 12:00:00", tz="UTC")
        result = _safe_dt(ts)
        assert result is not None
        assert result.tzinfo is not None

    def test_pandas_nat_returns_none(self):
        ts = pd.NaT
        result = _safe_dt(ts)
        assert result is None

    def test_nan_float_returns_none(self):

        result = _safe_dt(float("nan"))
        assert result is None


@pytest.mark.unit
class TestFlush:
    """Tests for _flush() — the bulk-create helper."""

    def test_empty_list_returns_zero(self):
        mock_model = MagicMock()
        records = []
        result = _flush(records, mock_model, unique_fields=["hostname"], update_fields=["host_id"])
        assert result == 0
        mock_model.objects.bulk_create.assert_not_called()

    def test_calls_bulk_create_with_correct_args(self):
        mock_model = MagicMock()
        records = [MagicMock(), MagicMock()]
        _flush(records, mock_model, unique_fields=["hostname"], update_fields=["host_id"])
        mock_model.objects.bulk_create.assert_called_once_with(
            records,
            update_conflicts=True,
            unique_fields=["hostname"],
            update_fields=["host_id"],
        )

    def test_clears_list_after_flush(self):
        mock_model = MagicMock()
        records = [MagicMock(), MagicMock(), MagicMock()]
        _flush(records, mock_model, unique_fields=["hostname"], update_fields=["host_id"])
        assert len(records) == 0

    def test_returns_count_of_flushed_records(self):
        mock_model = MagicMock()
        records = [MagicMock(), MagicMock(), MagicMock()]
        result = _flush(records, mock_model, unique_fields=["hostname"], update_fields=["host_id"])
        assert result == 3

    def test_returns_correct_count_for_single_record(self):
        mock_model = MagicMock()
        records = [MagicMock()]
        result = _flush(records, mock_model, unique_fields=["id"], update_fields=["name"])
        assert result == 1


@pytest.mark.unit
class TestCollectBiBillingDataValidation:
    """Validation tests for collect_bi_billing_data() that do not require DB."""

    def test_missing_collector_type_raises_value_error(self):
        with pytest.raises(ValueError, match="collector_type is required"):
            collect_bi_billing_data({})

    def test_none_task_data_raises_value_error(self):
        with pytest.raises(ValueError, match="collector_type is required"):
            collect_bi_billing_data(None)

    def test_empty_collector_type_raises_value_error(self):
        with pytest.raises(ValueError, match="collector_type is required"):
            collect_bi_billing_data({"collector_type": ""})

    def test_unknown_collector_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown collector_type"):
            collect_bi_billing_data({"collector_type": "nonexistent_billing_collector"})

    def test_unknown_collector_type_error_includes_valid_types(self):
        with pytest.raises(ValueError) as exc_info:
            collect_bi_billing_data({"collector_type": "bogus"})
        assert "main_host" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.django_db
class TestCollectBiBillingDataExecution:
    """Tests for collect_bi_billing_data() execution paths requiring DB."""

    def _create_batch(self, collector_type: str = "main_host") -> CollectionBatch:
        return CollectionBatch.objects.create(
            collector_type=collector_type,
            batch_type="scheduled",
            status="pending",
        )

    def test_batch_status_set_to_running_then_completed(self):
        batch = self._create_batch()
        mock_handler = MagicMock(return_value=5)
        mock_registry = {"main_host": mock_handler}

        with (
            patch(_DB_PATCH, return_value=MagicMock()),
            patch(_REGISTRY_PATCH, mock_registry),
        ):
            collect_bi_billing_data(
                {"collector_type": "main_host", "batch_id": batch.id}
            )

        batch.refresh_from_db()
        assert batch.status == "completed"
        assert batch.records_imported == 5
        assert batch.completed_at is not None

    def test_batch_status_set_to_failed_on_exception(self):
        batch = self._create_batch()
        mock_handler = MagicMock(side_effect=RuntimeError("handler failed"))
        mock_registry = {"main_host": mock_handler}
        task_data = {"collector_type": "main_host", "batch_id": batch.id}

        with (
            patch(_DB_PATCH, return_value=MagicMock()),
            patch(_REGISTRY_PATCH, mock_registry),
            pytest.raises(RuntimeError, match="handler failed"),
        ):
            collect_bi_billing_data(task_data)

        batch.refresh_from_db()
        assert batch.status == "failed"
        assert "handler failed" in batch.error_message

    def test_returns_success_dict(self):
        mock_handler = MagicMock(return_value=42)
        mock_registry = {"main_host": mock_handler}

        with (
            patch(_DB_PATCH, return_value=MagicMock()),
            patch(_REGISTRY_PATCH, mock_registry),
        ):
            result = collect_bi_billing_data({"collector_type": "main_host"})

        assert result["status"] == "success"
        assert result["collector_type"] == "main_host"
        assert result["records_imported"] == 42

    def test_dispatches_to_correct_handler(self):
        mock_conn = MagicMock()
        mock_handler = MagicMock(return_value=0)
        mock_registry = {"main_host": mock_handler}

        with (
            patch(_DB_PATCH, return_value=mock_conn),
            patch(_REGISTRY_PATCH, mock_registry),
        ):
            collect_bi_billing_data({"collector_type": "main_host"})

        mock_handler.assert_called_once()
        call_args = mock_handler.call_args
        assert call_args[0][0] is mock_conn  # conn passed as first positional arg

    def test_handler_receives_batch_when_provided(self):
        batch = self._create_batch()
        mock_conn = MagicMock()
        mock_handler = MagicMock(return_value=0)
        mock_registry = {"main_host": mock_handler}

        with (
            patch(_DB_PATCH, return_value=mock_conn),
            patch(_REGISTRY_PATCH, mock_registry),
        ):
            collect_bi_billing_data(
                {"collector_type": "main_host", "batch_id": batch.id}
            )

        call_args = mock_handler.call_args
        # batch is the 4th positional arg: handler(conn, since, until, batch)
        assert call_args[0][3].id == batch.id

    def test_handler_receives_parsed_since_and_until(self):
        mock_conn = MagicMock()
        mock_handler = MagicMock(return_value=0)
        mock_registry = {"main_host": mock_handler}

        with (
            patch(_DB_PATCH, return_value=mock_conn),
            patch(_REGISTRY_PATCH, mock_registry),
        ):
            collect_bi_billing_data(
                {
                    "collector_type": "main_host",
                    "since": "2025-03-01T00:00:00Z",
                    "until": "2025-03-07T00:00:00Z",
                }
            )

        call_args = mock_handler.call_args
        since = call_args[0][1]
        until = call_args[0][2]
        assert since is not None
        assert until is not None
        assert since.year == 2025
        assert since.month == 3

    def test_no_batch_id_runs_without_batch(self):
        mock_handler = MagicMock(return_value=10)
        mock_registry = {"main_host": mock_handler}

        with (
            patch(_DB_PATCH, return_value=MagicMock()),
            patch(_REGISTRY_PATCH, mock_registry),
        ):
            result = collect_bi_billing_data({"collector_type": "main_host"})

        assert result["status"] == "success"
        assert result["records_imported"] == 10

    def test_none_since_until_passed_to_handler_when_not_provided(self):
        mock_conn = MagicMock()
        mock_handler = MagicMock(return_value=0)
        mock_registry = {"main_host": mock_handler}

        with (
            patch(_DB_PATCH, return_value=mock_conn),
            patch(_REGISTRY_PATCH, mock_registry),
        ):
            collect_bi_billing_data({"collector_type": "main_host"})

        call_args = mock_handler.call_args
        assert call_args[0][1] is None  # since
        assert call_args[0][2] is None  # until
