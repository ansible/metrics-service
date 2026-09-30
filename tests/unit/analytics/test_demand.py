"""Tests for analytics demand period resolution."""

from datetime import UTC, datetime

import pytest

from apps.analytics.demand import previous_and_current_windows, resolve_task_period
from apps.analytics.registry import get_entry
from apps.tasks.models import Task

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

HOURLY = "controller.unified_jobs_dashboard"
DAILY = "controller.main_host_daily"


def _task(function_name, task_data, *, scheduled_time=None, cron_expression=None):
    return Task.objects.create(
        name=f"test-{function_name}-{Task.objects.count()}",
        description="",
        function_name=function_name,
        task_data=task_data,
        scheduled_time=scheduled_time,
        cron_expression=cron_expression,
        status="pending",
    )


def test_previous_and_current_windows_are_utc():
    now = datetime(2026, 8, 17, 10, 30, tzinfo=UTC)

    previous, current = previous_and_current_windows("hourly", now)

    assert previous.since == datetime(2026, 8, 17, 9, tzinfo=UTC)
    assert previous.until == datetime(2026, 8, 17, 10, tzinfo=UTC)
    assert current.since == datetime(2026, 8, 17, 10, tzinfo=UTC)
    assert current.until == datetime(2026, 8, 17, 11, tzinfo=UTC)


def test_previous_and_current_daily_windows_accept_naive_datetimes():
    previous, current = previous_and_current_windows("daily", datetime(2026, 8, 18, 1, 30))

    assert previous.since == datetime(2026, 8, 17, tzinfo=UTC)
    assert previous.until == datetime(2026, 8, 18, tzinfo=UTC)
    assert current.since == datetime(2026, 8, 18, tzinfo=UTC)
    assert current.until == datetime(2026, 8, 19, tzinfo=UTC)


def test_previous_and_current_windows_reject_snapshot_mode():
    with pytest.raises(ValueError, match="snapshot"):
        previous_and_current_windows("snapshot", datetime(2026, 8, 17, tzinfo=UTC))


def test_hour_timestamp_resolves_exact_hour():
    task = _task(
        "collect_hourly_metrics",
        {"collector_type": "unified_jobs", "hour_timestamp": "2026-08-17T09:00:00Z"},
    )

    period = resolve_task_period(get_entry(HOURLY), task, datetime(2026, 8, 17, 10, 30, tzinfo=UTC))

    assert period.window.since == datetime(2026, 8, 17, 9, tzinfo=UTC)
    assert period.window.until == datetime(2026, 8, 17, 10, tzinfo=UTC)


def test_daily_hour_timestamp_resolves_previous_day():
    task = _task(
        "collect_daily_metrics",
        {"collector_type": "main_host_daily", "hour_timestamp": "2026-08-18T00:00:00Z"},
    )

    period = resolve_task_period(get_entry(DAILY), task, datetime(2026, 8, 18, 1, tzinfo=UTC))

    assert period.window.since == datetime(2026, 8, 17, tzinfo=UTC)
    assert period.window.until == datetime(2026, 8, 18, tzinfo=UTC)


def test_manual_scheduled_task_uses_existing_fallback_semantics():
    scheduled_time = datetime(2026, 8, 17, 11, tzinfo=UTC)
    task = _task(
        "collect_hourly_metrics",
        {"collector_type": "unified_jobs"},
        scheduled_time=scheduled_time,
    )

    period = resolve_task_period(get_entry(HOURLY), task, datetime(2026, 8, 17, 10, 30, tzinfo=UTC))

    assert period.window.since == datetime(2026, 8, 17, 10, tzinfo=UTC)
    assert period.window.until == datetime(2026, 8, 17, 11, tzinfo=UTC)


def test_open_ended_custom_task_does_not_match_canonical_window():
    task = _task(
        "collect_analytics_on_demand",
        {"collector": HOURLY, "since": None, "until": "2026-08-17T10:00:00Z"},
    )

    period = resolve_task_period(get_entry(HOURLY), task, datetime(2026, 8, 17, 10, 30, tzinfo=UTC))

    assert period.window is None
    assert period.resolvable


def test_invalid_on_demand_timestamp_is_unresolvable():
    task = _task("collect_analytics_on_demand", {"collector": HOURLY, "since": "invalid"})

    period = resolve_task_period(get_entry(HOURLY), task, datetime(2026, 8, 17, 10, 30, tzinfo=UTC))

    assert not period.resolvable


def test_snapshot_on_demand_task_resolves_creation_time():
    task = _task("collect_analytics_on_demand", {"collector": "controller.config"})

    period = resolve_task_period(get_entry("controller.config"), task, datetime(2026, 8, 17, tzinfo=UTC))

    assert period.snapshot_at == task.created


def test_regular_snapshot_task_resolves_and_rejects_bad_metadata():
    valid_task = _task(
        "collect_snapshot_metrics",
        {"collector_type": "config", "collection_timestamp": "2026-08-16T23:00:00Z"},
    )
    invalid_task = _task("collect_snapshot_metrics", {"collector_type": "config", "collection_timestamp": "invalid"})

    valid_period = resolve_task_period(get_entry("controller.config"), valid_task, datetime(2026, 8, 17, tzinfo=UTC))
    invalid_period = resolve_task_period(
        get_entry("controller.config"), invalid_task, datetime(2026, 8, 17, tzinfo=UTC)
    )

    assert valid_period.snapshot_at == valid_task.created
    assert not invalid_period.resolvable


def test_task_for_another_collector_is_not_resolved():
    task = _task("collect_hourly_metrics", {"collector_type": "other_collector"})

    assert resolve_task_period(get_entry(HOURLY), task, datetime(2026, 8, 17, tzinfo=UTC)) is None


def test_invalid_timestamp_is_unresolvable():
    task = _task(
        "collect_hourly_metrics",
        {"collector_type": "unified_jobs", "hour_timestamp": "not-a-date"},
    )

    period = resolve_task_period(get_entry(HOURLY), task, datetime(2026, 8, 17, 10, 30, tzinfo=UTC))

    assert not period.resolvable
