# test_sync_dashboard_on_demand.py - Unit tests for the manual dashboard sync task

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from apps.dashboard_reports.tasks import _on_demand_windows, sync_dashboard_on_demand

MODULE = "apps.dashboard_reports.tasks"
SINCE = datetime(2024, 1, 1, tzinfo=UTC)
UNTIL = datetime(2024, 1, 2, tzinfo=UTC)
COLLECTORS = "metrics_utility.library.collectors.controller"
HOURLY = "apps.tasks.collectors.collect_hourly_metrics"


def _ok(**data):
    return {"status": "success", **data}


@pytest.fixture
def mocks():
    """Patch collectors, helpers, DB access, and both sync writers."""
    with (
        patch(f"{MODULE}.get_db_connection") as db,
        patch(f"{COLLECTORS}.unified_jobs_dashboard") as jobs_collector,
        patch(f"{COLLECTORS}.job_host_summary_service") as hs_collector,
        patch(f"{HOURLY}._build_dashboard_job_records", return_value=[{"id": 1}]) as build_jobs,
        patch(f"{HOURLY}._build_host_summary_by_job", return_value={1: [{"id": 9, "job_remote_id": 1}]}) as build_hs,
        patch(f"{MODULE}.sync_dashboard_job_records", return_value=_ok(job_count=1)) as sync_jobs,
        patch(f"{MODULE}.sync_dashboard_host_summaries", return_value=_ok(job_count=1)) as sync_hs,
        patch(f"{MODULE}._save_telemetry_details") as telemetry,
        patch(f"{MODULE}.JobData.last_finished_timestamp", return_value=SINCE),
    ):
        yield MagicMock(
            db=db,
            jobs_collector=jobs_collector,
            hs_collector=hs_collector,
            build_jobs=build_jobs,
            build_hs=build_hs,
            sync_jobs=sync_jobs,
            sync_hs=sync_hs,
            telemetry=telemetry,
        )


@pytest.mark.unit
class TestOnDemandWindows:
    def test_single_window_when_range_within_one_day(self):
        assert list(_on_demand_windows(SINCE, SINCE + timedelta(hours=5))) == [(SINCE, SINCE + timedelta(hours=5))]

    def test_splits_into_daily_windows(self):
        windows = list(_on_demand_windows(SINCE, SINCE + timedelta(days=2, hours=3)))
        assert len(windows) == 3
        assert windows[0] == (SINCE, SINCE + timedelta(days=1))
        assert windows[-1][1] == SINCE + timedelta(days=2, hours=3)


@pytest.mark.unit
class TestSyncDashboardOnDemand:
    def test_explicit_range_runs_both_paths(self, mocks):
        result = sync_dashboard_on_demand(since=SINCE.isoformat(), until=UNTIL.isoformat())

        assert result["status"] == "success"
        assert result["date_range"] == {"start": SINCE.isoformat(), "end": UNTIL.isoformat()}
        assert result["job_count"] == 1
        assert result["host_summary_job_count"] == 1
        mocks.jobs_collector.assert_called_once()
        assert mocks.jobs_collector.call_args.kwargs["since"] == SINCE
        assert mocks.jobs_collector.call_args.kwargs["until"] == UNTIL
        mocks.hs_collector.assert_called_once()
        mocks.sync_jobs.assert_called_once_with(raw_jobs=[{"id": 1}], hour_timestamp=SINCE.isoformat())
        mocks.sync_hs.assert_called_once_with(
            raw_host_summaries=[{"id": 9, "job_remote_id": 1}], hour_timestamp=SINCE.isoformat()
        )
        assert mocks.telemetry.call_args.kwargs["success"] is True

    def test_default_window_uses_watermark_until_now(self, mocks):
        result = sync_dashboard_on_demand()

        assert result["status"] == "success"
        assert result["date_range"]["start"] == SINCE.isoformat()
        assert datetime.fromisoformat(result["date_range"]["end"]) > SINCE

    def test_multi_day_range_syncs_each_window(self, mocks):
        until = SINCE + timedelta(days=3)

        result = sync_dashboard_on_demand(since=SINCE.isoformat(), until=until.isoformat())

        assert result["status"] == "success"
        assert mocks.sync_jobs.call_count == 3
        assert mocks.sync_hs.call_count == 3
        assert result["job_count"] == 3

    def test_rerun_is_repeatable(self, mocks):
        first = sync_dashboard_on_demand(since=SINCE.isoformat(), until=UNTIL.isoformat())
        second = sync_dashboard_on_demand(since=SINCE.isoformat(), until=UNTIL.isoformat())

        assert first["status"] == second["status"] == "success"
        assert first["job_count"] == second["job_count"]

    def test_empty_window_skips_writers(self, mocks):
        mocks.build_jobs.return_value = []
        mocks.build_hs.return_value = {}

        result = sync_dashboard_on_demand(since=SINCE.isoformat(), until=UNTIL.isoformat())

        assert result["status"] == "success"
        assert result["job_count"] == 0
        mocks.sync_jobs.assert_not_called()
        mocks.sync_hs.assert_not_called()

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"since": UNTIL.isoformat(), "until": SINCE.isoformat()},
            {"since": SINCE.isoformat(), "until": SINCE.isoformat()},
            {"since": "not-a-date"},
            {"until": 123},
        ],
    )
    def test_invalid_range_returns_error(self, mocks, kwargs):
        result = sync_dashboard_on_demand(**kwargs)

        assert result["status"] == "error"
        assert result["error"]
        mocks.jobs_collector.assert_not_called()

    def test_job_sync_failure_skips_host_summaries(self, mocks):
        mocks.sync_jobs.return_value = {"status": "error", "error": "Failed to sync 1 job(s): [1]"}

        result = sync_dashboard_on_demand(since=SINCE.isoformat(), until=UNTIL.isoformat())

        assert result["status"] == "error"
        assert "sync_dashboard_job_records failed" in result["error"]
        mocks.sync_hs.assert_not_called()
        assert mocks.telemetry.call_args.kwargs["success"] is False

    def test_host_summary_failure_is_not_reported_as_success(self, mocks):
        mocks.sync_hs.return_value = {"status": "error", "job_count": 0, "failed": 2}

        result = sync_dashboard_on_demand(since=SINCE.isoformat(), until=UNTIL.isoformat())

        assert result["status"] == "error"
        assert "2 job(s) failed" in result["error"]
        assert result["job_count"] == 1

    def test_failure_stops_remaining_windows(self, mocks):
        mocks.sync_jobs.return_value = {"status": "error", "error": "boom"}
        until = SINCE + timedelta(days=3)

        result = sync_dashboard_on_demand(since=SINCE.isoformat(), until=until.isoformat())

        assert result["status"] == "error"
        assert mocks.sync_jobs.call_count == 1

    def test_collector_exception_returns_error(self, mocks):
        mocks.jobs_collector.return_value.gather.side_effect = RuntimeError("db down")

        result = sync_dashboard_on_demand(since=SINCE.isoformat(), until=UNTIL.isoformat())

        assert result["status"] == "error"
        assert "Collection failed" in result["error"]
        mocks.sync_jobs.assert_not_called()

    def test_db_connection_error_returns_error(self, mocks):
        mocks.db.side_effect = RuntimeError("no connection")

        result = sync_dashboard_on_demand(since=SINCE.isoformat(), until=UNTIL.isoformat())

        assert result["status"] == "error"
        assert "Database error" in result["error"]
