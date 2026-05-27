"""
Unit tests for the AWX database grant guard introduced in AAP-76771.

Covers:
- AwxDbNotReadyError: exception class is importable and is an Exception subclass
- check_awx_db_grant: returns None when db_connection is None (no-op)
- check_awx_db_grant: returns None when sentinel SELECT succeeds (grant present)
- check_awx_db_grant: raises AwxDbNotReadyError on "permission denied" psycopg2 error
- check_awx_db_grant: raises AwxDbNotReadyError on "insufficient_privilege" error text
- check_awx_db_grant: re-raises non-permission errors unchanged
- generic_collect_metrics: returns retriable error (no HourlyMetricsCollection written)
  when check_awx_db_grant raises AwxDbNotReadyError
- generic_collect_metrics: proceeds normally when check_awx_db_grant passes (grant present)
"""

from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# AwxDbNotReadyError
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAwxDbNotReadyError:
    """AwxDbNotReadyError exception class tests."""

    def test_is_exception_subclass(self):
        """AwxDbNotReadyError must be a subclass of Exception."""
        from apps.tasks.utils import AwxDbNotReadyError

        assert issubclass(AwxDbNotReadyError, Exception)

    def test_can_be_raised_and_caught(self):
        """AwxDbNotReadyError can be raised and caught as Exception."""
        from apps.tasks.utils import AwxDbNotReadyError

        with pytest.raises(AwxDbNotReadyError, match="will retry"):
            raise AwxDbNotReadyError("AWX database SELECT grant not yet available — will retry")

    def test_caught_as_generic_exception(self):
        """AwxDbNotReadyError is caught by a bare except Exception block."""
        from apps.tasks.utils import AwxDbNotReadyError

        caught = False
        try:
            raise AwxDbNotReadyError("test")
        except Exception:
            caught = True

        assert caught


# ---------------------------------------------------------------------------
# check_awx_db_grant
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckAwxDbGrant:
    """Unit tests for check_awx_db_grant helper."""

    def test_no_op_when_connection_is_none(self):
        """check_awx_db_grant must return None when db_connection is None."""
        from apps.tasks.utils import check_awx_db_grant

        result = check_awx_db_grant(None)
        assert result is None

    def test_returns_none_when_select_succeeds(self):
        """check_awx_db_grant returns None (no exception) when sentinel SELECT succeeds."""
        from apps.tasks.utils import check_awx_db_grant

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        result = check_awx_db_grant(mock_conn)

        assert result is None
        mock_cursor.execute.assert_called_once_with("SELECT 1 FROM main_unifiedjob LIMIT 1")

    def test_cursor_is_closed_after_success(self):
        """Cursor must be closed even when the SELECT succeeds."""
        from apps.tasks.utils import check_awx_db_grant

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        check_awx_db_grant(mock_conn)

        mock_cursor.close.assert_called_once()

    def test_raises_awx_not_ready_on_permission_denied(self):
        """check_awx_db_grant must raise AwxDbNotReadyError when 'permission denied' is in error."""
        from apps.tasks.utils import AwxDbNotReadyError, check_awx_db_grant

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("ERROR: permission denied for relation main_unifiedjob")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with pytest.raises(AwxDbNotReadyError, match="will retry"):
            check_awx_db_grant(mock_conn)

    def test_raises_awx_not_ready_on_insufficient_privilege(self):
        """check_awx_db_grant must raise AwxDbNotReadyError when 'insufficient_privilege' is in error."""
        from apps.tasks.utils import AwxDbNotReadyError, check_awx_db_grant

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("insufficient_privilege: SELECT denied")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with pytest.raises(AwxDbNotReadyError):
            check_awx_db_grant(mock_conn)

    def test_raises_awx_not_ready_on_sqlstate_42501(self):
        """check_awx_db_grant must raise AwxDbNotReadyError when '42501' is in error text."""
        from apps.tasks.utils import AwxDbNotReadyError, check_awx_db_grant

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("sqlstate: 42501")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with pytest.raises(AwxDbNotReadyError):
            check_awx_db_grant(mock_conn)

    def test_reraises_non_permission_errors_unchanged(self):
        """Non-privilege errors must be re-raised as-is (not wrapped)."""
        from apps.tasks.utils import check_awx_db_grant

        original_exc = ConnectionError("connection refused")
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = original_exc
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with pytest.raises(ConnectionError, match="connection refused"):
            check_awx_db_grant(mock_conn)

    def test_cursor_closed_after_permission_error(self):
        """Cursor must be closed even when a permission error is raised."""
        from apps.tasks.utils import AwxDbNotReadyError, check_awx_db_grant

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("permission denied for table foo")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with pytest.raises(AwxDbNotReadyError):
            check_awx_db_grant(mock_conn)

        mock_cursor.close.assert_called_once()

    def test_awx_not_ready_error_contains_original_message(self):
        """AwxDbNotReadyError message must include the original error text for diagnostics."""
        from apps.tasks.utils import AwxDbNotReadyError, check_awx_db_grant

        mock_cursor = MagicMock()
        original_msg = "ERROR: permission denied for relation main_unifiedjob"
        mock_cursor.execute.side_effect = Exception(original_msg)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with pytest.raises(AwxDbNotReadyError) as exc_info:
            check_awx_db_grant(mock_conn)

        assert original_msg in str(exc_info.value)


# ---------------------------------------------------------------------------
# generic_collect_metrics — AWX grant guard integration
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
class TestGenericCollectMetricsGrantGuard:
    """
    Integration tests for the AWX grant guard inside generic_collect_metrics.

    These tests verify that:
    1. When the grant is absent (check_awx_db_grant raises AwxDbNotReadyError),
       generic_collect_metrics returns a retriable error result and does NOT
       write a HourlyMetricsCollection record with status='failed'.
    2. When the grant is present (check_awx_db_grant passes),
       generic_collect_metrics proceeds normally.
    """

    def _make_registry(self, collector_mock=None):
        """Build a minimal collector registry for testing."""
        if collector_mock is None:
            collector_mock = MagicMock()
            collector_mock.return_value.gather.return_value = {"rows": []}

        return {
            "unified_jobs": {
                "collector_func": collector_mock,
                "rollup_processor": None,
                "description": "Unified jobs collector",
            }
        }

    def test_returns_error_without_writing_failed_record_when_grant_absent(self):
        """
        When check_awx_db_grant raises AwxDbNotReadyError, generic_collect_metrics
        must return an error result and must NOT write a HourlyMetricsCollection
        record with status='failed'.
        """
        from datetime import UTC, datetime

        from apps.tasks.models import HourlyMetricsCollection
        from apps.tasks.utils import AwxDbNotReadyError, generic_collect_metrics

        timestamp = datetime(2024, 3, 10, 5, 0, 0, tzinfo=UTC)
        registry = self._make_registry()
        mock_conn = MagicMock()

        with patch("apps.tasks.utils.check_awx_db_grant") as mock_guard:
            mock_guard.side_effect = AwxDbNotReadyError("AWX database SELECT grant not yet available — will retry")

            result = generic_collect_metrics(
                collector_type="unified_jobs",
                collector_registry=registry,
                collection_mode="hourly",
                timestamp=timestamp,
                db_connection=mock_conn,
            )

        assert result["status"] == "error"
        assert "will retry" in result["error"].lower() or "grant" in result["error"].lower()

        # Critical: no failed audit record should have been written
        failed_records = HourlyMetricsCollection.objects.filter(
            collector_type="unified_jobs",
            collection_timestamp=timestamp,
            status="failed",
        )
        assert not failed_records.exists(), (
            "A failed HourlyMetricsCollection record was written for a transient grant-absence error. "
            "This pollutes the audit trail and should not happen."
        )

    def test_collector_not_called_when_grant_absent(self):
        """When the grant is absent, the collector function must not be invoked."""
        from datetime import UTC, datetime

        from apps.tasks.utils import AwxDbNotReadyError, generic_collect_metrics

        timestamp = datetime(2024, 3, 10, 5, 0, 0, tzinfo=UTC)
        collector_mock = MagicMock()
        registry = self._make_registry(collector_mock)
        mock_conn = MagicMock()

        with patch("apps.tasks.utils.check_awx_db_grant") as mock_guard:
            mock_guard.side_effect = AwxDbNotReadyError("grant absent")

            generic_collect_metrics(
                collector_type="unified_jobs",
                collector_registry=registry,
                collection_mode="hourly",
                timestamp=timestamp,
                db_connection=mock_conn,
            )

        collector_mock.assert_not_called()

    def test_proceeds_normally_when_grant_present(self):
        """
        When check_awx_db_grant does not raise, generic_collect_metrics must
        proceed to call the collector and return a success result.
        """
        from datetime import UTC, datetime

        from apps.tasks.models import HourlyMetricsCollection
        from apps.tasks.utils import generic_collect_metrics

        timestamp = datetime(2024, 3, 10, 6, 0, 0, tzinfo=UTC)
        collector_mock = MagicMock()
        collector_mock.return_value.gather.return_value = {"rows": [{"job_id": 1}]}
        registry = self._make_registry(collector_mock)
        mock_conn = MagicMock()

        with patch("apps.tasks.utils.check_awx_db_grant") as mock_guard:
            mock_guard.return_value = None  # grant present, probe passes

            result = generic_collect_metrics(
                collector_type="unified_jobs",
                collector_registry=registry,
                collection_mode="hourly",
                timestamp=timestamp,
                db_connection=mock_conn,
            )

        assert result["status"] == "success"
        collector_mock.assert_called_once()

    def test_check_awx_db_grant_called_with_db_connection(self):
        """check_awx_db_grant must be invoked with the db_connection argument."""
        from datetime import UTC, datetime

        from apps.tasks.utils import generic_collect_metrics

        timestamp = datetime(2024, 3, 10, 7, 0, 0, tzinfo=UTC)
        registry = self._make_registry()
        mock_conn = MagicMock()

        with patch("apps.tasks.utils.check_awx_db_grant") as mock_guard:
            mock_guard.return_value = None

            generic_collect_metrics(
                collector_type="unified_jobs",
                collector_registry=registry,
                collection_mode="hourly",
                timestamp=timestamp,
                db_connection=mock_conn,
            )

        mock_guard.assert_called_once_with(mock_conn)

    def test_unknown_collector_type_still_returns_error_without_grant_check(self):
        """Unknown collector_type must return an error before the grant check is even invoked."""
        from datetime import UTC, datetime

        from apps.tasks.utils import generic_collect_metrics

        timestamp = datetime(2024, 3, 10, 8, 0, 0, tzinfo=UTC)
        registry = self._make_registry()
        mock_conn = MagicMock()

        with patch("apps.tasks.utils.check_awx_db_grant") as mock_guard:
            result = generic_collect_metrics(
                collector_type="nonexistent_type",
                collector_registry=registry,
                collection_mode="hourly",
                timestamp=timestamp,
                db_connection=mock_conn,
            )

        assert result["status"] == "error"
        assert "Unknown collector_type" in result["error"]
        mock_guard.assert_not_called()


# ---------------------------------------------------------------------------
# task_groups — AWX_COLLECTOR_MAX_ATTEMPTS constant and task config
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAwxCollectorMaxAttempts:
    """Verify that AWX_COLLECTOR_MAX_ATTEMPTS is defined and applied to relevant tasks."""

    def test_constant_is_defined(self):
        """AWX_COLLECTOR_MAX_ATTEMPTS must be importable from task_groups."""
        from apps.tasks.task_groups import AWX_COLLECTOR_MAX_ATTEMPTS

        assert AWX_COLLECTOR_MAX_ATTEMPTS >= 5

    def test_hourly_collectors_have_increased_max_attempts(self):
        """Hourly AWX collector tasks must carry max_attempts == AWX_COLLECTOR_MAX_ATTEMPTS."""
        from apps.tasks.task_groups import AWX_COLLECTOR_MAX_ATTEMPTS, METRICS_COLLECTION_GROUP

        awx_hourly_task_ids = {
            "hourly_job_host_summary",
            "hourly_unified_jobs",
            "hourly_credentials",
        }

        tasks_by_id = {t["task_id"]: t for t in METRICS_COLLECTION_GROUP.tasks}

        for task_id in awx_hourly_task_ids:
            task = tasks_by_id[task_id]
            assert task.get("max_attempts") == AWX_COLLECTOR_MAX_ATTEMPTS, (
                f"Task '{task_id}' should have max_attempts={AWX_COLLECTOR_MAX_ATTEMPTS} "
                f"but got {task.get('max_attempts')!r}"
            )

    def test_snapshot_collectors_have_increased_max_attempts(self):
        """Daily snapshot AWX collector tasks must carry max_attempts == AWX_COLLECTOR_MAX_ATTEMPTS."""
        from apps.tasks.task_groups import AWX_COLLECTOR_MAX_ATTEMPTS, METRICS_COLLECTION_GROUP

        awx_snapshot_task_ids = {
            "daily_execution_environments",
            "daily_config",
            "daily_controller_version",
            "daily_table_metadata",
            "daily_feature_flags",
        }

        tasks_by_id = {t["task_id"]: t for t in METRICS_COLLECTION_GROUP.tasks}

        for task_id in awx_snapshot_task_ids:
            task = tasks_by_id[task_id]
            assert task.get("max_attempts") == AWX_COLLECTOR_MAX_ATTEMPTS, (
                f"Task '{task_id}' should have max_attempts={AWX_COLLECTOR_MAX_ATTEMPTS} "
                f"but got {task.get('max_attempts')!r}"
            )
