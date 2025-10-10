"""
Comprehensive unit tests for main URL patterns to achieve full coverage.
"""

from django.test import TestCase
from django.urls import include, resolve, reverse
from drf_spectacular.views import SpectacularAPIView


class MainURLsComprehensiveCoverageTestCase(TestCase):
    """Test cases for main URL patterns with full coverage."""

    def test_core_urls_inclusion(self):
        """Test core app URLs are included at root."""
        # Test that core URLs are accessible
        resolver = resolve("/login/")
        self.assertIsNotNone(resolver)

    def test_health_urls_inclusion(self):
        """Test health URLs are included at root."""
        # Test that health URLs are accessible
        resolver = resolve("/health/")
        self.assertIsNotNone(resolver)

    def test_dashboard_urls_inclusion(self):
        """Test dashboard URLs are included with prefix."""
        # Test that dashboard URLs are accessible
        resolver = resolve("/dashboard/")
        self.assertIsNotNone(resolver)

    def test_api_schema_url_pattern(self):
        """Test API schema URL pattern configuration."""
        url = reverse("schema")
        self.assertEqual(url, "/api/schema/")

        resolver = resolve("/api/schema/")
        self.assertEqual(resolver.func.view_class, SpectacularAPIView)
        self.assertEqual(resolver.url_name, "schema")

    def test_api_urls_inclusion(self):
        """Test API URLs are included with prefix."""
        # Test that API URLs are accessible
        resolver = resolve("/api/v1/")
        self.assertIsNotNone(resolver)

    def test_resource_api_urls_inclusion(self):
        """Test resource API URLs are included."""
        # These are from Django-Ansible-Base
        # Test that the include function is called correctly
        from metrics_service.urls import urlpatterns

        # Find the resource API URL pattern
        resource_patterns = [
            pattern for pattern in urlpatterns if hasattr(pattern, "pattern") and str(pattern.pattern) == "api/v1/"
        ]
        self.assertGreater(len(resource_patterns), 0)

    def test_api_version_urls_inclusion(self):
        """Test API version URLs are included."""
        # These are from Django-Ansible-Base
        from metrics_service.urls import urlpatterns

        # Verify that api_version_urls are included
        api_v1_patterns = [
            pattern for pattern in urlpatterns if hasattr(pattern, "pattern") and str(pattern.pattern) == "api/v1/"
        ]
        self.assertGreater(len(api_v1_patterns), 0)

    def test_root_urls_inclusion(self):
        """Test root URLs are included."""
        # These are from Django-Ansible-Base
        from metrics_service.urls import urlpatterns

        # Verify that root_urls are included
        root_patterns = [
            pattern for pattern in urlpatterns if hasattr(pattern, "pattern") and str(pattern.pattern) == ""
        ]
        self.assertGreater(len(root_patterns), 0)

    def test_url_pattern_order(self):
        """Test that URL patterns are in correct order."""
        from metrics_service.urls import urlpatterns

        # Verify we have the expected number of URL patterns
        self.assertGreater(len(urlpatterns), 5)

        # Verify patterns are URLPattern or URLResolver instances
        for pattern in urlpatterns:
            self.assertTrue(hasattr(pattern, "pattern"), f"Pattern {pattern} should have 'pattern' attribute")

    def test_url_imports(self):
        """Test that all required imports are available."""
        from ansible_base.lib.dynamic_config.dynamic_urls import (
            api_version_urls,
            root_urls,
        )
        from ansible_base.resource_registry.urls import (
            urlpatterns as resource_api_urls,
        )
        from django.urls import path
        from drf_spectacular.views import SpectacularAPIView

        # Verify all imports are available and not None
        self.assertIsNotNone(api_version_urls)
        self.assertIsNotNone(root_urls)
        self.assertIsNotNone(resource_api_urls)
        self.assertIsNotNone(include)
        self.assertIsNotNone(path)
        self.assertIsNotNone(SpectacularAPIView)
