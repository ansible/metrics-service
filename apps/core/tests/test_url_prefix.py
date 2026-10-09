"""Tests for translating internal API paths to the configured public prefix."""

import pytest
from django.test import override_settings

from apps.core.url_prefix import replace_api_root


@pytest.mark.parametrize(
    ("url", "prefix", "expected"),
    [
        ("/api/v1/tasks/", "/api/metrics/", "/api/metrics/v1/tasks/"),
        ("/api/v1/tasks/?page=2", "/api/metrics", "/api/metrics/v1/tasks/?page=2"),
        (
            "https://metrics.example.com/api/v1/tasks/#task",
            "/api/metrics/",
            "https://metrics.example.com/api/metrics/v1/tasks/#task",
        ),
        ("/api/metrics/v1/tasks/", "/api/metrics/", "/api/metrics/v1/tasks/"),
        ("/api/v1/tasks/", None, "/api/v1/tasks/"),
        ("/dashboard/", "/api/metrics/", "/dashboard/"),
    ],
)
def test_replace_api_root_preserves_version_suffix_and_avoids_duplicates(url, prefix, expected):
    assert replace_api_root(url, prefix) == expected


@override_settings(URL_PREFIX="/api/metrics/")
def test_openapi_postprocessor_prefixes_offline_schema_paths():
    from apps.core.openapi import replace_openapi_api_paths

    result = {"paths": {"/api/v1/tasks/": {"get": {}}}}

    actual = replace_openapi_api_paths(result, "/api/metrics/")

    assert "/api/metrics/v1/tasks/" in actual["paths"]
    assert "/api/v1/tasks/" not in actual["paths"]


@override_settings(URL_PREFIX="/api/metrics/")
def test_openapi_path_mapping_leaves_unmounted_live_paths_canonical():
    from apps.core.openapi import replace_openapi_api_paths

    result = {"paths": {"/api/v1/tasks/": {"get": {}}}}

    actual = replace_openapi_api_paths(result, None)

    assert "/api/v1/tasks/" in actual["paths"]
    assert "/api/metrics/v1/tasks/" not in actual["paths"]
