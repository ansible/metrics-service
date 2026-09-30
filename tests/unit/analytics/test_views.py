"""Tests for the read-only analytics API."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from apps.analytics.models import AnalyticsPayload
from apps.analytics.v1 import views
from apps.tasks.models import Task

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

ROOT = "/api/v1/analytics/"
UNIFIED = "controller.unified_jobs_dashboard"
CONFIG = "controller.config"
DAILY = "controller.main_host_daily"


def _row(collector, since, until, payload=None):
    started = datetime(2026, 8, 17, 10, tzinfo=UTC)
    return AnalyticsPayload.objects.create(
        collector=collector,
        since=since,
        until=until,
        started_at=started,
        finished_at=started + timedelta(seconds=1),
        payload=payload or {"collector": collector},
    )


def test_root_lists_enabled_collectors(authenticated_client):
    response = authenticated_client.get(ROOT)

    assert response.status_code == 200
    names = {collector["name"] for collector in response.json()["collectors"]}
    assert UNIFIED in names
    assert CONFIG in names
    unified = next(collector for collector in response.json()["collectors"] if collector["name"] == UNIFIED)
    assert unified["description"] == (
        "Job executions, including status and timing, organization, inventory, project, template, "
        "execution environment, launcher, labels, and host count."
    )
    assert "service.task_executions_service" not in names
    assert all(
        collector["rows_url"].startswith("http://testserver/api/v1/analytics/")
        for collector in response.json()["collectors"]
    )
    assert all(
        collector["collect_url"].endswith(f"/api/v1/analytics/{collector['name']}/collect/")
        for collector in response.json()["collectors"]
    )


def test_root_browsable_response_links_collector_urls(authenticated_client):
    response = authenticated_client.get(ROOT, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert 'href="http://testserver/api/v1/analytics/controller.config/"' in response.text
    assert "accepts_since_until" in response.text
    assert "collect_url" in response.text


def test_collect_get_schema_documents_query_parameters_and_demand_response():
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)
    operation = schema["paths"]["/api/v1/analytics/{collector}/collect/"]["get"]
    params_by_name = {parameter["name"]: parameter for parameter in operation["parameters"]}

    assert {"collector", "page", "page_size", "since", "until"} == set(params_by_name)
    assert params_by_name["since"]["schema"] == {"type": "string", "format": "date-time"}
    assert params_by_name["until"]["schema"] == {"type": "string", "format": "date-time"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AnalyticsCollectRowsResponse"
    }

    demand_schema = schema["components"]["schemas"]["CollectionDemand"]
    assert set(demand_schema["properties"]) == {"previous", "current", "snapshot"}
    result_schema = schema["components"]["schemas"]["CollectionDemandResult"]
    assert result_schema["properties"]["action"]["enum"] == [
        "already_collected",
        "cron_covered",
        "existing_task",
        "scheduled",
        "suppressed",
        "triggered",
    ]


def test_rows_browsable_response_shows_field_description(authenticated_client):
    response = authenticated_client.get(f"{ROOT}{CONFIG}/", HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert "The linked collector row endpoints return paginated collection envelopes." in response.text
    assert "payload" in response.text


def test_rows_pagination_links_are_absolute(authenticated_client):
    for index in range(2):
        _row(
            CONFIG,
            datetime(2026, 8, 17, 10 + index, tzinfo=UTC),
            datetime(2026, 8, 17, 11 + index, tzinfo=UTC),
            {"index": index},
        )

    response = authenticated_client.get(f"{ROOT}{CONFIG}/?page_size=1")

    assert response.status_code == 200
    body = response.json()
    assert body["next"].startswith("http://testserver/api/v1/analytics/")
    assert body["previous"] is None


def test_root_requires_auth(api_client):
    assert api_client.get(ROOT).status_code in (401, 403)


def test_rows_unknown_collector_404(authenticated_client):
    assert authenticated_client.get(f"{ROOT}nope.nope/").status_code == 404


def test_rows_return_collection_envelope(authenticated_client):
    _row(UNIFIED, datetime(2026, 8, 17, 10, tzinfo=UTC), datetime(2026, 8, 17, 11, tzinfo=UTC), {"v": 1})

    response = authenticated_client.get(f"{ROOT}{UNIFIED}/")

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["collector"] == UNIFIED
    assert result["source"] == "local"
    assert result["payload"] == {"v": 1}
    assert "started_at" in result
    assert "finished_at" in result
    assert "state" not in result


def test_rows_retain_duplicate_collections(authenticated_client):
    since = datetime(2026, 8, 17, 10, tzinfo=UTC)
    until = datetime(2026, 8, 17, 11, tzinfo=UTC)
    _row(UNIFIED, since, until, {"v": 1})
    _row(UNIFIED, since, until, {"v": 2})

    response = authenticated_client.get(f"{ROOT}{UNIFIED}/")

    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_rows_window_overlap_until_exclusive(authenticated_client):
    _row(UNIFIED, datetime(2026, 8, 17, 10, tzinfo=UTC), datetime(2026, 8, 17, 11, tzinfo=UTC))
    _row(UNIFIED, datetime(2026, 8, 17, 11, tzinfo=UTC), datetime(2026, 8, 17, 12, tzinfo=UTC))

    response = authenticated_client.get(f"{ROOT}{UNIFIED}/?since=2026-08-17T11:00:00Z&until=2026-08-17T12:00:00Z")

    assert response.status_code == 200
    windows = {(row["since"], row["until"]) for row in response.json()["results"]}
    assert len(windows) == 1


def test_rows_snapshot_null_window_always_matches(authenticated_client):
    _row(CONFIG, None, None, {"v": 1})
    response = authenticated_client.get(f"{ROOT}{CONFIG}/?since=2026-08-17T11:00:00Z&until=2026-08-17T12:00:00Z")

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_rows_one_sided_window_is_open_ended(authenticated_client):
    _row(UNIFIED, datetime(2026, 8, 17, 10, tzinfo=UTC), None)
    _row(UNIFIED, None, datetime(2026, 8, 17, 11, tzinfo=UTC))

    response = authenticated_client.get(f"{ROOT}{UNIFIED}/?until=2026-08-17T12:00:00Z")

    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_rows_invalid_since_400(authenticated_client):
    assert authenticated_client.get(f"{ROOT}{UNIFIED}/?since=notadate").status_code == 400


def test_rows_invalid_until_400(authenticated_client):
    assert authenticated_client.get(f"{ROOT}{UNIFIED}/?until=notadate").status_code == 400


def test_rows_reversed_window_400(authenticated_client):
    response = authenticated_client.get(f"{ROOT}{UNIFIED}/?since=2026-08-17T11:00:00Z&until=2026-08-17T10:00:00Z")

    assert response.status_code == 400


def test_collect_snapshot_creates_pending_task_without_collecting(authenticated_client):
    response = authenticated_client.post(f"{ROOT}{CONFIG}/collect/", {}, format="json")

    assert response.status_code == 202
    body = response.json()
    task = Task.objects.get(pk=body["task_id"])
    assert body["task_url"].endswith(f"/api/v1/tasks/{task.pk}/")
    assert body["task_data"] == {"collector": CONFIG}
    assert task.status == "pending"
    assert not AnalyticsPayload.objects.exists()


def test_collect_windowed_missing_until_uses_default(authenticated_client):
    response = authenticated_client.post(
        f"{ROOT}{UNIFIED}/collect/",
        {"since": "2026-08-17T10:00:00Z"},
        format="json",
    )

    assert response.status_code == 202
    task_data = response.json()["task_data"]
    assert task_data["collector"] == UNIFIED
    assert task_data["since"] == "2026-08-17T10:00:00+00:00"
    assert task_data["until"] is not None


def test_collect_windowed_fills_default_window(authenticated_client):
    response = authenticated_client.post(f"{ROOT}{UNIFIED}/collect/", {}, format="json")

    assert response.status_code == 202
    task_data = response.json()["task_data"]
    assert task_data["collector"] == UNIFIED
    assert task_data["since"] is not None
    assert task_data["until"] is not None
    assert task_data["since"] < task_data["until"]


def test_collect_windowed_explicit_null_bounds_remain_unbounded(authenticated_client):
    response = authenticated_client.post(
        f"{ROOT}{UNIFIED}/collect/",
        {"since": None, "until": None},
        format="json",
    )

    assert response.status_code == 202
    assert response.json()["task_data"] == {"collector": UNIFIED}


def test_collect_windowed_explicit_null_leaves_since_open(authenticated_client):
    response = authenticated_client.post(
        f"{ROOT}{UNIFIED}/collect/",
        {"since": None},
        format="json",
    )

    assert response.status_code == 202
    task_data = response.json()["task_data"]
    assert task_data["collector"] == UNIFIED
    assert "since" not in task_data
    assert task_data["until"] is not None


def test_collect_windowed_explicit_null_leaves_until_open(authenticated_client):
    response = authenticated_client.post(
        f"{ROOT}{UNIFIED}/collect/",
        {"until": None},
        format="json",
    )

    assert response.status_code == 202
    task_data = response.json()["task_data"]
    assert task_data["collector"] == UNIFIED
    assert task_data["since"] is not None
    assert "until" not in task_data


def test_collect_rejects_invalid_since(authenticated_client):
    response = authenticated_client.post(
        f"{ROOT}{UNIFIED}/collect/",
        {"since": "not-a-date"},
        format="json",
    )

    assert response.status_code == 400


def test_collect_rejects_configured_source(authenticated_client):
    response = authenticated_client.post(
        f"{ROOT}{CONFIG}/collect/",
        {"source": "controller"},
        format="json",
    )

    assert response.status_code == 400


def test_collect_get_triggers_previous_and_schedules_current_window(authenticated_client):
    now = datetime(2026, 8, 17, 10, 30, tzinfo=UTC)

    with patch("apps.analytics.v1.views.timezone.now", return_value=now):
        response = authenticated_client.get(f"{ROOT}{UNIFIED}/collect/")

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    demand = body["collection_demand"]
    assert demand["previous"]["action"] == "triggered"
    assert demand["current"]["action"] == "scheduled"
    assert demand["current"]["scheduled_time"] == "2026-08-17T11:00:00Z"
    assert demand["previous"]["task_url"].endswith(f"/api/v1/tasks/{demand['previous']['task_id']}/")
    assert demand["current"]["task_url"].endswith(f"/api/v1/tasks/{demand['current']['task_id']}/")

    tasks = list(Task.objects.order_by("id"))
    assert len(tasks) == 2
    assert tasks[0].task_data == {
        "collector": UNIFIED,
        "since": "2026-08-17T09:00:00+00:00",
        "until": "2026-08-17T10:00:00+00:00",
    }
    assert tasks[1].task_data == {
        "collector": UNIFIED,
        "since": "2026-08-17T10:00:00+00:00",
        "until": "2026-08-17T11:00:00+00:00",
    }


def test_collect_get_does_not_duplicate_existing_current_task(authenticated_client):
    now = datetime(2026, 8, 17, 10, 30, tzinfo=UTC)
    current_since = datetime(2026, 8, 17, 10, tzinfo=UTC)
    current_until = datetime(2026, 8, 17, 11, tzinfo=UTC)
    Task.objects.create(
        name="existing-demand",
        description="",
        function_name="collect_analytics_on_demand",
        task_data={
            "collector": UNIFIED,
            "since": current_since.isoformat(),
            "until": current_until.isoformat(),
        },
        status="pending",
    )
    _row(UNIFIED, datetime(2026, 8, 17, 9, tzinfo=UTC), datetime(2026, 8, 17, 10, tzinfo=UTC))

    with patch("apps.analytics.v1.views.timezone.now", return_value=now):
        response = authenticated_client.get(f"{ROOT}{UNIFIED}/collect/")

    assert response.status_code == 200
    demand = response.json()["collection_demand"]
    assert demand["previous"]["action"] == "already_collected"
    assert demand["current"]["action"] == "existing_task"
    assert Task.objects.filter(function_name="collect_analytics_on_demand").count() == 1


def test_collect_get_does_not_treat_overlapping_custom_window_as_match(authenticated_client):
    now = datetime(2026, 8, 17, 10, 30, tzinfo=UTC)
    Task.objects.create(
        name="custom-overlap",
        description="",
        function_name="collect_analytics_on_demand",
        task_data={
            "collector": UNIFIED,
            "since": "2026-08-17T09:30:00+00:00",
            "until": "2026-08-17T10:30:00+00:00",
        },
        status="pending",
    )

    with patch("apps.analytics.v1.views.timezone.now", return_value=now):
        response = authenticated_client.get(f"{ROOT}{UNIFIED}/collect/")

    assert response.status_code == 200
    demand = response.json()["collection_demand"]
    assert demand["previous"]["action"] == "triggered"
    assert demand["current"]["action"] == "scheduled"
    assert Task.objects.filter(function_name="collect_analytics_on_demand").count() == 3


def test_collect_get_is_idempotent_for_sequential_requests(authenticated_client):
    now = datetime(2026, 8, 17, 10, 30, tzinfo=UTC)

    with patch("apps.analytics.v1.views.timezone.now", return_value=now):
        first = authenticated_client.get(f"{ROOT}{UNIFIED}/collect/")
        second = authenticated_client.get(f"{ROOT}{UNIFIED}/collect/")

    assert first.status_code == second.status_code == 200
    demand = second.json()["collection_demand"]
    assert demand["previous"]["action"] == "existing_task"
    assert demand["current"]["action"] == "existing_task"
    assert Task.objects.filter(function_name="collect_analytics_on_demand").count() == 2


def test_collect_get_uses_cron_for_current_but_catches_up_previous(authenticated_client):
    now = datetime(2026, 8, 17, 10, 30, tzinfo=UTC)
    Task.objects.create(
        name="hourly-unified-jobs",
        description="",
        function_name="collect_hourly_metrics",
        task_data={"collector_type": "unified_jobs"},
        cron_expression="5 * * * *",
        status="pending",
    )

    with patch("apps.analytics.v1.views.timezone.now", return_value=now):
        response = authenticated_client.get(f"{ROOT}{UNIFIED}/collect/")

    assert response.status_code == 200
    demand = response.json()["collection_demand"]
    assert demand["previous"]["action"] == "triggered"
    assert demand["current"]["action"] == "cron_covered"
    assert Task.objects.filter(function_name="collect_analytics_on_demand").count() == 1


def test_collect_get_snapshot_runs_once_per_24_hours(authenticated_client):
    now = datetime(2026, 8, 17, 10, 30, tzinfo=UTC)
    started = now - timedelta(hours=2)
    AnalyticsPayload.objects.create(
        collector=CONFIG,
        started_at=started,
        finished_at=started + timedelta(minutes=1),
        payload={"v": 1},
    )

    with patch("apps.analytics.v1.views.timezone.now", return_value=now):
        response = authenticated_client.get(f"{ROOT}{CONFIG}/collect/")

    assert response.status_code == 200
    assert response.json()["collection_demand"]["snapshot"]["action"] == "already_collected"
    assert not Task.objects.exists()


def test_collect_get_snapshot_creates_immediate_task_when_stale(authenticated_client):
    now = datetime(2026, 8, 17, 10, 30, tzinfo=UTC)
    old = now - timedelta(days=1, minutes=1)
    AnalyticsPayload.objects.create(
        collector=CONFIG,
        started_at=old,
        finished_at=old,
        payload={"v": 1},
    )

    with patch("apps.analytics.v1.views.timezone.now", return_value=now):
        response = authenticated_client.get(f"{ROOT}{CONFIG}/collect/")

    assert response.status_code == 200
    demand = response.json()["collection_demand"]["snapshot"]
    assert demand["action"] == "triggered"
    assert demand["task_url"].endswith(f"/api/v1/tasks/{demand['task_id']}/")
    assert Task.objects.get().task_data == {"collector": CONFIG}


def test_collect_get_unknown_collector_and_invalid_window_are_rejected(authenticated_client):
    assert authenticated_client.get(f"{ROOT}nope.nope/collect/").status_code == 404

    response = authenticated_client.get(f"{ROOT}{UNIFIED}/collect/?since=not-a-date")

    assert response.status_code == 400


def test_collect_get_daily_triggers_previous_and_schedules_current(authenticated_client):
    now = datetime(2026, 8, 18, 1, 30, tzinfo=UTC)

    with patch("apps.analytics.v1.views.timezone.now", return_value=now):
        response = authenticated_client.get(f"{ROOT}{DAILY}/collect/")

    assert response.status_code == 200
    demand = response.json()["collection_demand"]
    assert demand["previous"]["action"] == "triggered"
    assert demand["current"]["action"] == "scheduled"
    assert demand["current"]["scheduled_time"] == "2026-08-19T00:00:00Z"


def test_collect_get_suppresses_demand_for_unresolvable_task(authenticated_client):
    Task.objects.create(
        name="malformed-hourly-task",
        description="",
        function_name="collect_hourly_metrics",
        task_data={"collector_type": "unified_jobs", "hour_timestamp": "invalid"},
        status="pending",
    )

    with patch("apps.analytics.v1.views.timezone.now", return_value=datetime(2026, 8, 17, 10, 30, tzinfo=UTC)):
        response = authenticated_client.get(f"{ROOT}{UNIFIED}/collect/")

    assert response.status_code == 200
    demand = response.json()["collection_demand"]
    assert demand["previous"] == {"action": "suppressed", "reason": "unresolved_task_metadata"}
    assert demand["current"] == {"action": "suppressed", "reason": "unresolved_task_metadata"}
    assert Task.objects.filter(function_name="collect_analytics_on_demand").count() == 0


def test_collect_get_ignores_demand_for_another_collector(authenticated_client):
    Task.objects.create(
        name="other-collector-demand",
        description="",
        function_name="collect_analytics_on_demand",
        task_data={"collector": CONFIG},
        status="pending",
    )

    with patch("apps.analytics.v1.views.timezone.now", return_value=datetime(2026, 8, 17, 10, 30, tzinfo=UTC)):
        response = authenticated_client.get(f"{ROOT}{UNIFIED}/collect/")

    assert response.status_code == 200
    demand = response.json()["collection_demand"]
    assert demand["previous"]["action"] == "triggered"
    assert demand["current"]["action"] == "scheduled"


def test_collect_get_snapshot_reuses_recent_snapshot_task(authenticated_client):
    Task.objects.create(
        name="other-collector-demand",
        description="",
        function_name="collect_analytics_on_demand",
        task_data={"collector": UNIFIED},
        status="pending",
    )
    Task.objects.create(
        name="recent-snapshot",
        description="",
        function_name="collect_snapshot_metrics",
        task_data={"collector_type": "config", "collection_timestamp": "2026-08-16T23:00:00Z"},
        status="pending",
    )

    with patch("apps.analytics.v1.views.timezone.now", return_value=datetime(2026, 9, 30, 10, 30, tzinfo=UTC)):
        response = authenticated_client.get(f"{ROOT}{CONFIG}/collect/")

    assert response.status_code == 200
    assert response.json()["collection_demand"]["snapshot"]["action"] == "existing_task"
    assert Task.objects.filter(function_name="collect_analytics_on_demand").count() == 1


def test_collect_get_snapshot_suppresses_unresolvable_snapshot_task(authenticated_client):
    Task.objects.create(
        name="malformed-snapshot",
        description="",
        function_name="collect_snapshot_metrics",
        task_data={"collector_type": "config", "collection_timestamp": "invalid"},
        status="pending",
    )

    with patch("apps.analytics.v1.views.timezone.now", return_value=datetime(2026, 9, 30, 10, 30, tzinfo=UTC)):
        response = authenticated_client.get(f"{ROOT}{CONFIG}/collect/")

    assert response.status_code == 200
    assert response.json()["collection_demand"]["snapshot"] == {
        "action": "suppressed",
        "reason": "unresolved_task_metadata",
    }
    assert not Task.objects.filter(function_name="collect_analytics_on_demand").exists()


def test_collect_post_rejects_unknown_snapshot_bounds_and_reversed_windows(authenticated_client):
    unknown = authenticated_client.post(f"{ROOT}nope.nope/collect/", {}, format="json")
    snapshot = authenticated_client.post(f"{ROOT}{CONFIG}/collect/", {"since": "2026-08-17T00:00:00Z"}, format="json")
    reversed_window = authenticated_client.post(
        f"{ROOT}{UNIFIED}/collect/",
        {"since": "2026-08-17T11:00:00Z", "until": "2026-08-17T10:00:00Z"},
        format="json",
    )

    assert unknown.status_code == 404
    assert snapshot.status_code == 400
    assert reversed_window.status_code == 400


def test_collect_get_handles_rows_response_error(authenticated_client):
    error = Response({"detail": "invalid"}, status=400)

    with (
        patch.object(views.CollectorCollectView, "_schedule_demand", return_value={}),
        patch("apps.analytics.v1.views._rows_response", return_value=error),
    ):
        response = authenticated_client.get(f"{ROOT}{UNIFIED}/collect/")

    assert response.status_code == 400


def test_rows_response_returns_validation_error():
    request = APIRequestFactory().get(f"{ROOT}{UNIFIED}/?since=not-a-date")
    error = Response({"detail": "invalid"}, status=400)

    with patch("apps.analytics.v1.views._validate_rows_request", return_value=error):
        response = views._rows_response(request, UNIFIED)

    assert response is error
