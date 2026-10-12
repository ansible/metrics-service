"""Tests for database-backed analytics endpoint usage telemetry."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.analytics.models import AnalyticsUsage
from apps.analytics.telemetry import daily_analytics_usage, record_collector_get

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

ROOT = "/api/v1/analytics/"
COLLECTOR = "controller.config"


def test_successful_collector_gets_accumulate_in_one_daily_row(authenticated_client):
    for _ in range(2):
        response = authenticated_client.get(f"{ROOT}{COLLECTOR}/")
        assert response.status_code == 200

    usage = AnalyticsUsage.objects.get(usage_date=timezone.now().date(), collector=COLLECTOR)
    assert usage.request_count == 2
    assert usage.duration_ms_total > 0


def test_unsuccessful_collector_gets_are_not_counted(authenticated_client):
    invalid_window = authenticated_client.get(f"{ROOT}{COLLECTOR}/?since=not-a-date")
    unknown_collector = authenticated_client.get(f"{ROOT}nope.nope/")

    assert invalid_window.status_code == 400
    assert unknown_collector.status_code == 404
    assert not AnalyticsUsage.objects.exists()


def test_recording_failure_does_not_escape_to_api_caller(monkeypatch):
    def fail_to_save(**kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(AnalyticsUsage.objects, "get_or_create", fail_to_save)

    record_collector_get(COLLECTOR, 12.5)


def test_daily_aggregate_returns_counts_and_duration_statistics():
    summary_date = timezone.now().date() - timedelta(days=1)
    AnalyticsUsage.objects.create(
        usage_date=summary_date,
        collector=COLLECTOR,
        request_count=4,
        duration_ms_total=Decimal("10.500000"),
    )
    AnalyticsUsage.objects.create(
        usage_date=summary_date - timedelta(days=1),
        collector=COLLECTOR,
        request_count=100,
        duration_ms_total=Decimal("500.000000"),
    )

    assert daily_analytics_usage(summary_date) == {
        COLLECTOR: {
            "request_count": 4,
            "duration_ms_total": 10.5,
            "duration_ms_average": 2.625,
        }
    }


def test_daily_aggregate_is_empty_when_no_usage_exists():
    assert daily_analytics_usage(timezone.now().date() - timedelta(days=1)) == {}
