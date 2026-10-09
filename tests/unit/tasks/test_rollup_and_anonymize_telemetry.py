"""Unit tests for dashboard telemetry integration in daily_metrics_rollup
and daily_anonymize_and_prepare collectors."""

import decimal
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _aggregate_dashboard_telemetry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAggregateDashboardTelemetry:
    """Tests for the _aggregate_dashboard_telemetry helper in daily_metrics_rollup."""

    def test_returns_rows_for_given_date(self):
        """Returns a list of dicts with the expected keys for matching rows."""
        mock_row = MagicMock()
        mock_row.task_name = "collect_dashboard_reports_initial_data"
        mock_row.collection_duration_ms = decimal.Decimal("1500.00")
        mock_row.number_of_records_processed = 42
        mock_row.database_query_time_ms = decimal.Decimal("200.00")
        mock_row.cache_hit_rate = None

        with patch("apps.tasks.collectors.daily_metrics_rollup.DashboardTelemetry") as mock_model:
            mock_model.objects.filter.return_value = [mock_row]
            from apps.tasks.collectors.daily_metrics_rollup import _aggregate_dashboard_telemetry

            result = _aggregate_dashboard_telemetry(date.today())

        assert len(result) == 1
        entry = result[0]
        assert entry["task_name"] == "collect_dashboard_reports_initial_data"
        assert entry["collection_duration_ms"] == 1500.00
        assert entry["number_of_records_processed"] == 42
        assert entry["database_query_time_ms"] == 200.00
        assert entry["cache_hit_rate"] is None

    def test_returns_empty_list_when_no_rows(self):
        """Returns [] when no telemetry rows exist for the given date."""
        with patch("apps.tasks.collectors.daily_metrics_rollup.DashboardTelemetry") as mock_model:
            mock_model.objects.filter.return_value = []
            from apps.tasks.collectors.daily_metrics_rollup import _aggregate_dashboard_telemetry

            result = _aggregate_dashboard_telemetry(date.today())

        assert result == []

    def test_returns_empty_list_on_exception(self):
        """When DashboardTelemetry query raises an exception, returns [] and logs the error."""
        with (
            patch("apps.tasks.collectors.daily_metrics_rollup.DashboardTelemetry") as mock_model,
            patch("apps.tasks.collectors.daily_metrics_rollup.logger") as mock_logger,
        ):
            mock_model.objects.filter.side_effect = Exception("DB error")
            from apps.tasks.collectors.daily_metrics_rollup import _aggregate_dashboard_telemetry

            result = _aggregate_dashboard_telemetry(date.today())

        assert result == []
        mock_logger.exception.assert_called_once()

    def test_output_contains_no_sensitive_fields(self):
        """The aggregated dict does not expose org names, user ids, or job details."""
        mock_row = MagicMock()
        mock_row.task_name = "task"
        mock_row.collection_duration_ms = decimal.Decimal("100.00")
        mock_row.number_of_records_processed = 1
        mock_row.database_query_time_ms = decimal.Decimal("10.00")
        mock_row.cache_hit_rate = None

        with patch("apps.tasks.collectors.daily_metrics_rollup.DashboardTelemetry") as mock_model:
            mock_model.objects.filter.return_value = [mock_row]
            from apps.tasks.collectors.daily_metrics_rollup import _aggregate_dashboard_telemetry

            result = _aggregate_dashboard_telemetry(date.today())

        entry = result[0]
        sensitive_keys = {"organization_name", "user_id", "username", "job_id", "job_name"}
        assert not sensitive_keys.intersection(entry.keys())

    def test_multiple_rows_are_all_returned(self):
        """All rows for the given date are included in the result list."""

        def make_row(task_name):
            r = MagicMock()
            r.task_name = task_name
            r.collection_duration_ms = decimal.Decimal("100.00")
            r.number_of_records_processed = 0
            r.database_query_time_ms = decimal.Decimal("5.00")
            r.cache_hit_rate = None
            return r

        rows = [make_row("task_a"), make_row("task_b")]

        with patch("apps.tasks.collectors.daily_metrics_rollup.DashboardTelemetry") as mock_model:
            mock_model.objects.filter.return_value = rows
            from apps.tasks.collectors.daily_metrics_rollup import _aggregate_dashboard_telemetry

            result = _aggregate_dashboard_telemetry(date.today())

        assert len(result) == 2
        task_names = {r["task_name"] for r in result}
        assert task_names == {"task_a", "task_b"}


# ---------------------------------------------------------------------------
# daily_metrics_rollup — dashboard_telemetry appended
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
class TestDailyMetricsRollupTelemetry:
    """Tests that daily_metrics_rollup appends dashboard_telemetry to the daily summary."""

    def test_rollup_sets_dashboard_telemetry_key(self):
        """daily_metrics_rollup sets the 'dashboard_telemetry' key on the daily rollup."""
        telemetry_rows = [
            {
                "task_name": "collect_dashboard_reports_initial_data",
                "collection_duration_ms": decimal.Decimal("1000.00"),
                "number_of_records_processed": 5,
                "database_query_time_ms": decimal.Decimal("100.00"),
                "cache_hit_rate": None,
            }
        ]
        with (
            patch(
                "apps.tasks.collectors.daily_metrics_rollup._aggregate_dashboard_telemetry",
                return_value=telemetry_rows,
            ) as mock_aggregate,
            patch(
                "apps.tasks.collectors.daily_metrics_rollup.aggregate_analytics_usage",
                return_value={
                    "controller.config": {"request_count": 5, "duration_ms_total": 60.0, "duration_sample_count": 4}
                },
            ) as mock_usage,
            patch(
                "apps.tasks.collectors.daily_metrics_rollup._previous_analytics_usage_snapshot",
                return_value={
                    "observed_at": "2026-10-08T02:00:00+00:00",
                    "metrics": {
                        "controller.config": {
                            "request_count": 3,
                            "duration_ms_total": 30.0,
                            "duration_sample_count": 2,
                        }
                    },
                },
            ),
            patch(
                "apps.tasks.collectors.daily_metrics_rollup._collect_and_group_hourly_collections"
            ) as mock_collections,
            patch("apps.tasks.collectors.daily_metrics_rollup._merge_hourly_rollups") as mock_merge,
            patch("apps.tasks.collectors.daily_metrics_rollup._save_daily_summary") as mock_save,
            patch("apps.tasks.collectors.daily_metrics_rollup.log_task_execution"),
            patch("apps.tasks.models.HourlyMetricsCollection") as mock_hourly,
            patch("apps.tasks.collectors.daily_metrics_rollup.create_task_result") as mock_result,
        ):
            mock_hourly.objects.filter.return_value.exists.return_value = True
            mock_collections.return_value = ({}, None, None)
            mock_merge.return_value = ({}, [])
            mock_save.return_value = (MagicMock(aggregated_metrics={}), True, 0)
            mock_result.return_value = {"status": "success"}

            from apps.tasks.collectors.daily_metrics_rollup import daily_metrics_rollup

            daily_metrics_rollup()

        # _aggregate_dashboard_telemetry should have been called
        mock_aggregate.assert_called_once()

        # The daily_rollup dict passed to _save_daily_summary should contain dashboard_telemetry
        call_args = mock_save.call_args
        rollup_arg = call_args[0][1]  # second positional arg is the daily_rollup dict
        assert "dashboard_telemetry" in rollup_arg
        assert rollup_arg["dashboard_telemetry"] == telemetry_rows
        mock_usage.assert_called_once_with()
        assert rollup_arg["analytics_usage"] == {
            "controller.config": {"request_count": 2, "duration_ms_total": 30.0, "duration_ms_average": 15.0}
        }
        assert mock_save.call_args.args[6]["metrics"] == {
            "controller.config": {"request_count": 5, "duration_ms_total": 60.0, "duration_sample_count": 4}
        }

    def test_first_usage_scrape_saves_baseline_without_reporting_partial_counts(self):
        cumulative_usage = {
            "controller.config": {"request_count": 5, "duration_ms_total": 60.0, "duration_sample_count": 4}
        }
        with (
            patch(
                "apps.tasks.collectors.daily_metrics_rollup.aggregate_analytics_usage", return_value=cumulative_usage
            ),
            patch("apps.tasks.collectors.daily_metrics_rollup._previous_analytics_usage_snapshot", return_value=None),
            patch(
                "apps.tasks.collectors.daily_metrics_rollup._collect_and_group_hourly_collections"
            ) as mock_collections,
            patch("apps.tasks.collectors.daily_metrics_rollup._merge_hourly_rollups", return_value=({}, [])),
            patch("apps.tasks.collectors.daily_metrics_rollup._aggregate_dashboard_telemetry", return_value=[]),
            patch("apps.tasks.collectors.daily_metrics_rollup._save_daily_summary") as mock_save,
            patch("apps.tasks.collectors.daily_metrics_rollup.log_task_execution"),
            patch("apps.tasks.models.HourlyMetricsCollection") as mock_hourly,
            patch("apps.tasks.collectors.daily_metrics_rollup.create_task_result", return_value={"status": "success"}),
        ):
            mock_hourly.objects.filter.return_value.exists.return_value = True
            mock_collections.return_value = ({}, None, None)

            from apps.tasks.collectors.daily_metrics_rollup import daily_metrics_rollup

            daily_metrics_rollup()

        rollup_arg = mock_save.call_args.args[1]
        assert rollup_arg["analytics_usage"] == {}
        assert mock_save.call_args.args[6]["metrics"] == cumulative_usage

    def test_failed_usage_scrape_does_not_replace_saved_baseline(self):
        with (
            patch("apps.tasks.collectors.daily_metrics_rollup.aggregate_analytics_usage", return_value=None),
            patch(
                "apps.tasks.collectors.daily_metrics_rollup._collect_and_group_hourly_collections"
            ) as mock_collections,
            patch("apps.tasks.collectors.daily_metrics_rollup._merge_hourly_rollups", return_value=({}, [])),
            patch("apps.tasks.collectors.daily_metrics_rollup._aggregate_dashboard_telemetry", return_value=[]),
            patch("apps.tasks.collectors.daily_metrics_rollup._save_daily_summary") as mock_save,
            patch("apps.tasks.collectors.daily_metrics_rollup.log_task_execution"),
            patch("apps.tasks.models.HourlyMetricsCollection") as mock_hourly,
            patch("apps.tasks.collectors.daily_metrics_rollup.create_task_result", return_value={"status": "success"}),
        ):
            mock_hourly.objects.filter.return_value.exists.return_value = True
            mock_collections.return_value = ({}, None, None)

            from apps.tasks.collectors.daily_metrics_rollup import daily_metrics_rollup

            daily_metrics_rollup()

        assert mock_save.call_args.args[1]["analytics_usage"] == {}
        assert mock_save.call_args.args[6] is None

    def test_rollup_uses_summary_date_for_telemetry_query(self):
        """_aggregate_dashboard_telemetry is called with the summary_date being rolled up."""
        specific_date = date.today() - timedelta(days=2)

        with (
            patch(
                "apps.tasks.collectors.daily_metrics_rollup._aggregate_dashboard_telemetry",
                return_value=[],
            ) as mock_aggregate,
            patch("apps.tasks.collectors.daily_metrics_rollup.aggregate_analytics_usage") as mock_usage,
            patch(
                "apps.tasks.collectors.daily_metrics_rollup._collect_and_group_hourly_collections"
            ) as mock_collections,
            patch("apps.tasks.collectors.daily_metrics_rollup._merge_hourly_rollups") as mock_merge,
            patch("apps.tasks.collectors.daily_metrics_rollup._save_daily_summary") as mock_save,
            patch("apps.tasks.collectors.daily_metrics_rollup.log_task_execution"),
            patch("apps.tasks.models.HourlyMetricsCollection") as mock_hourly,
            patch("apps.tasks.collectors.daily_metrics_rollup.create_task_result") as mock_result,
        ):
            mock_hourly.objects.filter.return_value.exists.return_value = True
            mock_collections.return_value = ({}, None, None)
            mock_merge.return_value = ({}, [])
            mock_save.return_value = (MagicMock(aggregated_metrics={}), True, 0)
            mock_result.return_value = {"status": "success"}

            from apps.tasks.collectors.daily_metrics_rollup import daily_metrics_rollup

            daily_metrics_rollup(summary_date=specific_date.isoformat())

        mock_aggregate.assert_called_once_with(specific_date)
        mock_usage.assert_not_called()


# ---------------------------------------------------------------------------
# daily_anonymize_and_prepare — dashboard_telemetry propagation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
class TestDailyAnonymizeTelemetry:
    """Tests that daily_anonymize_and_prepare forwards dashboard_telemetry to the payload."""

    def test_dashboard_telemetry_included_in_anonymized_data(self):
        """When the DailyMetricsSummary metrics contain dashboard_telemetry,
        it is propagated into the AnonymizedMetricsPayload's anonymized_data."""
        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        telemetry = [
            {
                "task_name": "collect_dashboard_reports_initial_data",
                "collection_duration_ms": "1500.00",
                "number_of_records_processed": 10,
                "database_query_time_ms": "200.00",
                "cache_hit_rate": None,
            }
        ]

        specific_date = date(2024, 5, 20)
        DailyMetricsSummary.objects.filter(summary_date=specific_date).delete()

        DailyMetricsSummary.objects.create(
            summary_date=specific_date,
            status="aggregated",
            aggregated_metrics={
                "unified_jobs": {},
                "job_host_summary_service": {},
                "dashboard_telemetry": telemetry,
            },
        )

        mock_anonymized = {"data": {"metrics": []}, "salt": "test-salt"}

        with patch("metrics_utility.anonymized_rollups.anonymize_rollups", return_value=mock_anonymized):
            from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare

            result = daily_anonymize_and_prepare(summary_date="2024-05-20")

        assert result["status"] == "success"
        payload = AnonymizedMetricsPayload.objects.get(summary_date=specific_date)
        assert payload.anonymized_data["dashboard_telemetry"] == telemetry

    def test_analytics_usage_included_in_anonymized_data(self):
        """Prometheus usage remains in its own aggregate-only payload section."""
        from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare
        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        specific_date = date(2024, 8, 1)
        usage = {"controller.config": {"request_count": 2, "duration_ms_average": 15.5}}
        DailyMetricsSummary.objects.filter(summary_date=specific_date).delete()
        DailyMetricsSummary.objects.create(
            summary_date=specific_date,
            status="aggregated",
            aggregated_metrics={"unified_jobs": {}, "job_host_summary_service": {}, "analytics_usage": usage},
        )

        with patch("metrics_utility.anonymized_rollups.anonymize_rollups", return_value={"data": {}}):
            result = daily_anonymize_and_prepare(summary_date=specific_date.isoformat())

        assert result["status"] == "success"
        payload = AnonymizedMetricsPayload.objects.get(summary_date=specific_date)
        assert payload.anonymized_data["analytics_usage"] == usage
        assert "organization_name" not in str(payload.anonymized_data["analytics_usage"])

    def test_missing_analytics_usage_is_empty(self):
        """A missing or empty Prometheus scrape does not block anonymization."""
        from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare
        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        specific_date = date(2024, 8, 2)
        DailyMetricsSummary.objects.filter(summary_date=specific_date).delete()
        DailyMetricsSummary.objects.create(
            summary_date=specific_date,
            status="aggregated",
            aggregated_metrics={"unified_jobs": {}, "job_host_summary_service": {}},
        )

        with patch("metrics_utility.anonymized_rollups.anonymize_rollups", return_value={"data": {}}):
            result = daily_anonymize_and_prepare(summary_date=specific_date.isoformat())

        assert result["status"] == "success"
        payload = AnonymizedMetricsPayload.objects.get(summary_date=specific_date)
        assert payload.anonymized_data["analytics_usage"] == {}

    def test_missing_dashboard_telemetry_defaults_to_empty_list(self):
        """When dashboard_telemetry is absent from the summary metrics,
        the payload's anonymized_data sets dashboard_telemetry to []."""
        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        specific_date = date(2024, 6, 10)
        DailyMetricsSummary.objects.filter(summary_date=specific_date).delete()

        DailyMetricsSummary.objects.create(
            summary_date=specific_date,
            status="aggregated",
            aggregated_metrics={"unified_jobs": {}, "job_host_summary_service": {}},
        )

        mock_anonymized = {"data": {"metrics": []}, "salt": "test-salt"}

        with patch("metrics_utility.anonymized_rollups.anonymize_rollups", return_value=mock_anonymized):
            from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare

            result = daily_anonymize_and_prepare(summary_date="2024-06-10")

        assert result["status"] == "success"
        payload = AnonymizedMetricsPayload.objects.get(summary_date=specific_date)
        assert payload.anonymized_data["dashboard_telemetry"] == []

    def test_no_sensitive_data_in_payload(self):
        """The dashboard_telemetry transmitted in the payload contains no sensitive fields."""
        from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

        specific_date = date(2024, 7, 1)
        DailyMetricsSummary.objects.filter(summary_date=specific_date).delete()

        telemetry = [
            {
                "task_name": "cleanup_dashboard_reports_old_data",
                "collection_duration_ms": "300.00",
                "number_of_records_processed": 2,
                "database_query_time_ms": "50.00",
                "cache_hit_rate": None,
            }
        ]

        DailyMetricsSummary.objects.create(
            summary_date=specific_date,
            status="aggregated",
            aggregated_metrics={"unified_jobs": {}, "job_host_summary_service": {}, "dashboard_telemetry": telemetry},
        )

        mock_anonymized = {"data": {"metrics": []}, "salt": "test-salt"}

        with patch("metrics_utility.anonymized_rollups.anonymize_rollups", return_value=mock_anonymized):
            from apps.tasks.collectors.daily_anonymize_and_prepare import daily_anonymize_and_prepare

            daily_anonymize_and_prepare(summary_date="2024-07-01")

        payload = AnonymizedMetricsPayload.objects.get(summary_date=specific_date)
        for entry in payload.anonymized_data["dashboard_telemetry"]:
            sensitive_keys = {"organization_name", "user_id", "username", "job_id"}
            assert not sensitive_keys.intersection(entry.keys())


# ---------------------------------------------------------------------------
# _analytics_usage — failure isolation and reported status
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.django_db
class TestAnalyticsUsageStatus:
    """The usage helper degrades to empty usage and a status, never an exception."""

    @staticmethod
    def _yesterday():
        from django.utils import timezone

        return timezone.now().date() - timedelta(days=1)

    def test_backfill_of_an_older_date_is_skipped(self):
        from apps.tasks.collectors.daily_metrics_rollup import _analytics_usage

        usage, snapshot, status = _analytics_usage(self._yesterday() - timedelta(days=3))

        assert (usage, snapshot, status) == ({}, None, "skipped")

    def test_unconfigured_endpoint_is_reported_without_scraping(self):
        from django.test import override_settings

        from apps.tasks.collectors.daily_metrics_rollup import _analytics_usage

        with (
            override_settings(INTERNAL_PROMETHEUS_URL=""),
            patch("apps.tasks.collectors.daily_metrics_rollup.aggregate_analytics_usage") as mock_usage,
        ):
            usage, snapshot, status = _analytics_usage(self._yesterday())

        assert (usage, snapshot, status) == ({}, None, "not_configured")
        mock_usage.assert_not_called()

    def test_failed_scrape_is_reported(self):
        from apps.tasks.collectors.daily_metrics_rollup import _analytics_usage

        with patch("apps.tasks.collectors.daily_metrics_rollup.aggregate_analytics_usage", return_value=None):
            usage, snapshot, status = _analytics_usage(self._yesterday())

        assert (usage, snapshot, status) == ({}, None, "scrape_failed")

    def test_first_scrape_reports_baseline(self):
        cumulative = {"controller.config": {"request_count": 5, "duration_ms_total": 60.0, "duration_sample_count": 4}}
        from apps.tasks.collectors.daily_metrics_rollup import _analytics_usage

        with (
            patch("apps.tasks.collectors.daily_metrics_rollup.aggregate_analytics_usage", return_value=cumulative),
            patch("apps.tasks.collectors.daily_metrics_rollup._previous_analytics_usage_snapshot", return_value=None),
        ):
            usage, snapshot, status = _analytics_usage(self._yesterday())

        assert usage == {}
        assert snapshot["metrics"] == cumulative
        assert status == "baseline"

    def test_a_malformed_stored_baseline_does_not_raise(self):
        """A non-dict value in the stored snapshot must not abort the caller's rollup."""
        cumulative = {"controller.config": {"request_count": 5, "duration_ms_total": 60.0, "duration_sample_count": 4}}
        from apps.tasks.collectors.daily_metrics_rollup import _analytics_usage

        with (
            patch("apps.tasks.collectors.daily_metrics_rollup.aggregate_analytics_usage", return_value=cumulative),
            patch(
                "apps.tasks.collectors.daily_metrics_rollup._previous_analytics_usage_snapshot",
                return_value={"observed_at": "2026-10-08T02:00:00+00:00", "metrics": {"controller.config": "corrupt"}},
            ),
            patch("apps.tasks.collectors.daily_metrics_rollup.logger") as mock_logger,
        ):
            usage, snapshot, status = _analytics_usage(self._yesterday())

        assert (usage, snapshot, status) == ({}, None, "delta_failed")
        mock_logger.exception.assert_called_once()


@pytest.mark.unit
class TestDailyMetricsRollupSurvivesTelemetryFailure:
    """Telemetry must never cost us the day's summary or its anonymized payload."""

    def test_rollup_still_saves_a_summary_when_the_usage_delta_fails(self):
        with (
            patch(
                "apps.tasks.collectors.daily_metrics_rollup._analytics_usage",
                return_value=({}, None, "delta_failed"),
            ),
            patch("apps.tasks.collectors.daily_metrics_rollup._aggregate_dashboard_telemetry", return_value=[]),
            patch(
                "apps.tasks.collectors.daily_metrics_rollup._collect_and_group_hourly_collections"
            ) as mock_collections,
            patch("apps.tasks.collectors.daily_metrics_rollup._merge_hourly_rollups") as mock_merge,
            patch("apps.tasks.collectors.daily_metrics_rollup._save_daily_summary") as mock_save,
            patch("apps.tasks.collectors.daily_metrics_rollup.log_task_execution"),
            patch("apps.tasks.models.HourlyMetricsCollection") as mock_hourly,
        ):
            mock_hourly.objects.filter.return_value.exists.return_value = True
            mock_collections.return_value = ({}, None, None)
            mock_merge.return_value = ({}, [])
            mock_save.return_value = (MagicMock(id=7, aggregated_metrics={}), True, 0)

            from apps.tasks.collectors.daily_metrics_rollup import daily_metrics_rollup

            result = daily_metrics_rollup()

        mock_save.assert_called_once()
        assert result["status"] == "success"
        assert result["analytics_usage_status"] == "delta_failed"


@pytest.mark.unit
@pytest.mark.django_db
class TestAnalyticsUsagePreservedOnRerun:
    """Re-running a rollup must not re-measure a date that was already measured."""

    @staticmethod
    def _summary(summary_date, usage, snapshot):
        from apps.tasks.models import DailyMetricsSummary

        return DailyMetricsSummary.objects.create(
            summary_date=summary_date,
            status="aggregated",
            aggregated_metrics={"unified_jobs": {}, "analytics_usage": usage},
            analytics_usage_snapshot=snapshot,
        )

    def _yesterday(self):
        from django.utils import timezone

        return timezone.now().date() - timedelta(days=1)

    def test_rerun_keeps_the_recorded_usage_and_baseline(self):
        """A second scrape would report C2-C0, re-counting what C1-C0 already shipped."""
        from apps.tasks.collectors.daily_metrics_rollup import _analytics_usage

        recorded = {"controller.config": {"request_count": 2, "duration_ms_total": 30.0, "duration_ms_average": 15.0}}
        self._summary(
            self._yesterday(),
            recorded,
            {
                "observed_at": "2026-10-09T02:00:00+00:00",
                "metrics": {"controller.config": {"request_count": 5, "duration_ms_total": 60.0}},
            },
        )

        with patch("apps.tasks.collectors.daily_metrics_rollup.aggregate_analytics_usage") as mock_usage:
            usage, snapshot, status = _analytics_usage(self._yesterday())

        assert usage == recorded
        # A None snapshot leaves the stored baseline in place, so tomorrow still diffs against C1.
        assert snapshot is None
        assert status == "preserved"
        mock_usage.assert_not_called()

    def test_backfilling_an_older_date_does_not_blank_its_recorded_usage(self):
        from apps.tasks.collectors.daily_metrics_rollup import _analytics_usage

        older = self._yesterday() - timedelta(days=5)
        recorded = {"controller.config": {"request_count": 7, "duration_ms_total": 91.0, "duration_ms_average": 13.0}}
        self._summary(older, recorded, {"observed_at": "2026-10-04T02:00:00+00:00", "metrics": {}})

        usage, snapshot, status = _analytics_usage(older)

        assert (usage, snapshot, status) == (recorded, None, "preserved")

    def test_rerun_after_a_failed_scrape_still_measures_the_date(self):
        """No stored baseline means the date was never measured, so a retry should scrape."""
        from apps.tasks.collectors.daily_metrics_rollup import _analytics_usage

        self._summary(self._yesterday(), {}, {})
        cumulative = {"controller.config": {"request_count": 5, "duration_ms_total": 60.0, "duration_sample_count": 4}}

        with (
            patch("apps.tasks.collectors.daily_metrics_rollup.aggregate_analytics_usage", return_value=cumulative),
            patch("apps.tasks.collectors.daily_metrics_rollup._previous_analytics_usage_snapshot", return_value=None),
        ):
            usage, snapshot, status = _analytics_usage(self._yesterday())

        assert (usage, status) == ({}, "baseline")
        assert snapshot["metrics"] == cumulative
