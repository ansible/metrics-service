"""Tests for analytics Prometheus usage telemetry."""

import os
import subprocess
import sys
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import ProxyHandler, Request

import jwt
import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics.registry import CollectorEntry, get_entry
from apps.analytics.telemetry import (
    _open_metrics_endpoint,
    aggregate_analytics_usage,
    daily_analytics_usage_delta,
    record_collector_get,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_production_metrics_endpoint_aggregates_workers_and_preserves_default_collectors(
    tmp_path, authenticated_client
):
    child_code = """
import apps.settings.production
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'metrics_service.settings')
import django
django.setup()
from apps.analytics.telemetry import ANALYTICS_REQUESTS
ANALYTICS_REQUESTS.labels(collector='controller.config').inc()
"""
    environment = os.environ.copy()
    environment["METRICS_SERVICE_MODE"] = "test"
    environment["METRICS_SERVICE_PROMETHEUS_MULTIPROC_DIR"] = str(tmp_path)
    environment.pop("PROMETHEUS_MULTIPROC_DIR", None)
    environment.pop("prometheus_multiproc_dir", None)
    repository_root = Path(__file__).resolve().parents[3]

    for _ in range(2):
        subprocess.run([sys.executable, "-c", child_code], cwd=repository_root, env=environment, check=True)

    with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}):
        response = authenticated_client.get("/api/v1/metrics")

    assert response.status_code == 200
    assert b'analytics_collector_get_requests_total{collector="controller.config"} 2.0' in response.content
    assert b"python_info" in response.content


def test_metrics_http_opener_bypasses_proxies_and_redirects():
    request = Request("http://metrics-web:8000/api/v1/metrics")
    with patch("apps.analytics.telemetry.build_opener") as build_opener:
        _open_metrics_endpoint(request, timeout=5)

    proxy_handler, redirect_handler = build_opener.call_args.args
    assert isinstance(proxy_handler, ProxyHandler)
    assert proxy_handler.proxies == {}
    assert redirect_handler.redirect_request(request, None, 301, "Moved", {}, "http://other/metrics") is None
    build_opener.return_value.open.assert_called_once_with(request, timeout=5)


def test_record_collector_get_uses_canonical_public_name():
    with (
        patch("apps.analytics.telemetry.ANALYTICS_REQUESTS") as requests,
        patch("apps.analytics.telemetry.ANALYTICS_REQUEST_DURATION") as duration,
    ):
        record_collector_get(get_entry("controller.config"), 12.5)

    requests.labels.assert_called_once_with(collector="controller.config")
    requests.labels.return_value.inc.assert_called_once_with()
    duration.labels.assert_called_once_with(collector="controller.config")
    duration.labels.return_value.observe.assert_called_once_with(12.5)


def test_record_collector_get_rejects_disabled_entry():
    entry = CollectorEntry("controller.disabled", collector_type="disabled", mode="hourly", enabled=False)
    with (
        patch("apps.analytics.telemetry.ANALYTICS_REQUESTS") as requests,
        patch("apps.analytics.telemetry.ANALYTICS_REQUEST_DURATION") as duration,
    ):
        record_collector_get(entry, 12.5)

    requests.labels.assert_not_called()
    duration.labels.assert_not_called()


def test_record_collector_get_swallows_metric_failure():
    with (
        patch("apps.analytics.telemetry.ANALYTICS_REQUESTS.labels", side_effect=RuntimeError("registry down")),
        patch("apps.analytics.telemetry.logger.exception") as log_exception,
    ):
        record_collector_get(get_entry("controller.config"), 12.5)

    log_exception.assert_called_once()


def test_recorded_metrics_are_visible_through_existing_export(authenticated_client):
    record_collector_get(get_entry("controller.config"), 12.5)

    response = authenticated_client.get("/api/v1/metrics")

    assert response.status_code == 200
    assert b"analytics_collector_get_requests_total" in response.content
    assert b'collector="controller.config"' in response.content


def test_metrics_endpoint_accepts_local_service_token():
    token = jwt.encode(
        {
            "iss": "test-service-id",
            "exp": timezone.now() + timedelta(minutes=1),
        },
        settings.RESOURCE_SERVER["SECRET_KEY"],
        algorithm=settings.RESOURCE_SERVER.get("JWT_ALGORITHM", "HS256"),
    )

    with patch("apps.core.authentication.service_id", return_value="test-service-id"):
        response = APIClient().get("/api/v1/metrics", HTTP_X_ANSIBLE_SERVICE_AUTH=token)

    assert response.status_code == 200


def test_metrics_endpoint_remains_protected_from_anonymous_clients(api_client):
    assert api_client.get("/api/v1/metrics").status_code in (401, 403)


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "test-service-id", "exp": timezone.now() - timedelta(minutes=1)},
        {"iss": "other-service-id", "exp": timezone.now() + timedelta(minutes=1)},
    ],
)
def test_metrics_endpoint_rejects_invalid_or_foreign_service_tokens(claims):
    token = jwt.encode(
        claims,
        settings.RESOURCE_SERVER["SECRET_KEY"],
        algorithm=settings.RESOURCE_SERVER.get("JWT_ALGORITHM", "HS256"),
    )

    with patch("apps.core.authentication.service_id", return_value="test-service-id"):
        response = APIClient().get("/api/v1/metrics", HTTP_X_ANSIBLE_SERVICE_AUTH=token)

    assert response.status_code in (401, 403)


def test_aggregate_analytics_usage_scrapes_internal_endpoint_with_service_token():
    exposition = b"""# HELP analytics_collector_get_requests_total requests
# TYPE analytics_collector_get_requests_total counter
analytics_collector_get_requests_total{collector="controller.config"} 2.0
# HELP analytics_collector_get_duration_milliseconds duration
# TYPE analytics_collector_get_duration_milliseconds histogram
analytics_collector_get_duration_milliseconds_count{collector="controller.config"} 2.0
analytics_collector_get_duration_milliseconds_sum{collector="controller.config"} 31.0
"""

    with (
        override_settings(INTERNAL_PROMETHEUS_URL="http://metrics-web:8000/api/v1/metrics"),
        patch("apps.analytics.telemetry.get_service_token", return_value="internal-token"),
        patch("apps.analytics.telemetry._open_metrics_endpoint", return_value=BytesIO(exposition)) as open_endpoint,
    ):
        result = aggregate_analytics_usage()

    request = open_endpoint.call_args.args[0]
    assert request.full_url == "http://metrics-web:8000/api/v1/metrics"
    assert request.get_header("X-ansible-service-auth") == "internal-token"
    assert result == {
        "controller.config": {
            "request_count": 2,
            "duration_ms_total": 31.0,
            "duration_sample_count": 2,
        }
    }


def test_aggregate_analytics_usage_rejects_sensitive_or_unknown_labels():
    exposition = b"""# TYPE analytics_collector_get_requests_total counter
analytics_collector_get_requests_total{collector="controller.config",organization="secret"} 4.0
analytics_collector_get_requests_total{collector="customer-supplied"} 3.0
"""

    with (
        override_settings(INTERNAL_PROMETHEUS_URL="http://metrics-web:8000/api/v1/metrics"),
        patch("apps.analytics.telemetry.get_service_token", return_value="internal-token"),
        patch("apps.analytics.telemetry._open_metrics_endpoint", return_value=BytesIO(exposition)),
    ):
        result = aggregate_analytics_usage()

    assert result == {}


def test_aggregate_analytics_usage_returns_empty_for_no_samples():
    with (
        override_settings(INTERNAL_PROMETHEUS_URL="http://metrics-web:8000/api/v1/metrics"),
        patch("apps.analytics.telemetry.get_service_token", return_value="internal-token"),
        patch(
            "apps.analytics.telemetry._open_metrics_endpoint",
            return_value=BytesIO(b"# TYPE unrelated gauge\nunrelated 1\n"),
        ),
    ):
        assert aggregate_analytics_usage() == {}


def test_aggregate_analytics_usage_returns_none_on_scrape_failure():
    with (
        override_settings(INTERNAL_PROMETHEUS_URL="http://metrics-web:8000/api/v1/metrics"),
        patch("apps.analytics.telemetry.get_service_token", return_value="internal-token"),
        patch("apps.analytics.telemetry._open_metrics_endpoint", side_effect=URLError("scrape failed")),
        patch("apps.analytics.telemetry.logger.exception") as log_exception,
    ):
        result = aggregate_analytics_usage()

    assert result is None
    log_exception.assert_called_once()


def test_aggregate_analytics_usage_returns_none_without_endpoint_url():
    with override_settings(INTERNAL_PROMETHEUS_URL=""):
        assert aggregate_analytics_usage() is None


def test_aggregate_analytics_usage_rejects_non_http_urls():
    with (
        override_settings(INTERNAL_PROMETHEUS_URL="file:///etc/passwd"),
        patch("apps.analytics.telemetry._open_metrics_endpoint") as open_endpoint,
    ):
        assert aggregate_analytics_usage() is None

    open_endpoint.assert_not_called()


def test_daily_analytics_usage_delta_is_empty_without_a_baseline():
    current = {"controller.config": {"request_count": 4, "duration_ms_total": 40.0, "duration_sample_count": 4}}

    assert daily_analytics_usage_delta(current, None) == {}


def test_daily_analytics_usage_delta_subtracts_cumulative_counters():
    current = {"controller.config": {"request_count": 7, "duration_ms_total": 91.0, "duration_sample_count": 7}}
    previous = {
        "observed_at": "2026-10-08T02:00:00+00:00",
        "metrics": {"controller.config": {"request_count": 2, "duration_ms_total": 31.0, "duration_sample_count": 2}},
    }

    assert daily_analytics_usage_delta(current, previous) == {
        "controller.config": {"request_count": 5, "duration_ms_total": 60.0, "duration_ms_average": 12.0}
    }


def test_daily_analytics_usage_delta_uses_current_values_after_counter_reset():
    current = {"controller.config": {"request_count": 3, "duration_ms_total": 24.0, "duration_sample_count": 3}}
    previous = {
        "observed_at": "2026-10-08T02:00:00+00:00",
        "metrics": {"controller.config": {"request_count": 7, "duration_ms_total": 91.0, "duration_sample_count": 7}},
    }

    assert daily_analytics_usage_delta(current, previous) == {
        "controller.config": {"request_count": 3, "duration_ms_total": 24.0, "duration_ms_average": 8.0}
    }


def test_daily_analytics_usage_delta_returns_null_average_without_samples():
    current = {"controller.config": {"request_count": 2, "duration_ms_total": 31.0, "duration_sample_count": 2}}
    previous = {
        "observed_at": "2026-10-08T02:00:00+00:00",
        "metrics": {"controller.config": {"request_count": 2, "duration_ms_total": 31.0, "duration_sample_count": 2}},
    }

    assert daily_analytics_usage_delta(current, previous) == {
        "controller.config": {"request_count": 0, "duration_ms_total": 0.0, "duration_ms_average": None}
    }


def test_daily_analytics_usage_delta_keeps_disabled_collectors_out_of_payload():
    entry = CollectorEntry("controller.disabled", collector_type="disabled", mode="hourly", enabled=False)
    current = {"controller.disabled": {"request_count": 3, "duration_ms_total": 20.0, "duration_sample_count": 3}}
    previous = {
        "observed_at": "2026-10-08T02:00:00+00:00",
        "metrics": {"controller.disabled": {"request_count": 1, "duration_ms_total": 4.0, "duration_sample_count": 1}},
    }

    with patch("apps.analytics.telemetry.get_entry", return_value=entry):
        assert daily_analytics_usage_delta(current, previous) == {}
