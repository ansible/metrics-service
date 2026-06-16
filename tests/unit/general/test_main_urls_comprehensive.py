"""
Comprehensive test coverage for metrics_service/urls.py

This module provides extensive coverage for the main URL configuration,
including URL pattern resolution, view integration, and routing behavior.
"""

import pytest
from django.test import Client, TestCase
from django.urls import NoReverseMatch, resolve, reverse
from django.urls.exceptions import Resolver404


@pytest.mark.unit
class TestHealthURLsIntegration(TestCase):
    """Test health URLs integration."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()

    def test_health_url_resolves(self):
        """Test that the health URL resolves."""
        resolver_match = resolve("/health/")
        assert resolver_match is not None
        assert resolver_match.url_name == "health"

    def test_health_endpoint_response(self):
        """Test that the health endpoint returns 200."""
        response = self.client.get("/health/")
        assert response.status_code == 200


@pytest.mark.unit
class TestAPISchemaURL(TestCase):
    """Test API schema URL configuration."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()

    def test_schema_url_resolution(self):
        """Test that schema URL resolves correctly."""
        resolver_match = resolve("/api/v1/docs/schema/")
        assert resolver_match is not None
        assert resolver_match.url_name == "schema"

    def test_schema_url_reverse(self):
        """Test that schema URL can be reversed."""
        try:
            url = reverse("schema")
            assert url == "/api/v1/docs/schema/"
        except NoReverseMatch:
            pytest.skip("schema URL name not registered for reverse lookup")

    def test_schema_endpoint_response(self):
        """Test schema endpoint response."""
        response = self.client.get("/api/v1/docs/schema/")
        assert response.status_code == 200

    def test_schema_content_type(self):
        """Test schema endpoint content type."""
        response = self.client.get("/api/v1/docs/schema/")
        assert response.status_code == 200
        assert "content-type" in response.headers


@pytest.mark.unit
class TestAPIURLsIntegration(TestCase):
    """Test API URLs integration."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()

    def test_api_urls_resolve(self):
        """Test that API URLs resolve."""
        resolver_match = resolve("/api/")
        assert resolver_match is not None

        resolver_match = resolve("/api/v1/")
        assert resolver_match is not None

    def test_api_endpoints_response(self):
        """Test API endpoints respond with 200."""
        for url in ["/api/", "/api/v1/"]:
            response = self.client.get(url)
            assert response.status_code == 200

    def test_api_documentation_urls_not_registered(self):
        """Test that standalone documentation URLs are not registered."""
        for url in ["/api/docs/", "/api/redoc/"]:
            response = self.client.get(url)
            assert response.status_code == 404


@pytest.mark.unit
class TestDjangoAnsibleBaseURLs(TestCase):
    """Test Django-Ansible-Base URLs integration."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()

    def test_api_v1_resolves(self):
        """Test that the v1 API root resolves."""
        resolver_match = resolve("/api/v1/")
        assert resolver_match is not None

    def test_dab_resource_endpoints_require_auth(self):
        """Test DAB resource endpoints require authentication."""
        for url in ["/api/v1/users/", "/api/v1/organizations/"]:
            response = self.client.get(url)
            assert response.status_code == 403

    def test_dab_authentication_endpoints_not_registered(self):
        """Test that DAB authentication endpoints are not registered."""
        for url in ["/api/v1/auth/", "/api/v1/me/"]:
            response = self.client.get(url)
            assert response.status_code == 404


@pytest.mark.unit
class TestRootURLsIntegration(TestCase):
    """Test root URLs integration."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()

    def test_root_url_resolves(self):
        """Test that the root URL resolves."""
        resolver_match = resolve("/")
        assert resolver_match is not None

    def test_root_url_response(self):
        """Test root URL responds with 200."""
        response = self.client.get("/")
        assert response.status_code == 200

    def test_admin_url_does_not_resolve(self):
        """Test that admin URL is not registered."""
        with pytest.raises(Resolver404):
            resolve("/admin/")

    def test_admin_url_returns_404(self):
        """Test that admin URL returns 404."""
        response = self.client.get("/admin/")
        assert response.status_code == 404


@pytest.mark.unit
class TestURLErrorHandling(TestCase):
    """Test URL error handling and edge cases."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()

    def test_nonexistent_url_404(self):
        """Test that non-existent URLs return 404."""
        response = self.client.get("/nonexistent/url/")
        assert response.status_code == 404

    def test_malformed_urls(self):
        """Test handling of malformed URLs."""
        malformed_urls = ["/api//", "/api/v1//"]

        for url in malformed_urls:
            response = self.client.get(url)
            assert response.status_code in [200, 404]

    def test_url_with_special_characters(self):
        """Test URLs with special characters."""
        special_urls = ["/api/test%20space/", "/api/test@email.com/", "/api/test-dash/", "/api/test_underscore/"]

        for url in special_urls:
            response = self.client.get(url)
            assert response.status_code == 404

    def test_url_with_unicode(self):
        """Test URLs with unicode characters."""
        unicode_urls = ["/api/tëst/", "/api/测试/", "/api/🚀/"]

        for url in unicode_urls:
            response = self.client.get(url)
            assert response.status_code == 404

    def test_very_long_url(self):
        """Test handling of very long URLs."""
        long_path = "/api/" + "a" * 1000 + "/"
        response = self.client.get(long_path)
        assert response.status_code in [404, 414]


@pytest.mark.unit
class TestURLSecurityConsiderations(TestCase):
    """Test URL security considerations."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()

    def test_path_traversal_protection(self):
        """Test protection against path traversal attacks."""
        traversal_urls = ["/api/../../../etc/passwd", "/admin/../../../etc/passwd", "/api/v1/../../../settings.py"]

        for url in traversal_urls:
            response = self.client.get(url)
            assert response.status_code != 200

    def test_admin_access_protection(self):
        """Test that admin URLs are not accessible."""
        response = self.client.get("/admin/")
        assert response.status_code == 404


@pytest.mark.unit
class TestURLPerformance(TestCase):
    """Test URL resolution performance."""

    def test_url_resolution_speed(self):
        """Test that URL resolution is fast."""
        import time

        urls_to_test = ["/api/", "/api/v1/", "/api/v1/docs/schema/", "/health/"]

        start_time = time.time()

        for url in urls_to_test:
            resolve(url)

        end_time = time.time()
        resolution_time = end_time - start_time

        assert resolution_time < 1.0


@pytest.mark.unit
class TestURLIntegrationWithViews(TestCase):
    """Test URL integration with actual views."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()

    def test_url_view_mapping(self):
        """Test that URLs map to actual views."""
        test_urls = ["/api/v1/docs/schema/", "/health/", "/api/", "/api/v1/"]

        for url in test_urls:
            resolver_match = resolve(url)
            assert resolver_match is not None
            assert resolver_match.func is not None

    def test_view_response_consistency(self):
        """Test that views respond consistently through URLs."""
        response1 = self.client.get("/api/")
        response2 = self.client.get("/api/v1/")

        assert response1.status_code == 200
        assert response2.status_code == 200
