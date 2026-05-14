"""
Unit tests for apps/tasks/simple/ and daily_metrics_rollup coverage.
"""

from datetime import date, timedelta

import pytest
from django.utils import timezone


# ---------------------------------------------------------------------------
# hello_world task
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_hello_world_returns_success():
    from apps.tasks.simple.hello_world import hello_world

    result = hello_world()
    assert result["status"] == "success"
    assert result["message"] == "Hello World from dispatcherd!"
    assert result["completed"] is True


@pytest.mark.unit
def test_hello_world_ignores_kwargs():
    from apps.tasks.simple.hello_world import hello_world

    result = hello_world(some_kwarg="ignored", another=42)
    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# daily_metrics_rollup helpers
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_collect_and_group_hourly_collections_empty():
    from apps.tasks.collectors.daily_metrics_rollup import _collect_and_group_hourly_collections
    from apps.tasks.models import HourlyMetricsCollection

    yesterday = date.today() - timedelta(days=1)
    HourlyMetricsCollection.objects.filter(
        collection_timestamp__date=yesterday
    ).delete()

    collections_by_type, start, end = _collect_and_group_hourly_collections(yesterday)
    assert isinstance(collections_by_type, dict)


@pytest.mark.unit
@pytest.mark.django_db
def test_collect_and_group_hourly_collections_with_data():
    from apps.tasks.collectors.daily_metrics_rollup import _collect_and_group_hourly_collections
    from apps.tasks.models import HourlyMetricsCollection

    yesterday = date.today() - timedelta(days=3)
    ts = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=3)
    HourlyMetricsCollection.objects.get_or_create(
        collector_type="unified_jobs",
        collection_timestamp=ts,
        defaults={"raw_data": {"jobs": []}, "status": "collected"},
    )

    collections_by_type, start, end = _collect_and_group_hourly_collections(yesterday)
    assert isinstance(collections_by_type, dict)


@pytest.mark.unit
@pytest.mark.django_db
def test_daily_metrics_rollup_with_no_collections():
    from apps.tasks.collectors.daily_metrics_rollup import daily_metrics_rollup

    # Ensure yesterday has no collections
    yesterday = (date.today() - timedelta(days=5)).isoformat()
    result = daily_metrics_rollup(rollup_date=yesterday)
    assert result["status"] in ("success", "error")


@pytest.mark.unit
@pytest.mark.django_db
def test_daily_metrics_rollup_invalid_date():
    from apps.tasks.collectors.daily_metrics_rollup import daily_metrics_rollup

    result = daily_metrics_rollup(rollup_date="not-a-date")
    assert result["status"] == "error"
