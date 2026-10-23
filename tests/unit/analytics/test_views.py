"""Tests for the read-only analytics API."""

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics.models import AnalyticsPayload, APIUsageCounter
from apps.analytics.v1.views import _fail_stale
from apps.tasks.models import Task, TaskExecution

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

ROOT = "/api/v1/analytics/"
UNIFIED = "controller.unified_jobs_dashboard"
CONFIG = "controller.config"
INSTANCE_INFO = "controller.instance_info"


def _row(collector, since, until, payload=None, cluster_id=None):
    started = datetime(2026, 8, 17, 10, tzinfo=UTC)
    return AnalyticsPayload.objects.create(
        collector=collector,
        cluster_id=cluster_id,
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
        "execution environment, launcher, labels, and host count. The nested installed_collections "
        "object is keyed by collection FQCN."
    )
    assert unified["payload_shape"] == "array"
    assert unified["key_field"] is None
    config = next(collector for collector in response.json()["collectors"] if collector["name"] == CONFIG)
    assert config["payload_shape"] == "object"
    assert config["key_field"] is None
    # A collector keyed by data reports what its top-level keys mean; the two object shapes
    # are only distinguishable by that value.
    instance_info = next(collector for collector in response.json()["collectors"] if collector["name"] == INSTANCE_INFO)
    assert instance_info["payload_shape"] == "object"
    assert instance_info["key_field"] == "uuid"
    assert "service.task_executions_service" not in names
    assert "dashboard.dashboard_jobs" not in names
    assert all(
        collector["rows_url"].startswith("http://testserver/api/v1/analytics/")
        for collector in response.json()["collectors"]
    )
    assert all(
        collector["collect_url"].endswith(f"/api/v1/analytics/{collector['name']}/collect/")
        for collector in response.json()["collectors"]
    )
    assert all("last_collect" in collector for collector in response.json()["collectors"])
    assert all(collector["last_collect"] is None for collector in response.json()["collectors"])


def test_root_reports_latest_finished_collection_per_collector(authenticated_client):
    older = _row(CONFIG, None, None)
    newer = _row(CONFIG, None, None)
    _row(UNIFIED, datetime(2026, 8, 17, 10, tzinfo=UTC), datetime(2026, 8, 17, 11, tzinfo=UTC))

    older.finished_at = datetime(2026, 8, 17, 10, 1, tzinfo=UTC)
    older.save(update_fields=["finished_at"])
    newer.finished_at = datetime(2026, 8, 17, 10, 3, tzinfo=UTC)
    newer.save(update_fields=["finished_at"])

    response = authenticated_client.get(ROOT)

    assert response.status_code == 200
    collectors = {collector["name"]: collector for collector in response.json()["collectors"]}
    assert collectors[CONFIG]["last_collect"] == "2026-08-17T10:03:00Z"
    assert collectors[UNIFIED]["last_collect"] == "2026-08-17T10:00:01Z"


def test_root_browsable_response_links_collector_urls(authenticated_client):
    response = authenticated_client.get(ROOT, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert 'href="http://testserver/api/v1/analytics/controller.config/"' in response.text
    assert "accepts_since_until" in response.text
    assert "payload_shape" in response.text
    assert "key_field" in response.text
    assert "collect_url" in response.text


def test_openapi_associates_every_enabled_collector_with_a_payload_schema():
    from drf_spectacular.generators import SchemaGenerator

    from apps.analytics.registry import enabled_collectors

    schema = SchemaGenerator().get_schema(request=None, public=True)
    operation = schema["paths"]["/api/v1/analytics/{collector}/"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    components = schema["components"]["schemas"]
    result_schema = components["AnalyticsPayloadByCollector"]

    assert response_schema["$ref"] == "#/components/schemas/PaginatedAnalyticsPayloadList"
    assert result_schema["discriminator"]["propertyName"] == "collector"
    assert set(result_schema["discriminator"]["mapping"]) == set(enabled_collectors())
    assert all(ref["$ref"].split("/")[-1] in components for ref in result_schema["oneOf"])
    assert all(
        entry.payload_schema.name in components
        for entry in enabled_collectors().values()
        if entry.payload_schema.kind == "array"
    )
    assert {parameter["name"] for parameter in operation["parameters"]} >= {"page", "page_size", "since", "until"}


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


def test_api_requests_are_counted_for_successful_and_failed_responses(authenticated_client):
    usage_date = timezone.now().date()

    unauthorized_response = APIClient().get(ROOT)
    discovery_response = authenticated_client.get(ROOT)
    rows_response = authenticated_client.get(f"{ROOT}nope.nope/")
    collect_response = authenticated_client.post(f"{ROOT}{CONFIG}/collect/", {}, format="json")

    assert unauthorized_response.status_code in (401, 403)
    assert discovery_response.status_code == 200
    assert rows_response.status_code == 404
    assert collect_response.status_code == 202

    summary = APIUsageCounter.daily_summary(usage_date)
    assert summary["total_requests"] == 4
    assert summary["by_endpoint"]["analytics:v1:root"]["4xx"] == 1
    assert summary["by_endpoint"]["analytics:v1:root"]["2xx"] == 1
    assert summary["by_endpoint"]["analytics:v1:rows"]["4xx"] == 1
    assert summary["by_endpoint"]["analytics:v1:collect"]["2xx"] == 1


def test_api_preflight_requests_are_counted():
    usage_date = timezone.now().date()

    response = APIClient().options(ROOT)

    assert response.status_code in (200, 403)
    status_class = response.status_code // 100
    summary = APIUsageCounter.daily_summary(usage_date)
    assert summary["total_requests"] == 1
    assert summary["by_endpoint"]["analytics:v1:root"][f"{status_class}xx"] == 1


def test_rows_return_collection_envelope(authenticated_client):
    _row(
        UNIFIED,
        datetime(2026, 8, 17, 10, tzinfo=UTC),
        datetime(2026, 8, 17, 11, tzinfo=UTC),
        {"v": 1},
        cluster_id="2aebf27a-42ee-4e15-93d0-8bd5f9b52219",
    )

    response = authenticated_client.get(f"{ROOT}{UNIFIED}/")

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["collector"] == UNIFIED
    assert result["source"] == "local"
    assert result["cluster_id"] == "2aebf27a-42ee-4e15-93d0-8bd5f9b52219"
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
    assert task.max_attempts == 1
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


def _collect(client, collector, body=None):
    """POST a collection request for one collector."""
    return client.post(f"{ROOT}{collector}/collect/", body or {}, format="json")


@pytest.mark.parametrize(
    ("collector", "body"),
    [
        (CONFIG, {}),
        (UNIFIED, {}),
        (UNIFIED, {"since": "2026-08-17T10:00:00Z", "until": "2026-08-17T11:00:00Z"}),
    ],
)
def test_collect_repeated_request_returns_same_task(authenticated_client, collector, body):
    """Repeats of one resolved window share a task, for snapshots and windows."""
    first = _collect(authenticated_client, collector, body)
    second = _collect(authenticated_client, collector, body)

    assert first.status_code == 202
    assert first.json()["disposition"] == "created"
    assert second.status_code == 200
    assert second.json()["disposition"] == "reused"
    assert second.json()["task_id"] == first.json()["task_id"]
    assert Task.objects.filter(function_name="collect_analytics_on_demand").count() == 1


def test_collect_equivalent_timestamp_offsets_are_the_same_window(authenticated_client):
    """The same instant in different UTC offsets is one idempotency key."""
    first = _collect(
        authenticated_client,
        UNIFIED,
        {"since": "2026-08-17T10:00:00Z", "until": "2026-08-17T11:00:00Z"},
    )
    second = _collect(
        authenticated_client,
        UNIFIED,
        {"since": "2026-08-17T12:00:00+02:00", "until": "2026-08-17T13:00:00+02:00"},
    )

    assert second.status_code == 200
    assert second.json()["task_id"] == first.json()["task_id"]
    assert second.json()["task_data"]["since"] == "2026-08-17T10:00:00+00:00"


def test_collect_reuses_completed_task(authenticated_client):
    """A completed window is reused instead of re-collected."""
    first = _collect(authenticated_client, UNIFIED)
    Task.objects.filter(pk=first.json()["task_id"]).update(status="completed")

    second = _collect(authenticated_client, UNIFIED)

    assert second.status_code == 200
    assert second.json()["task_status"] == "completed"
    assert Task.objects.filter(function_name="collect_analytics_on_demand").count() == 1


def test_collect_unbounded_window_does_not_match_a_bounded_task(authenticated_client):
    """Exact task_data matching, not JSON containment, selects the window."""
    bounded = _collect(
        authenticated_client,
        UNIFIED,
        {"since": "2026-08-17T10:00:00Z", "until": "2026-08-17T11:00:00Z"},
    )
    Task.objects.filter(pk=bounded.json()["task_id"]).update(status="completed")

    unbounded = _collect(authenticated_client, UNIFIED, {"since": None, "until": None})

    assert unbounded.status_code == 202
    assert unbounded.json()["disposition"] == "created"
    assert unbounded.json()["task_id"] != bounded.json()["task_id"]


def test_collect_requeues_failed_task(authenticated_client):
    """A failed task for the same window is requeued in place."""
    first = _collect(authenticated_client, UNIFIED)
    task = Task.objects.get(pk=first.json()["task_id"])
    Task.objects.filter(pk=task.pk).update(status="failed", error_message="boom")

    second = _collect(authenticated_client, UNIFIED)

    assert second.status_code == 202
    assert second.json()["disposition"] == "requeued"
    assert second.json()["task_id"] == task.pk
    task.refresh_from_db()
    assert task.status == "pending"
    assert task.error_message == ""
    assert Task.objects.filter(function_name="collect_analytics_on_demand").count() == 1


def test_collect_recovers_stale_running_task(authenticated_client):
    """A stuck task and its execution are failed, then requeued."""
    first = _collect(authenticated_client, UNIFIED)
    task = Task.objects.get(pk=first.json()["task_id"])
    Task.objects.filter(pk=task.pk).update(status="running", started_at=timezone.now() - timedelta(hours=2))
    execution = TaskExecution.objects.create(task=task, status="running")

    second = _collect(authenticated_client, UNIFIED)

    assert second.status_code == 202
    assert second.json()["disposition"] == "requeued"
    task.refresh_from_db()
    execution.refresh_from_db()
    assert task.status == "pending"
    assert execution.status == "failed"
    assert Task.objects.filter(function_name="collect_analytics_on_demand").count() == 1


def test_fail_stale_requires_a_running_overdue_task():
    """Recovery rechecks status and age under the task lock."""
    now = timezone.now()
    overdue = Task.objects.create(
        name="overdue-collect",
        function_name="collect_analytics_on_demand",
        task_data={"collector": UNIFIED},
        status="running",
        started_at=now - timedelta(hours=2),
    )
    execution = TaskExecution.objects.create(task=overdue, status="running")
    completed = Task.objects.create(
        name="completed-collect",
        function_name="collect_analytics_on_demand",
        task_data={"collector": UNIFIED},
        status="completed",
        started_at=now - timedelta(hours=2),
    )
    fresh = Task.objects.create(
        name="fresh-collect",
        function_name="collect_analytics_on_demand",
        task_data={"collector": UNIFIED},
        status="running",
        started_at=now,
    )

    assert _fail_stale(overdue, now) is True
    assert _fail_stale(completed, now) is False
    assert _fail_stale(fresh, now) is False

    overdue.refresh_from_db()
    execution.refresh_from_db()
    assert overdue.status == "pending"
    assert execution.status == "failed"


def test_collect_conflicts_with_a_different_window_in_flight(authenticated_client):
    """A second window is rejected while one is pending or running."""
    first = _collect(
        authenticated_client,
        UNIFIED,
        {"since": "2026-08-17T10:00:00Z", "until": "2026-08-17T11:00:00Z"},
    )

    second = _collect(
        authenticated_client,
        UNIFIED,
        {"since": "2026-08-17T11:00:00Z", "until": "2026-08-17T12:00:00Z"},
    )

    assert second.status_code == 409
    assert second.json()["task_id"] == first.json()["task_id"]
    assert Task.objects.filter(function_name="collect_analytics_on_demand").count() == 1


def test_collect_does_not_requeue_a_failed_window_while_another_is_in_flight(authenticated_client):
    """Requeueing a failed window must not overlap a live collection."""
    failed = _collect(
        authenticated_client,
        UNIFIED,
        {"since": "2026-08-17T10:00:00Z", "until": "2026-08-17T11:00:00Z"},
    )
    Task.objects.filter(pk=failed.json()["task_id"]).update(status="failed")
    live = _collect(
        authenticated_client,
        UNIFIED,
        {"since": "2026-08-17T11:00:00Z", "until": "2026-08-17T12:00:00Z"},
    )
    assert live.status_code == 202

    retry = _collect(
        authenticated_client,
        UNIFIED,
        {"since": "2026-08-17T10:00:00Z", "until": "2026-08-17T11:00:00Z"},
    )

    assert retry.status_code == 409
    assert retry.json()["task_id"] == live.json()["task_id"]
    assert Task.objects.get(pk=failed.json()["task_id"]).status == "failed"


def test_collect_reuses_completed_window_while_another_is_in_flight(authenticated_client):
    """Reuse starts no work, so a live sibling window does not conflict."""
    completed = _collect(
        authenticated_client,
        UNIFIED,
        {"since": "2026-08-17T10:00:00Z", "until": "2026-08-17T11:00:00Z"},
    )
    Task.objects.filter(pk=completed.json()["task_id"]).update(status="completed")
    other = _collect(
        authenticated_client,
        UNIFIED,
        {"since": "2026-08-17T11:00:00Z", "until": "2026-08-17T12:00:00Z"},
    )
    assert other.status_code == 202

    repeat = _collect(
        authenticated_client,
        UNIFIED,
        {"since": "2026-08-17T10:00:00Z", "until": "2026-08-17T11:00:00Z"},
    )

    assert repeat.status_code == 200
    assert repeat.json()["disposition"] == "reused"
    assert repeat.json()["task_id"] == completed.json()["task_id"]


def test_collect_recreates_a_cancelled_task(authenticated_client):
    """Cancelled work cannot be revived, so a new task is created."""
    first = _collect(authenticated_client, UNIFIED)
    Task.objects.filter(pk=first.json()["task_id"]).update(status="cancelled")

    second = _collect(authenticated_client, UNIFIED)

    assert second.status_code == 202
    assert second.json()["disposition"] == "created"
    assert second.json()["task_id"] != first.json()["task_id"]


def test_collect_disabled_collector_returns_410(authenticated_client):
    """Known but disabled collectors are not collectable."""
    response = _collect(authenticated_client, "service.task_executions_service")

    assert response.status_code == 410
    assert not Task.objects.filter(function_name="collect_analytics_on_demand").exists()
