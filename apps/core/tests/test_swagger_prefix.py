"""
Tests for prefix-aware Swagger/OpenAPI URLs and feature-flag redirects.

Two bugs were fixed:

1. The Swagger UI needs the mounted schema URL, and the served OpenAPI document
   needs mounted path keys. The prefix-aware views replace only the internal
   /api root, retaining the /v1/... suffix.

2. Feature-flag redirects need the same request/configured-prefix mapping while
   leaving local /api/v1/ requests unchanged.
"""

import json

import pytest
from django.test import RequestFactory, TestCase, override_settings
from django.urls import set_script_prefix
from rest_framework.test import APIClient


class TestMetricsSpectacularSwaggerView(TestCase):
    """Unit tests for MetricsSpectacularSwaggerView._get_schema_url."""

    def _make_request(self, path="/api/v1/docs/", api_service_prefix=None):
        """Return a GET request, optionally with _api_service_prefix set."""
        factory = RequestFactory()
        request = factory.get(path)
        if api_service_prefix is not None:
            request._api_service_prefix = api_service_prefix
        return request

    def test_schema_url_without_prefix_is_unchanged(self):
        """When no service prefix is present, the schema URL is the bare Django path."""
        from apps.core.views.swagger import MetricsSpectacularSwaggerView

        view = MetricsSpectacularSwaggerView()
        request = self._make_request()
        schema_url = view._get_schema_url(request)
        # Without prefix the URL should be the canonical Django-generated path.
        self.assertIn("/api/v1/docs/schema/", schema_url)
        self.assertNotIn("/api/metrics", schema_url)

    def test_schema_url_with_api_metrics_prefix(self):
        """When _api_service_prefix='/api/metrics', schema URL gains that prefix."""
        from apps.core.views.swagger import MetricsSpectacularSwaggerView

        view = MetricsSpectacularSwaggerView()
        request = self._make_request(api_service_prefix="/api/metrics")
        schema_url = view._get_schema_url(request)
        self.assertIn("/api/metrics/v1/docs/schema/", schema_url)
        # The old bare internal path must not appear.
        self.assertNotIn("/api/v1/docs/schema/", schema_url)

    def test_schema_url_with_custom_prefix(self):
        """Any non-empty _api_service_prefix is prepended correctly."""
        from apps.core.views.swagger import MetricsSpectacularSwaggerView

        view = MetricsSpectacularSwaggerView()
        request = self._make_request(api_service_prefix="/api/custom-service")
        schema_url = view._get_schema_url(request)
        self.assertIn("/api/custom-service/v1/docs/schema/", schema_url)

    def test_schema_url_with_empty_string_prefix_is_unchanged(self):
        """An empty _api_service_prefix leaves the URL unchanged."""
        from apps.core.views.swagger import MetricsSpectacularSwaggerView

        view = MetricsSpectacularSwaggerView()
        request = self._make_request(api_service_prefix="")
        schema_url = view._get_schema_url(request)
        self.assertIn("/api/v1/docs/schema/", schema_url)

    def test_schema_url_query_params_are_preserved(self):
        """lang/version query params from the request are forwarded to the schema URL."""
        from apps.core.views.swagger import MetricsSpectacularSwaggerView

        view = MetricsSpectacularSwaggerView()
        factory = RequestFactory()
        request = factory.get("/api/v1/docs/", {"lang": "en", "version": "v1"})
        request._api_service_prefix = "/api/metrics"
        schema_url = view._get_schema_url(request)
        self.assertIn("lang=en", schema_url)
        self.assertIn("version=v1", schema_url)

    def test_view_class_is_subclass_of_spectacular_swagger_view(self):
        """MetricsSpectacularSwaggerView is a proper subclass."""
        from drf_spectacular.views import SpectacularSwaggerView

        from apps.core.views.swagger import MetricsSpectacularSwaggerView

        self.assertTrue(issubclass(MetricsSpectacularSwaggerView, SpectacularSwaggerView))

    def test_view_exported_from_core_views(self):
        """MetricsSpectacularSwaggerView is exported from apps.core.views."""
        from apps.core.views import MetricsSpectacularSwaggerView

        self.assertIsNotNone(MetricsSpectacularSwaggerView)


@pytest.mark.django_db
class TestSwaggerEndpointWithPrefix:
    """Integration tests for the Swagger UI endpoint with the gateway prefix."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = APIClient()
        set_script_prefix("/")
        yield
        set_script_prefix("/")

    def test_swagger_ui_endpoint_responds_200(self):
        """GET /api/v1/docs/ returns 200 (Swagger UI page)."""
        response = self.client.get("/api/v1/docs/")
        assert response.status_code == 200

    def test_swagger_schema_endpoint_responds_200(self):
        """The local OpenAPI schema keeps its canonical /api/v1 paths."""
        response = self.client.get("/api/v1/docs/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
        assert response.status_code == 200
        paths = json.loads(response.content)["paths"]
        assert "/api/v1/tasks/" in paths
        assert "/api/metrics/v1/tasks/" not in paths

    @override_settings(URL_PREFIX="/api/metrics/")
    def test_mounted_openapi_schema_paths_preserve_v1_suffix(self):
        """Mounted OpenAPI paths replace /api with /api/metrics exactly once."""
        response = APIClient().get(
            "/api/metrics/v1/docs/schema/",
            HTTP_ACCEPT="application/vnd.oai.openapi+json",
        )
        assert response.status_code == 200
        paths = json.loads(response.content)["paths"]
        assert "/api/metrics/v1/tasks/" in paths
        assert "/api/v1/tasks/" not in paths
        assert "/api/metrics/api/v1/tasks/" not in paths

    def test_swagger_ui_via_api_metrics_prefix_responds_200(self):
        """GET /api/metrics-service/v1/docs/ (service prefix) returns 200."""
        # The service name prefix derived from ROOT_URLCONF is 'metrics-service'.
        from django.conf import settings

        service_name = settings.ROOT_URLCONF.split(".")[0].replace("_", "-")
        response = self.client.get(f"/api/{service_name}/v1/docs/")
        assert response.status_code == 200

    def test_swagger_ui_schema_url_contains_service_prefix(self):
        """Swagger UI served via /api/<svc>/v1/docs/ embeds the prefixed schema URL.

        The ``{{ schema_url|escapejs }}`` template filter may encode non-ASCII
        characters and some ASCII punctuation (e.g. '-' → \\u002D) as JSON
        unicode escapes.  We therefore search for the JS-escaped form of the
        URL as well as the literal form.
        """
        from django.conf import settings
        from django.utils.html import escapejs

        service_name = settings.ROOT_URLCONF.split(".")[0].replace("_", "-")
        response = self.client.get(
            f"/api/{service_name}/v1/docs/",
            HTTP_ACCEPT="text/html",
        )
        assert response.status_code == 200
        html = response.content.decode("utf-8")
        expected_path = f"/api/{service_name}/v1/docs/schema/"
        # The schema URL may appear as-is or JS-escaped by the template filter.
        assert expected_path in html or escapejs(expected_path) in html


@pytest.mark.django_db
class TestFeatureFlagsRedirect:
    """Tests for the feature_flags redirect URL (AAP-80896 fix 2)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = APIClient()
        set_script_prefix("/")
        yield
        set_script_prefix("/")

    def test_feature_flags_redirect_keeps_canonical_prefix_locally(self):
        """Without URL_PREFIX, redirects stay under the local /api/v1/ root."""
        response = self.client.get("/api/v1/feature_flags/", follow=False)
        assert response.status_code == 301
        assert response["Location"] == "/api/v1/feature_flags/states/"

    @override_settings(URL_PREFIX="/api/metrics/")
    def test_feature_flags_redirect_uses_configured_url_prefix(self):
        """A configured public API root replaces /api rather than being prepended."""
        response = APIClient().get("/api/v1/feature_flags/", follow=False)
        assert response.status_code == 301
        assert response["Location"] == "/api/metrics/v1/feature_flags/states/"

    @override_settings(URL_PREFIX="/api/metrics/")
    def test_prefixed_feature_flags_redirect_does_not_duplicate_api_root(self):
        """A request through the mounted path redirects to one /api/metrics root."""
        response = APIClient().get("/api/metrics/v1/feature_flags/", follow=False)
        assert response.status_code == 301
        assert response["Location"] == "/api/metrics/v1/feature_flags/states/"

    def test_feature_flags_redirect_is_permanent(self):
        """The redirect is permanent (HTTP 301)."""
        response = self.client.get("/api/v1/feature_flags/", follow=False)
        assert response.status_code == 301

    def test_feature_flags_redirect_via_service_prefix_uses_prefixed_location(self):
        """GET /api/<svc>/v1/feature_flags/ redirects to the prefixed states URL."""
        from django.conf import settings

        service_name = settings.ROOT_URLCONF.split(".")[0].replace("_", "-")
        response = self.client.get(f"/api/{service_name}/v1/feature_flags/", follow=False)
        assert response.status_code == 301
        location = response["Location"]
        # Without a configured URL_PREFIX, the middleware preserves the alias
        # used for this request rather than hardcoding the production prefix.
        assert location == f"/api/{service_name}/v1/feature_flags/states/"
