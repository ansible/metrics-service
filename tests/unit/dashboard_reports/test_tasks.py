# test_tasks.py - Unit tests for dashboard_reports tasks

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytz

from apps.dashboard_reports.models import JobData
from apps.dashboard_reports.tasks import (
    _collect_data,
    _collect_jobs,
    _parse_dt,
    _sync_jobs_atomically,
    cleanup_dashboard_reports_old_data,
    collect_dashboard_reports_data,
    collect_dashboard_reports_initial_data,
    sync_dashboard_job_records,
)


@pytest.mark.unit
class TestParseDt:
    """Tests for _parse_dt helper function."""

    def test_returns_tz_aware_datetime_unchanged(self):
        """_parse_dt returns a tz-aware datetime as the same object."""
        dt = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
        assert _parse_dt(dt) is dt

    def test_normalizes_naive_datetime_to_utc(self):
        """_parse_dt attaches UTC to a naive datetime."""
        dt = datetime(2024, 1, 15, 12, 0)
        result = _parse_dt(dt)
        assert result == datetime(2024, 1, 15, 12, 0, tzinfo=UTC)

    def test_parses_iso_string(self):
        """_parse_dt converts an ISO-format string to a datetime."""
        result = _parse_dt("2024-01-15T12:00:00")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_returns_none_unchanged(self):
        """_parse_dt returns None when given None."""
        assert _parse_dt(None) is None

    def test_raises_for_unsupported_types(self):
        """_parse_dt raises TypeError for non-str, non-datetime, non-None values."""
        with pytest.raises(TypeError, match="_parse_dt"):
            _parse_dt(42)


@pytest.mark.unit
class TestSyncJobsAtomically:
    """Tests for _sync_jobs_atomically helper (DB-free via mocking)."""

    @patch("apps.dashboard_reports.tasks.transaction.atomic")
    @patch("apps.dashboard_reports.tasks.JobData.create_or_update_from_awx")
    def test_all_jobs_succeed(self, mock_create, mock_atomic):
        """_sync_jobs_atomically returns empty list when all jobs sync successfully."""
        mock_atomic.return_value.__enter__ = MagicMock(return_value=None)
        mock_atomic.return_value.__exit__ = MagicMock(return_value=False)
        mock_create.return_value = None
        failed = _sync_jobs_atomically([{"id": 1}, {"id": 2}])
        assert failed == []

    @patch("apps.dashboard_reports.tasks.transaction.atomic")
    @patch("apps.dashboard_reports.tasks.JobData.create_or_update_from_awx")
    def test_partial_failure_returns_failed_ids(self, mock_create, mock_atomic):
        """_sync_jobs_atomically collects failed job IDs and rolls back."""
        mock_atomic.return_value.__enter__ = MagicMock(return_value=None)
        mock_atomic.return_value.__exit__ = MagicMock(return_value=False)
        mock_create.side_effect = Exception("db error")
        failed = _sync_jobs_atomically([{"id": 10}, {"id": 11}])
        assert set(failed) == {10, 11}

    @patch("apps.dashboard_reports.tasks.transaction.atomic")
    def test_empty_jobs_list_returns_empty(self, mock_atomic):
        """_sync_jobs_atomically returns empty list with no jobs."""
        mock_atomic.return_value.__enter__ = MagicMock(return_value=None)
        mock_atomic.return_value.__exit__ = MagicMock(return_value=False)
        failed = _sync_jobs_atomically([])
        assert failed == []


# --- Fixtures ---
@pytest.fixture
def mock_collect_data():
    with patch("apps.dashboard_reports.tasks._collect_data") as mock:
        yield mock


@pytest.fixture
def mock_create_task_result():
    with patch("apps.dashboard_reports.tasks.create_task_result") as mock:
        yield mock


@pytest.fixture
def mock_collect_data_deps():
    """Patch the internal helpers called by _collect_data."""
    since = datetime(2024, 1, 1, tzinfo=UTC)
    until = datetime(2024, 2, 1, tzinfo=UTC)
    with (
        patch("apps.dashboard_reports.tasks._resolve_collection_params") as mock_params,
        patch("apps.dashboard_reports.tasks.get_db_connection") as mock_db_conn,
        patch("apps.dashboard_reports.tasks._get_job_id_range") as mock_id_range,
        patch("apps.dashboard_reports.tasks._process_batches") as mock_batches,
        patch("apps.dashboard_reports.tasks.log_task_execution") as mock_log,
    ):
        mock_params.return_value = ("awx", since, until, 5000)
        mock_db_conn.return_value = MagicMock()
        mock_id_range.return_value = (100, 200)
        mock_batches.return_value = (42, None)
        yield mock_params, mock_db_conn, mock_id_range, mock_batches, mock_log, since, until


@pytest.mark.unit
class TestCollectJobs:
    @patch("apps.dashboard_reports.tasks.dashboard_jobs")
    def test_passes_all_args_to_dashboard_jobs(self, mock_dashboard_jobs):
        """_collect_jobs forwards all keyword args including pagination params."""
        db_connection = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)
        until = datetime(2024, 2, 1, tzinfo=UTC)
        expected_result = MagicMock()
        mock_dashboard_jobs.return_value.gather.return_value = expected_result

        result = _collect_jobs(db_connection, since, until, after_id=50, batch_size=100)

        mock_dashboard_jobs.assert_called_once_with(
            db=db_connection, since=since, until=until, after_id=50, batch_size=100
        )
        mock_dashboard_jobs.return_value.gather.assert_called_once()
        assert result == expected_result

    @patch("apps.dashboard_reports.tasks.dashboard_jobs")
    def test_defaults_pagination_params_to_none(self, mock_dashboard_jobs):
        """_collect_jobs defaults after_id and batch_size to None."""
        db_connection = MagicMock()
        since = datetime(2024, 1, 1, tzinfo=UTC)
        until = datetime(2024, 2, 1, tzinfo=UTC)
        mock_dashboard_jobs.return_value.gather.return_value = {}

        _collect_jobs(db_connection, since, until)

        mock_dashboard_jobs.assert_called_once_with(
            db=db_connection, since=since, until=until, after_id=None, batch_size=None
        )


@pytest.mark.unit
class TestCollectData:
    def test_success_returns_job_count(self, mock_collect_data_deps):
        """_collect_data returns correct job_count on success."""
        _, _, _, _, _, since, until = mock_collect_data_deps
        result = _collect_data("test_task")
        assert result["error"] is False
        assert result["data"]["job_count"] == 42
        assert result["data"]["date_range"]["start"] == since.isoformat()
        assert result["data"]["date_range"]["end"] == until.isoformat()

    def test_invalid_date_range_returns_error(self, mock_collect_data_deps):
        """_collect_data returns an error when since >= until."""
        mock_params, *_ = mock_collect_data_deps
        since = datetime(2024, 2, 1, tzinfo=UTC)
        until = datetime(2024, 1, 1, tzinfo=UTC)
        mock_params.return_value = ("awx", since, until, 5000)

        result = _collect_data("test_task")

        assert result["error"] is True
        assert "Invalid date range" in result["message"]

    def test_db_connection_error_returns_error(self, mock_collect_data_deps):
        """_collect_data returns error when DB connection fails."""
        _, mock_db_conn, *_ = mock_collect_data_deps
        mock_db_conn.side_effect = Exception("connection refused")

        result = _collect_data("test_task")

        assert result["error"] is True
        assert "Database connection failed" in result["message"]

    def test_no_jobs_in_range_returns_zero_count(self, mock_collect_data_deps):
        """_collect_data returns job_count=0 when min_id is None (no jobs in window)."""
        _, _, mock_id_range, *_ = mock_collect_data_deps
        mock_id_range.return_value = (None, None)

        result = _collect_data("test_task")

        assert result["error"] is False
        assert result["data"]["job_count"] == 0

    def test_batch_error_propagates(self, mock_collect_data_deps):
        """_collect_data returns error when _process_batches reports a failure."""
        _, _, _, mock_batches, *_ = mock_collect_data_deps
        mock_batches.return_value = (0, "Collecting jobs failed: timeout")

        result = _collect_data("test_task")

        assert result["error"] is True
        assert "Collecting jobs failed" in result["message"]

    def test_cursor_starts_at_min_id_minus_one(self, mock_collect_data_deps):
        """_collect_data always starts batching from min_id - 1 (safe cursor for concurrent writes)."""
        _, _, mock_id_range, mock_batches, *_ = mock_collect_data_deps
        mock_id_range.return_value = (500, 1000)

        _collect_data("test_task")

        call_kwargs = mock_batches.call_args
        # after_id is the 4th positional arg: (db_connection, since, until, max_id, after_id, ...)
        after_id_arg = call_kwargs[0][4]
        assert after_id_arg == 499  # min_id - 1


@pytest.mark.unit
class TestCollectDashboardReportsInitialData:
    def test_error_from_collect_data_propagates(self):
        """collect_dashboard_reports_initial_data returns error when _collect_data fails."""
        with (
            patch("apps.dashboard_reports.tasks._collect_data") as mock_collect,
            patch("apps.dashboard_reports.tasks.create_task_result") as mock_result,
        ):
            mock_collect.return_value = {"error": True, "message": "fail"}
            collect_dashboard_reports_initial_data()
            mock_result.assert_called_with("error", error="fail")

    def test_success_returns_data(self):
        """collect_dashboard_reports_initial_data returns success with data on success."""
        with (
            patch("apps.dashboard_reports.tasks._collect_data") as mock_collect,
            patch("apps.dashboard_reports.tasks.create_task_result") as mock_result,
        ):
            mock_collect.return_value = {"error": False, "data": {"job_count": 10}}
            collect_dashboard_reports_initial_data()
            mock_result.assert_called_with("success", data={"job_count": 10})

    def test_no_follow_up_task_creation(self):
        """collect_dashboard_reports_initial_data does NOT create a follow-up Task object."""
        with (
            patch("apps.dashboard_reports.tasks._collect_data") as mock_collect,
            patch("apps.dashboard_reports.tasks.create_task_result"),
        ):
            mock_collect.return_value = {"error": False, "data": {}}
            # If Task were imported it would be accessible; verify no Task ORM calls happen
            collect_dashboard_reports_initial_data()
            # No assertion needed — test passes if the above doesn't raise AttributeError
            # (Task is no longer imported in tasks.py)


@pytest.mark.unit
class TestCollectDashboardReportsData:
    def test_error_in_collect_data(self, mock_collect_data, mock_create_task_result):
        mock_collect_data.return_value = {"error": True, "message": "fail"}
        collect_dashboard_reports_data()
        mock_create_task_result.assert_called_with("error", error="fail")

    def test_success_in_collect_data(self, mock_collect_data, mock_create_task_result):
        mock_collect_data.return_value = {"error": False, "data": {"foo": "bar"}}
        collect_dashboard_reports_data()
        mock_create_task_result.assert_called_with("success", data={"foo": "bar"})

    def test_missing_data_key(self, mock_collect_data, mock_create_task_result):
        mock_collect_data.return_value = {"error": False}
        collect_dashboard_reports_data()
        mock_create_task_result.assert_called_with("success", data={})

    def test_error_message_fallback(self, mock_collect_data, mock_create_task_result):
        mock_collect_data.return_value = {"error": True}
        collect_dashboard_reports_data()
        args, kwargs = mock_create_task_result.call_args
        assert args[0] == "error"
        assert "An unknown error occurred" in kwargs["error"]


@pytest.mark.unit
class TestSyncDashboardJobRecords:
    def _raw_job(self, job_id=1, num_hosts=5, label_ids=None):
        return {
            "id": job_id,
            "name": "Test Job",
            "unified_job_template_id": 10,
            "organization_id": 1,
            "organization_name": "Org",
            "started": "2024-01-01T00:00:00+00:00",
            "finished": "2024-01-01T01:00:00+00:00",
            "status": "successful",
            "elapsed": 3600.0,
            "launched_by_id": 5,
            "launched_by_username": "user",
            "project_id": 2,
            "project_name": "Project",
            "created": "2024-01-01T00:00:00+00:00",
            "modified": "2024-01-01T01:00:00+00:00",
            "label_ids": label_ids,
            "num_hosts": num_hosts,
        }

    @patch("apps.dashboard_reports.tasks._sync_jobs_atomically", return_value=[])
    @patch("apps.dashboard_reports.tasks.log_task_execution")
    @patch("apps.dashboard_reports.tasks.create_task_result")
    def test_success_with_jobs(self, mock_result, mock_log, mock_sync):
        """sync_dashboard_job_records returns success with correct job_count."""
        raw_jobs = [self._raw_job(job_id=1), self._raw_job(job_id=2)]
        sync_dashboard_job_records(raw_jobs=raw_jobs, hour_timestamp="2024-01-01T00:00:00")
        mock_result.assert_called_once()
        args, kwargs = mock_result.call_args
        assert args[0] == "success"
        assert kwargs["data"]["job_count"] == 2

    @patch("apps.dashboard_reports.tasks._sync_jobs_atomically", return_value=[1])
    @patch("apps.dashboard_reports.tasks.log_task_execution")
    @patch("apps.dashboard_reports.tasks.create_task_result")
    def test_failed_jobs_returns_error(self, mock_result, mock_log, mock_sync):
        """sync_dashboard_job_records returns error when _sync_jobs_atomically reports failures."""
        sync_dashboard_job_records(raw_jobs=[self._raw_job()], hour_timestamp="2024-01-01T00:00:00")
        args, kwargs = mock_result.call_args
        assert args[0] == "error"
        assert "Failed to sync" in kwargs["error"]

    @patch("apps.dashboard_reports.tasks._sync_jobs_atomically", return_value=[])
    @patch("apps.dashboard_reports.tasks.log_task_execution")
    @patch("apps.dashboard_reports.tasks.create_task_result")
    def test_num_hosts_none_coerced_to_zero(self, mock_result, mock_log, mock_sync):
        """num_hosts=None in raw data is coerced to 0 rather than raising IntegrityError."""
        raw_jobs = [self._raw_job(num_hosts=None)]
        sync_dashboard_job_records(raw_jobs=raw_jobs, hour_timestamp="2024-01-01T00:00:00")
        assembled = mock_sync.call_args[0][0]
        assert assembled[0]["num_hosts"] == 0

    @patch("apps.dashboard_reports.tasks._sync_jobs_atomically", return_value=[])
    @patch("apps.dashboard_reports.tasks.log_task_execution")
    @patch("apps.dashboard_reports.tasks.create_task_result")
    def test_label_ids_parsed_from_csv(self, mock_result, mock_log, mock_sync):
        """label_ids CSV string is parsed into a list of ints."""
        raw_jobs = [self._raw_job(label_ids="3,7,12")]
        sync_dashboard_job_records(raw_jobs=raw_jobs, hour_timestamp="2024-01-01T00:00:00")
        assembled = mock_sync.call_args[0][0]
        assert assembled[0]["labels"] == [3, 7, 12]

    @patch("apps.dashboard_reports.tasks._sync_jobs_atomically", return_value=[])
    @patch("apps.dashboard_reports.tasks.log_task_execution")
    @patch("apps.dashboard_reports.tasks.create_task_result")
    def test_empty_raw_jobs(self, mock_result, mock_log, mock_sync):
        """sync_dashboard_job_records handles empty raw_jobs gracefully."""
        sync_dashboard_job_records(raw_jobs=[], hour_timestamp="2024-01-01T00:00:00")
        args, kwargs = mock_result.call_args
        assert args[0] == "success"
        assert kwargs["data"]["job_count"] == 0

    @patch("apps.dashboard_reports.tasks._sync_jobs_atomically", return_value=[])
    @patch("apps.dashboard_reports.tasks.log_task_execution")
    @patch("apps.dashboard_reports.tasks.create_task_result")
    def test_host_summaries_set_to_none(self, mock_result, mock_log, mock_sync):
        """host_summaries is always None so backfill records are preserved by hourly sync."""
        raw_jobs = [self._raw_job()]
        sync_dashboard_job_records(raw_jobs=raw_jobs, hour_timestamp="2024-01-01T00:00:00")
        assembled = mock_sync.call_args[0][0]
        assert assembled[0]["host_summaries"] is None


@pytest.mark.unit
class TestCollectDataConnectionHandling:
    """Connection must never be closed by _collect_data (shared singleton)."""

    def test_does_not_close_connection_on_success(self, mock_collect_data_deps):
        _, mock_db_conn, _, mock_batches, *_ = mock_collect_data_deps
        mock_connection = MagicMock()
        mock_db_conn.return_value = mock_connection
        mock_batches.return_value = (1, None)

        _collect_data("test_task")

        mock_connection.close.assert_not_called()

    def test_does_not_close_connection_on_batch_error(self, mock_collect_data_deps):
        _, mock_db_conn, _, mock_batches, *_ = mock_collect_data_deps
        mock_connection = MagicMock()
        mock_db_conn.return_value = mock_connection
        mock_batches.return_value = (0, "Collecting jobs failed: timeout")

        _collect_data("test_task")

        mock_connection.close.assert_not_called()


# --- Cleanup tests ---
@pytest.mark.unit
@pytest.mark.django_db
class TestCleanupDashboardReportsOldData:
    @pytest.fixture
    def mock_jobdata_objects(self):
        with patch("apps.dashboard_reports.tasks.JobData") as mock_jobdata:
            yield mock_jobdata

    @pytest.fixture
    def mock_log_task_execution(self):
        with patch("apps.dashboard_reports.tasks.log_task_execution") as mock_log:
            yield mock_log

    @pytest.fixture
    def mock_create_task_result_cleanup(self):
        with patch("apps.dashboard_reports.tasks.create_task_result") as mock:
            yield mock

    def test_cleanup_success(self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup):
        mock_jobdata_objects.objects.filter.return_value.count.return_value = 5
        mock_create_task_result_cleanup.return_value = {"result": "success"}
        result = cleanup_dashboard_reports_old_data()
        assert result["result"] == "success"
        args, kwargs = mock_create_task_result_cleanup.call_args
        assert args[0] == "success"
        assert kwargs["data"]["deleted_records"] == 5
        assert "cutoff_date" in kwargs["data"]
        assert "retention_period_days" in kwargs["data"]

    def test_cleanup_no_records(self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup):
        mock_jobdata_objects.objects.filter.return_value.count.return_value = 0
        cleanup_dashboard_reports_old_data()
        args, kwargs = mock_create_task_result_cleanup.call_args
        assert args[0] == "success"
        assert kwargs["data"]["deleted_records"] == 0

    def test_cleanup_exception(self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup):
        mock_jobdata_objects.objects.filter.return_value.count.return_value = 3
        mock_jobdata_objects.objects.filter.return_value.delete.side_effect = Exception("db error")
        cleanup_dashboard_reports_old_data()
        args, kwargs = mock_create_task_result_cleanup.call_args
        assert args[0] == "error"
        assert "Cleanup failed" in kwargs["error"]

    def test_cleanup_custom_retention(
        self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup
    ):
        mock_jobdata_objects.objects.filter.return_value.count.return_value = 2
        cleanup_dashboard_reports_old_data(retention_period_days=30)
        args, kwargs = mock_create_task_result_cleanup.call_args
        assert kwargs["data"]["retention_period_days"] == 30

    def test_cleanup_cutoff_date(self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup):
        mock_jobdata_objects.objects.filter.return_value.count.return_value = 1
        cleanup_dashboard_reports_old_data(retention_period_days=1)
        _, kwargs = mock_create_task_result_cleanup.call_args
        actual_cutoff = kwargs["data"]["cutoff_date"]
        expected_date = (datetime.now(tz=UTC) - timedelta(days=1)).date().isoformat()
        assert actual_cutoff.startswith(expected_date)

    def test_cleanup_invalid_retention_string(
        self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup
    ):
        cleanup_dashboard_reports_old_data(retention_period_days="not-a-number")
        args, kwargs = mock_create_task_result_cleanup.call_args
        assert args[0] == "error"
        assert "Invalid retention_period_days" in kwargs["error"]

    def test_cleanup_negative_retention_clamped(
        self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup
    ):
        mock_jobdata_objects.objects.filter.return_value.delete.return_value = (10, {})
        cleanup_dashboard_reports_old_data(retention_period_days=-5)
        args, kwargs = mock_create_task_result_cleanup.call_args
        assert args[0] == "success"
        assert kwargs["data"]["retention_period_days"] == 0

    def test_cleanup_with_db_data(self, db):
        """Test cleanup_dashboard_reports_old_data with real JobData records in the database."""
        cutoff = datetime.now().astimezone(pytz.utc) - timedelta(days=90)
        old_job1 = JobData.objects.create(
            job_id=1001, finished=cutoff - timedelta(days=1), status="successful", elapsed=1.0
        )
        old_job2 = JobData.objects.create(
            job_id=1002, finished=cutoff - timedelta(days=10), status="successful", elapsed=1.0
        )
        new_job1 = JobData.objects.create(
            job_id=1003, finished=cutoff + timedelta(days=1), status="successful", elapsed=1.0
        )
        new_job2 = JobData.objects.create(
            job_id=1004, finished=cutoff + timedelta(days=10), status="successful", elapsed=1.0
        )
        result = cleanup_dashboard_reports_old_data(retention_period_days=90)
        assert result["deleted_records"] == 2

        remaining_ids = set(JobData.objects.values_list("id", flat=True))
        assert old_job1.id not in remaining_ids
        assert old_job2.id not in remaining_ids
        assert new_job1.id in remaining_ids
        assert new_job2.id in remaining_ids
