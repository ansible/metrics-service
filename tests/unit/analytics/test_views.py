"""Tests for the read-only analytics API."""

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.analytics.models import AnalyticsPayload

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

ROOT = "/api/v1/analytics/"
UNIFIED = "controller.unified_jobs_dashboard"
CONFIG = "controller.config"


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
    assert "service.task_executions_service" not in names
    assert all("collect_url" not in collector for collector in response.json()["collectors"])
    assert all(
        collector["rows_url"].startswith("http://testserver/api/v1/analytics/")
        for collector in response.json()["collectors"]
    )


def test_root_browsable_response_links_collector_urls(authenticated_client):
    response = authenticated_client.get(ROOT, HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert 'href="http://testserver/api/v1/analytics/controller.config/"' in response.text


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


def test_collect_route_is_not_exposed(authenticated_client):
    assert authenticated_client.post(f"{ROOT}{UNIFIED}/collect/", {}, format="json").status_code == 404
