"""Tests for Analytics API request usage middleware."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.urls import resolve
from django.utils import timezone

from apps.analytics.middleware import AnalyticsAPIUsageMiddleware, record_analytics_api_request
from apps.analytics.models import AnalyticsAPIUsageCounter

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

ROOT = "/api/v1/analytics/"
CONFIG = "controller.config"


@pytest.mark.parametrize(
    ("method", "path", "status_code", "operation"),
    [
        ("GET", ROOT, 200, "discovery"),
        ("GET", ROOT, 401, "discovery"),
        ("GET", f"{ROOT}{CONFIG}/", 302, "rows"),
        ("GET", f"{ROOT}unknown.collector/", 404, "rows"),
        ("POST", f"{ROOT}{CONFIG}/collect/", 202, "collect"),
        ("DELETE", f"{ROOT}{CONFIG}/collect/", 500, "collect"),
    ],
)
def test_middleware_counts_resolved_analytics_api_requests_by_status_class(method, path, status_code, operation):
    request = RequestFactory().generic(method, path)
    request.resolver_match = resolve(path)
    expected_date = timezone.now().date()
    middleware = AnalyticsAPIUsageMiddleware(lambda _request: HttpResponse(status=status_code))

    response = middleware(request)

    assert response.status_code == status_code
    counter = AnalyticsAPIUsageCounter.objects.get(
        usage_date=expected_date,
        operation=operation,
        status_class=status_code // 100,
    )
    assert counter.request_count == 1


def test_middleware_ignores_unrelated_routes():
    request = RequestFactory().get("/api/v1/tasks/")
    request.resolver_match = SimpleNamespace(view_name="tasks:v1:task-list")
    middleware = AnalyticsAPIUsageMiddleware(lambda _request: HttpResponse(status=200))

    middleware(request)

    assert not AnalyticsAPIUsageCounter.objects.exists()


def test_counter_write_failure_does_not_change_api_response():
    request = RequestFactory().get(ROOT)
    request.resolver_match = resolve(ROOT)
    middleware = AnalyticsAPIUsageMiddleware(lambda _request: HttpResponse(status=503))

    with patch.object(AnalyticsAPIUsageCounter, "record_request", side_effect=RuntimeError("db unavailable")):
        response = middleware(request)

    assert response.status_code == 503


@override_settings(URL_PREFIX="/api/metrics")
def test_preflight_request_resolves_operation_with_service_url_prefix():
    request = RequestFactory().options("/api/metrics/v1/analytics/")
    usage_date = timezone.now().date()

    record_analytics_api_request(request, 200)

    counter = AnalyticsAPIUsageCounter.objects.get(
        usage_date=usage_date,
        operation="discovery",
        status_class=2,
    )
    assert counter.request_count == 1


def test_counter_increment_uses_atomic_addition_for_repeated_calls():
    usage_date = datetime(2026, 8, 17, tzinfo=UTC).date()

    for _ in range(10):
        AnalyticsAPIUsageCounter.record_request(usage_date, "rows", 2)

    counter = AnalyticsAPIUsageCounter.objects.get(usage_date=usage_date, operation="rows", status_class=2)
    assert counter.request_count == 10
