# test_tasks.py - Unit tests for dashboard_reports tasks
# Covers: _collect_jobs, _collect_data, collect_dashboard_reports_initial_data, collect_dashboard_reports_data

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytz

from apps.dashboard_reports.models import JobData
from apps.dashboard_reports.tasks import (
    _collect_data,
    _collect_jobs,
    cleanup_dashboard_reports_old_data,
    collect_dashboard_reports_data,
    collect_dashboard_reports_initial_data,
)


# --- Fixtures for dependency mocking ---
@pytest.fixture
def mock_collect_data():
    # Patch _collect_data for dashboard_reports tasks
    with patch("apps.dashboard_reports.tasks._collect_data") as mock_collect_data:
        yield mock_collect_data


@pytest.fixture
def mock_create_task_result():
    # Patch create_task_result for dashboard_reports tasks
    with patch("apps.dashboard_reports.tasks.create_task_result") as mock_create_task_result:
        yield mock_create_task_result


@pytest.fixture
def mock_dependencies():
    # Patch all dependencies for _collect_data tests
    with (
        patch("apps.dashboard_reports.tasks.get_db_connection") as mock_db_conn,
        patch("apps.dashboard_reports.tasks.JobData") as mock_job_data,
        patch("apps.dashboard_reports.tasks.dashboard_jobs") as mock_dashboard_jobs,
        patch("apps.dashboard_reports.tasks.log_task_execution") as mock_log_task,
    ):
        yield mock_db_conn, mock_job_data, mock_dashboard_jobs, mock_log_task


@pytest.fixture
def mock_task_dependencies():
    # Patch dependencies for initial data task creation
    with (
        patch("apps.dashboard_reports.tasks._collect_data") as mock_collect_data,
        patch("apps.dashboard_reports.tasks.create_task_result") as mock_create_task_result,
        patch("apps.dashboard_reports.tasks.log_task_execution") as mock_log_task,
        patch("apps.dashboard_reports.tasks.Task") as mock_task,
        patch("apps.dashboard_reports.tasks.DASHBOARD_COLLECTION_GROUP") as mock_group,
    ):
        yield mock_collect_data, mock_create_task_result, mock_log_task, mock_task, mock_group


# --- Helper for repeated _collect_data setup ---
def setup_collect_data_mocks(mock_job_data, mock_dashboard_jobs, jobs_result=None, gather_exc=None, update_exc=None):
    """Configure mocks for _collect_data scenarios."""
    mock_job_data.last_timestamp.return_value = None
    if gather_exc:
        mock_dashboard_jobs.return_value.gather.side_effect = gather_exc
    elif jobs_result:
        mock_dashboard_jobs.return_value.gather.return_value = jobs_result
    if update_exc:
        mock_job_data.create_or_update_from_awx.side_effect = update_exc
    elif jobs_result:
        mock_job_data.create_or_update_from_awx.return_value = None


@pytest.mark.unit
@pytest.mark.django_db
class TestDashboardReportsTasks:
    # --- _collect_jobs tests ---
    @patch("apps.dashboard_reports.tasks.dashboard_jobs")
    def test__collect_jobs(self, mock_dashboard_jobs):
        """Test that _collect_jobs calls dashboard_jobs with correct args and returns result."""
        db_connection = MagicMock()
        since = datetime(2024, 1, 1)
        until = datetime(2024, 2, 1)
        expected_result = MagicMock()
        mock_dashboard_jobs.return_value = expected_result
        result = _collect_jobs(db_connection, since, until)
        mock_dashboard_jobs.assert_called_once_with(db=db_connection, since=since, until=until)
        assert result == expected_result

    # --- _collect_data tests ---
    @pytest.mark.parametrize(
        "since,until,jobs_result,error,message",
        [
            (None, None, {"results": [{"id": 1}], "count": 1}, False, None),
            (datetime(2024, 1, 1), datetime(2024, 2, 1), {"results": [{"id": 2}], "count": 1}, False, None),
            (datetime(2024, 2, 1), datetime(2024, 1, 1), None, True, "Invalid date range"),
        ],
    )
    def test_collect_data_ranges(self, mock_dependencies, since, until, jobs_result, error, message):
        """Test _collect_data for default, custom, and invalid date ranges."""
        mock_db_conn, mock_job_data, mock_dashboard_jobs, mock_log_task = mock_dependencies
        setup_collect_data_mocks(mock_job_data, mock_dashboard_jobs, jobs_result)
        args = {"since": since, "until": until} if since and until else {}
        result = _collect_data("test_task", **args)
        assert result["error"] is error
        if not error:
            assert result["data"]["job_count"] == jobs_result["count"]
            if since and until:
                assert result["data"]["date_range"]["start"] == since.isoformat()
                assert result["data"]["date_range"]["end"] == until.isoformat()
        else:
            assert message in result["message"]

    def test_collect_data_gather_exception(self, mock_dependencies):
        """Test _collect_data handles exception in dashboard_jobs.gather."""
        mock_db_conn, mock_job_data, mock_dashboard_jobs, mock_log_task = mock_dependencies
        setup_collect_data_mocks(mock_job_data, mock_dashboard_jobs, gather_exc=Exception("gather failed"))
        result = _collect_data("test_task")
        assert result["error"] is True
        assert "Collecting jobs failed" in result["message"]

    def test_collect_data_create_update_exception(self, mock_dependencies):
        """Test _collect_data handles exception in JobData.create_or_update_from_awx."""
        mock_db_conn, mock_job_data, mock_dashboard_jobs, mock_log_task = mock_dependencies
        setup_collect_data_mocks(
            mock_job_data,
            mock_dashboard_jobs,
            jobs_result={"results": [{"id": 3}], "count": 1},
            update_exc=Exception("update failed"),
        )
        result = _collect_data("test_task")
        assert result["error"] is True
        assert "Failed to sync 1 job(s)" in result["message"]
        assert "3" in result["message"]

    # --- collect_dashboard_reports_initial_data tests ---
    def setup_initial_task(
        self, mock_collect_data, mock_group, mock_task, collect_data_result, group_tasks, task_count, create_exc=None
    ):
        """Configure mocks for initial data task creation scenarios."""
        mock_collect_data.return_value = collect_data_result
        mock_group.tasks = group_tasks
        mock_task.objects.filter.return_value.count.return_value = task_count
        if create_exc:
            mock_task.objects.create.side_effect = create_exc
        elif task_count == 0 and group_tasks:
            mock_task.objects.create.return_value = MagicMock()

    def test_initial_data_error(self, mock_task_dependencies):
        """Test error result from initial data collection."""
        mock_collect_data, mock_create_task_result, _, mock_task, mock_group = mock_task_dependencies
        self.setup_initial_task(mock_collect_data, mock_group, mock_task, {"error": True, "message": "fail"}, [], 0)
        collect_dashboard_reports_initial_data()
        mock_create_task_result.assert_called_with("error", error="fail")

    def test_initial_data_no_daily_task(self, mock_task_dependencies):
        """Test no daily_dashboard_collection task found in group."""
        mock_collect_data, mock_create_task_result, _, mock_task, mock_group = mock_task_dependencies
        self.setup_initial_task(mock_collect_data, mock_group, mock_task, {"error": False, "data": {}}, [], 0)
        collect_dashboard_reports_initial_data()
        mock_create_task_result.assert_called_with(
            "error", error="No task with task_id 'daily_dashboard_collection' found in DASHBOARD_COLLECTION_GROUP"
        )

    def test_initial_data_task_exists(self, mock_task_dependencies):
        """Test follow-up task already exists scenario."""
        mock_collect_data, mock_create_task_result, _, mock_task, mock_group = mock_task_dependencies
        group_tasks = [
            {
                "task_id": "daily_dashboard_collection",
                "args": {},
                "function": "func",
                "description": "",
                "cron": "0 */6 * * *",
            }
        ]
        self.setup_initial_task(mock_collect_data, mock_group, mock_task, {"error": False, "data": {}}, group_tasks, 1)
        collect_dashboard_reports_initial_data()
        assert mock_create_task_result.call_args[0][0] == "success"
        assert mock_create_task_result.call_args[1]["data"]["Follow-up task creation"] == "skipped"

    def test_initial_data_create_success(self, mock_task_dependencies):
        """Test successful follow-up task creation scenario."""
        mock_collect_data, mock_create_task_result, _, mock_task, mock_group = mock_task_dependencies
        group_tasks = [
            {
                "task_id": "daily_dashboard_collection",
                "args": {},
                "function": "func",
                "description": "",
                "cron": "0 */6 * * *",
            }
        ]
        self.setup_initial_task(mock_collect_data, mock_group, mock_task, {"error": False, "data": {}}, group_tasks, 0)
        collect_dashboard_reports_initial_data()
        assert mock_create_task_result.call_args[0][0] == "success"
        assert mock_create_task_result.call_args[1]["data"]["Follow-up task creation"] == "success"

    def test_initial_data_create_exception(self, mock_task_dependencies):
        """Test exception during follow-up task creation."""
        mock_collect_data, mock_create_task_result, _, mock_task, mock_group = mock_task_dependencies
        group_tasks = [
            {
                "task_id": "daily_dashboard_collection",
                "args": {},
                "function": "func",
                "description": "",
                "cron": "0 */6 * * *",
            }
        ]
        self.setup_initial_task(
            mock_collect_data,
            mock_group,
            mock_task,
            {"error": False, "data": {}},
            group_tasks,
            0,
            create_exc=Exception("fail"),
        )
        collect_dashboard_reports_initial_data()
        assert mock_create_task_result.call_args[0][0] == "error"
        assert "Creating follow-up task failed" in mock_create_task_result.call_args[1]["error"]

    # --- collect_dashboard_reports_data tests ---
    def test_error_in_collect_data(self, mock_collect_data, mock_create_task_result):
        """Test error result from collect_dashboard_reports_data."""
        mock_collect_data.return_value = {"error": True, "message": "fail"}
        collect_dashboard_reports_data()
        mock_create_task_result.assert_called_with("error", error="fail")

    def test_success_in_collect_data(self, mock_collect_data, mock_create_task_result):
        """Test success result from collect_dashboard_reports_data."""
        mock_collect_data.return_value = {"error": False, "data": {"foo": "bar"}}
        collect_dashboard_reports_data()
        mock_create_task_result.assert_called_with("success", data={"foo": "bar"})

    def test_missing_data_in_collect_data(self, mock_collect_data, mock_create_task_result):
        """Test missing data key in collect_dashboard_reports_data result."""
        mock_collect_data.return_value = {"error": False}
        collect_dashboard_reports_data()
        mock_create_task_result.assert_called_with("success", data={})

    def test_error_message_fallback(self, mock_collect_data, mock_create_task_result):
        """Test fallback error message in collect_dashboard_reports_data."""
        mock_collect_data.return_value = {"error": True}
        collect_dashboard_reports_data()
        args, kwargs = mock_create_task_result.call_args
        assert args[0] == "error"
        assert "An unknown error occurred" in kwargs["error"]

    # --- cleanup_dashboard_reports_old_data tests ---
    @pytest.fixture
    def mock_jobdata_objects(self):
        with patch("apps.dashboard_reports.tasks.JobData") as mock_jobdata:
            yield mock_jobdata

    @pytest.fixture
    def mock_log_task_execution(self):
        with patch("apps.dashboard_reports.tasks.log_task_execution") as mock_log_task_execution:
            yield mock_log_task_execution

    @pytest.fixture
    def mock_create_task_result_cleanup(self):
        with patch("apps.dashboard_reports.tasks.create_task_result") as mock_create_task_result:
            yield mock_create_task_result

    def test_cleanup_success(self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup):
        # Simulate successful deletion of records
        mock_jobdata_objects.objects.filter.return_value.delete.return_value = (5, {})
        mock_create_task_result_cleanup.return_value = {"result": "success"}
        result = cleanup_dashboard_reports_old_data()
        assert result["result"] == "success"
        args, kwargs = mock_create_task_result_cleanup.call_args
        assert args[0] == "success"
        assert kwargs["data"]["deleted_records"] == 5
        assert "cutoff_date" in kwargs["data"]
        assert "retention_period_days" in kwargs["data"]

    def test_cleanup_no_records(self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup):
        # Simulate no records deleted
        mock_jobdata_objects.objects.filter.return_value.delete.return_value = (0, {})
        cleanup_dashboard_reports_old_data()
        args, kwargs = mock_create_task_result_cleanup.call_args
        assert args[0] == "success"
        assert kwargs["data"]["deleted_records"] == 0

    def test_cleanup_exception(self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup):
        # Simulate exception during deletion
        mock_jobdata_objects.objects.filter.return_value.delete.side_effect = Exception("db error")
        cleanup_dashboard_reports_old_data()
        args, kwargs = mock_create_task_result_cleanup.call_args
        assert args[0] == "error"
        assert "Cleanup failed" in kwargs["error"]

    def test_cleanup_custom_retention(
        self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup
    ):
        # Test custom retention_period_days
        mock_jobdata_objects.objects.filter.return_value.delete.return_value = (2, {})
        cleanup_dashboard_reports_old_data(retention_period_days=30)
        args, kwargs = mock_create_task_result_cleanup.call_args
        assert kwargs["data"]["retention_period_days"] == 30

    def test_cleanup_cutoff_date(self, mock_jobdata_objects, mock_log_task_execution, mock_create_task_result_cleanup):
        # Test cutoff_date calculation
        mock_jobdata_objects.objects.filter.return_value.delete.return_value = (1, {})
        result = cleanup_dashboard_reports_old_data(retention_period_days=1)
        cutoff_date = result["data"]["cutoff_date"]
        assert cutoff_date.startswith(str(datetime.now().year))

    def test_cleanup_with_db_data(self, db):
        """Test cleanup_dashboard_reports_old_data with real JobData records in the database."""

        # Create 2 old and 2 recent records
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
        # Run cleanup
        result = cleanup_dashboard_reports_old_data(retention_period_days=90)
        # Only old_job1 and old_job2 should be deleted
        assert result["deleted_records"] == 2

        remaining_ids = set(JobData.objects.values_list("id", flat=True))
        assert old_job1.id not in remaining_ids
        assert old_job2.id not in remaining_ids
        assert new_job1.id in remaining_ids
        assert new_job2.id in remaining_ids
