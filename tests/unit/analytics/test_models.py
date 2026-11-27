"""Tests for analytics storage models."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from django.db import IntegrityError, connection
from django.db.models import QuerySet
from django.test.utils import CaptureQueriesContext

from apps.analytics.models import AnalyticsPayload, APIUsageCounter
from tests.test_utils import _times

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


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


def test_api_usage_counter_increments_and_summarizes_by_endpoint_and_status():
    usage_date = datetime(2026, 8, 17, tzinfo=UTC).date()

    APIUsageCounter.record_request(usage_date, "analytics:v1:root", 2)
    APIUsageCounter.record_request(usage_date, "analytics:v1:root", 2)
    APIUsageCounter.record_request(usage_date, "analytics:v1:rows", 4)
    APIUsageCounter.record_request(usage_date.replace(day=18), "analytics:v1:collect", 5)

    summary = APIUsageCounter.daily_summary(usage_date)

    assert summary["available"] is True
    assert summary["total_requests"] == 3
    assert summary["by_endpoint"]["analytics:v1:root"]["2xx"] == 2
    assert summary["by_endpoint"]["analytics:v1:rows"]["4xx"] == 1
    assert APIUsageCounter.objects.filter(usage_date=usage_date).count() == 2


def test_api_usage_counter_returns_empty_endpoint_map_when_empty():
    summary = APIUsageCounter.daily_summary(datetime(2026, 8, 17, tzinfo=UTC).date())

    assert summary["available"] is True
    assert summary["total_requests"] == 0
    assert summary["by_endpoint"] == {}


def test_api_usage_counter_stores_only_aggregate_fields():
    field_names = {field.name for field in APIUsageCounter._meta.get_fields()}

    assert field_names == {"id", "usage_date", "endpoint_name", "status_class", "request_count"}


def test_api_usage_counter_first_request_creates_row_with_count_one():
    usage_date = datetime(2026, 8, 17, tzinfo=UTC).date()

    APIUsageCounter.record_request(usage_date, "analytics:v1:root", 2)

    rows = APIUsageCounter.objects.filter(
        usage_date=usage_date,
        endpoint_name="analytics:v1:root",
        status_class=2,
    )
    assert rows.count() == 1
    assert rows.get().request_count == 1


def test_api_usage_counter_steady_state_increment_uses_single_query():
    usage_date = datetime(2026, 8, 17, tzinfo=UTC).date()
    counter = APIUsageCounter.objects.create(
        usage_date=usage_date,
        endpoint_name="analytics:v1:root",
        status_class=2,
        request_count=41,
    )

    with CaptureQueriesContext(connection) as captured:
        APIUsageCounter.record_request(usage_date, "analytics:v1:root", 2)

    assert len(captured.captured_queries) == 1
    assert captured.captured_queries[0]["sql"].strip().upper().startswith("UPDATE")
    counter.refresh_from_db()
    assert counter.request_count == 42


def test_api_usage_counter_increments_when_row_inserted_between_update_and_get_or_create():
    usage_date = datetime(2026, 8, 17, tzinfo=UTC).date()
    real_update = QuerySet.update
    update_calls = 0

    def update_then_competing_insert(self, **kwargs):
        nonlocal update_calls
        update_calls += 1
        updated = real_update(self, **kwargs)
        if update_calls == 1:
            # The first UPDATE finds no row; a competing writer inserts it before
            # get_or_create runs, so get_or_create() returns created=False.
            assert updated == 0
            APIUsageCounter.objects.create(
                usage_date=usage_date,
                endpoint_name="analytics:v1:root",
                status_class=2,
                request_count=1,
            )
        return updated

    with patch.object(QuerySet, "update", update_then_competing_insert):
        APIUsageCounter.record_request(usage_date, "analytics:v1:root", 2)

    rows = APIUsageCounter.objects.filter(usage_date=usage_date)
    assert rows.count() == 1
    assert rows.get().request_count == 2


def test_api_usage_counter_increments_on_unique_conflict_in_get_or_create():
    usage_date = datetime(2026, 8, 17, tzinfo=UTC).date()
    real_get = QuerySet.get
    real_create = QuerySet.create
    get_calls = 0
    conflicts = []

    def get_then_competing_insert(self, *args, **kwargs):
        nonlocal get_calls
        get_calls += 1
        try:
            return real_get(self, *args, **kwargs)
        except APIUsageCounter.DoesNotExist:
            if get_calls == 1:
                # The initial get() misses; a competing writer inserts the row before
                # create() runs, so create() hits the real unique constraint.
                APIUsageCounter.objects.create(
                    usage_date=usage_date,
                    endpoint_name="analytics:v1:root",
                    status_class=2,
                    request_count=1,
                )
            raise

    def record_conflicts(self, **kwargs):
        try:
            return real_create(self, **kwargs)
        except IntegrityError as exc:
            conflicts.append(exc)
            raise

    with (
        patch.object(QuerySet, "get", get_then_competing_insert),
        patch.object(QuerySet, "create", record_conflicts),
    ):
        APIUsageCounter.record_request(usage_date, "analytics:v1:root", 2)

    # One real IntegrityError from the unique constraint; the second get() recovers the row.
    assert len(conflicts) == 1
    assert get_calls == 2
    rows = APIUsageCounter.objects.filter(usage_date=usage_date)
    assert rows.count() == 1
    assert rows.get().request_count == 2
