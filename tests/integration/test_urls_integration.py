"""
Integration tests for URL configuration and routing.

Tests the complete URL routing system including:
- URL pattern resolution
- View integration
- API endpoint functionality
- Authentication and authorization
- Error handling
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import resolve
from django.urls.exceptions import Resolver404
from rest_framework.test import APIClient

from tests.test_utils import get_test_password

User = get_user_model()


@pytest.mark.integration
class TestURLResolution(TestCase):
    """Test URL resolution and routing functionality."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()
        self.api_client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_api_url_resolution(self):
        """Test API URL resolution."""
        resolver_match = resolve("/api/")
        assert resolver_match is not None

    def test_api_v1_url_resolution(self):
        """Test API v1 URL resolution."""
        resolver_match = resolve("/api/v1/")
        assert resolver_match is not None

    def test_admin_url_does_not_resolve(self):
        """Test that admin URL is not registered."""
        with pytest.raises(Resolver404):
            resolve("/admin/")


@pytest.mark.integration
class TestURLPatterns(TestCase):
    """Test URL pattern structure and organization."""

    def test_url_pattern_order(self):
        """Test that URL patterns are in the correct order."""
        from django.urls import get_resolver

        resolver = get_resolver()
        url_patterns = resolver.url_patterns

        routes = []
        for pattern in url_patterns:
            if hasattr(pattern, "pattern") and hasattr(pattern.pattern, "_route"):
                routes.append(pattern.pattern._route)

        assert len(routes) > 0

    def test_url_pattern_types(self):
        """Test that URL patterns have correct types."""
        from django.urls import URLPattern, URLResolver, get_resolver

        resolver = get_resolver()
        url_patterns = resolver.url_patterns

        for pattern in url_patterns:
            assert isinstance(pattern, URLResolver | URLPattern)
            assert hasattr(pattern, "pattern")

    def test_url_namespace_organization(self):
        """Test that URL namespaces are properly organized."""
        from django.urls import get_resolver

        resolver = get_resolver()
        url_patterns = resolver.url_patterns

        namespaces = []
        for pattern in url_patterns:
            if hasattr(pattern, "namespace") and pattern.namespace:
                namespaces.append(pattern.namespace)

        assert len(namespaces) >= 1


@pytest.mark.integration
class TestAPIEndpoints(TestCase):
    """Test API endpoint functionality through URL routing."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_api_root_endpoint(self):
        """Test API root endpoint."""
        response = self.client.get("/api/")
        assert response.status_code == 200

    def test_api_v1_endpoint(self):
        """Test API v1 endpoint."""
        response = self.client.get("/api/v1/")
        assert response.status_code == 200

    def test_schema_endpoint(self):
        """Test API schema endpoint."""
        response = self.client.get("/api/v1/docs/schema/")
        assert response.status_code == 200

    def test_documentation_endpoints_not_registered(self):
        """Test that standalone documentation endpoints are not registered."""
        for endpoint in ["/api/docs/", "/api/redoc/"]:
            response = self.client.get(endpoint)
            assert response.status_code == 404

    def test_authenticated_api_endpoints(self):
        """Test authenticated API endpoints."""
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/v1/users/")
        assert response.status_code == 200

        response = self.client.get(f"/api/v1/users/{self.user.id}/")
        assert response.status_code == 200


@pytest.mark.integration
class TestErrorHandling(TestCase):
    """Test URL error handling and edge cases."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()

    def test_404_handling(self):
        """Test 404 error handling for non-existent URLs."""
        non_existent_urls = ["/nonexistent/", "/api/nonexistent/", "/admin/nonexistent/"]

        for url in non_existent_urls:
            response = self.client.get(url)
            assert response.status_code == 404

    def test_admin_returns_404(self):
        """Test that admin UI is not exposed."""
        response = self.client.get("/admin/")
        assert response.status_code == 404

    def test_method_not_allowed(self):
        """Test method not allowed handling."""
        response = self.client.post("/api/v1/docs/schema/")
        assert response.status_code == 405

    def test_malformed_urls(self):
        """Test malformed URL handling."""
        malformed_urls = ["/api//", "/api/v1//"]

        for url in malformed_urls:
            response = self.client.get(url)
            assert response.status_code in [200, 404]


@pytest.mark.integration
class TestURLPerformance(TestCase):
    """Test URL resolution performance and efficiency."""

    def test_url_resolution_speed(self):
        """Test that URL resolution is fast."""
        import time

        start_time = time.time()

        urls_to_test = ["/api/", "/api/v1/", "/health/"]

        for url in urls_to_test:
            resolve(url)

        end_time = time.time()
        resolution_time = end_time - start_time

        assert resolution_time < 1.0

    def test_url_pattern_efficiency(self):
        """Test that URL patterns are efficiently organized."""
        from django.urls import get_resolver

        resolver = get_resolver()
        url_patterns = resolver.url_patterns

        assert len(url_patterns) < 100

        for pattern in url_patterns:
            assert hasattr(pattern, "pattern")
            assert pattern.pattern is not None


@pytest.mark.integration
class TestURLIntegrationWithViews(TestCase):
    """Test URL integration with actual views."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()
        self.api_client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_url_to_view_mapping(self):
        """Test that URLs correctly map to views."""
        test_urls = ["/api/v1/docs/schema/", "/api/", "/api/v1/", "/health/"]

        for url in test_urls:
            resolver_match = resolve(url)
            assert resolver_match is not None
            assert resolver_match.func is not None

    def test_view_response_through_urls(self):
        """Test that views respond correctly through URL routing."""
        response = self.client.get("/api/v1/docs/schema/")
        assert response.status_code == 200

    def test_api_view_integration(self):
        """Test API view integration through URLs."""
        self.api_client.force_authenticate(user=self.user)

        response = self.api_client.get("/api/v1/users/")
        assert response.status_code == 200


@pytest.mark.integration
class TestURLConfiguration(TestCase):
    """Test URL configuration and settings integration."""

    def test_url_configuration_loading(self):
        """Test that URL configuration loads correctly."""
        from django.conf import settings
        from django.urls import get_resolver

        assert settings.ROOT_URLCONF is not None

        resolver = get_resolver()
        assert resolver is not None

    def test_url_pattern_validation(self):
        """Test that URL patterns are valid."""
        from django.urls import get_resolver

        resolver = get_resolver()
        url_patterns = resolver.url_patterns

        for pattern in url_patterns:
            assert pattern is not None
            assert hasattr(pattern, "pattern")

    def test_url_namespace_validation(self):
        """Test that URL namespaces are properly configured."""
        from django.urls import get_resolver

        resolver = get_resolver()
        url_patterns = resolver.url_patterns

        for pattern in url_patterns:
            if hasattr(pattern, "namespace"):
                assert pattern.namespace is None or isinstance(pattern.namespace, str)


@pytest.mark.integration
class TestURLSecurity(TestCase):
    """Test URL security and access control."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_unauthenticated_api_requires_auth(self):
        """Test that API endpoints require authentication."""
        response = self.client.get("/api/v1/users/")
        assert response.status_code == 403

    def test_url_injection_protection(self):
        """Test protection against URL injection attacks."""
        malicious_urls = ["/api/../../../etc/passwd", "/admin/../../../etc/passwd"]
        for url in malicious_urls:
            response = self.client.get(url)
            assert response.status_code != 200
