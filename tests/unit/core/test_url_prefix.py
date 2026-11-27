"""Tests for service URL prefix resolution."""

import pytest

from apps.core.url_prefix import resolve_service_prefixes


@pytest.mark.unit
@pytest.mark.parametrize(
    ("url_prefix", "root_urlconf", "expected"),
    [
        ("/api/metrics/", "metrics_service.urls", ("/api/metrics", "/metrics")),
        ("/api/metrics", "metrics_service.urls", ("/api/metrics", "/metrics")),
        ("/metrics", "metrics_service.urls", ("/metrics", "/metrics")),
        (None, "metrics_service.urls", ("/api/metrics-service", "/metrics-service")),
        ("", "metrics_service.urls", ("/api/metrics-service", "/metrics-service")),
        ("/", "metrics_service.urls", ("/api/metrics-service", "/metrics-service")),
        ("   ", "metrics_service.urls", ("/api/metrics-service", "/metrics-service")),
        ("  /api/metrics/  ", "metrics_service.urls", ("/api/metrics", "/metrics")),
    ],
)
def test_resolve_service_prefixes(url_prefix, root_urlconf, expected):
    assert resolve_service_prefixes(url_prefix, root_urlconf) == expected
