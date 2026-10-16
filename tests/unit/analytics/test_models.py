"""Tests for analytics storage models."""

from datetime import UTC, datetime

import pytest

from apps.analytics.models import AnalyticsAPIUsageCounter, AnalyticsPayload

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _times():
    started = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)
    finished = datetime(2026, 8, 17, 10, 1, tzinfo=UTC)
    return started, finished


def test_analytics_payload_string_for_window():
    started, finished = _times()
    row = AnalyticsPayload.objects.create(
        collector="controller.unified_jobs_dashboard",
        since=started,
        until=finished,
        started_at=started,
        finished_at=finished,
        payload=[{"id": 1}],
    )

    assert str(row) == f"controller.unified_jobs_dashboard [local] ({started} \u2192 {finished})"


def test_analytics_payload_string_for_snapshot():
    started, finished = _times()
    row = AnalyticsPayload.objects.create(
        collector="controller.config",
        started_at=started,
        finished_at=finished,
        payload={"version": "1.2.3"},
    )

    assert str(row) == "controller.config [local] (snapshot)"


def test_analytics_payload_retains_multiple_snapshots():
    started, finished = _times()
    for offset in range(2):
        AnalyticsPayload.objects.create(
            collector="controller.config",
            started_at=started.replace(minute=started.minute + offset),
            finished_at=finished.replace(minute=finished.minute + offset),
            payload={"version": str(offset)},
        )

    assert AnalyticsPayload.objects.filter(collector="controller.config").count() == 2


def test_analytics_payload_retains_duplicate_window():
    started, finished = _times()
    window = {"collector": "controller.unified_jobs_dashboard", "since": started, "until": finished}
    for value in (1, 2):
        AnalyticsPayload.objects.create(started_at=started, finished_at=finished, payload={"v": value}, **window)

    assert AnalyticsPayload.objects.filter(**window).count() == 2


def test_analytics_api_usage_counter_increments_and_summarizes_by_operation_and_status():
    usage_date = datetime(2026, 8, 17, tzinfo=UTC).date()

    AnalyticsAPIUsageCounter.record_request(usage_date, "discovery", 2)
    AnalyticsAPIUsageCounter.record_request(usage_date, "discovery", 2)
    AnalyticsAPIUsageCounter.record_request(usage_date, "rows", 4)
    AnalyticsAPIUsageCounter.record_request(usage_date.replace(day=18), "collect", 5)

    summary = AnalyticsAPIUsageCounter.daily_summary(usage_date)

    assert summary["available"] is True
    assert summary["total_requests"] == 3
    assert summary["by_operation"]["discovery"]["2xx"] == 2
    assert summary["by_operation"]["rows"]["4xx"] == 1
    assert summary["by_operation"]["collect"]["5xx"] == 0
    assert AnalyticsAPIUsageCounter.objects.filter(usage_date=usage_date).count() == 2


def test_analytics_api_usage_counter_returns_zero_filled_summary_when_empty():
    summary = AnalyticsAPIUsageCounter.daily_summary(datetime(2026, 8, 17, tzinfo=UTC).date())

    assert summary["available"] is True
    assert summary["total_requests"] == 0
    assert summary["by_operation"]["discovery"] == {
        "1xx": 0,
        "2xx": 0,
        "3xx": 0,
        "4xx": 0,
        "5xx": 0,
    }


def test_analytics_api_usage_counter_stores_only_aggregate_fields():
    field_names = {field.name for field in AnalyticsAPIUsageCounter._meta.get_fields()}

    assert field_names == {"id", "usage_date", "operation", "status_class", "request_count"}
