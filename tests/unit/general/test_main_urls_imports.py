"""
Unit tests for main URL imports and patterns to improve coverage.
"""

from django.test import TestCase
from django.urls import include, path


class MainURLImportsTestCase(TestCase):
    """Test cases for main URL imports."""

    def test_imports_available(self):
        """Test that all imports in main urls.py are available."""
        from ansible_base.lib.dynamic_config.dynamic_urls import (
            api_version_urls,
            root_urls,
        )
        from ansible_base.resource_registry.urls import (
            urlpatterns as resource_api_urls,
        )
        from drf_spectacular.views import SpectacularAPIView

        # Verify all imports are successful
        self.assertIsNotNone(api_version_urls)
        self.assertIsNotNone(root_urls)
        self.assertIsNotNone(resource_api_urls)
        self.assertIsNotNone(include)
        self.assertIsNotNone(path)
        self.assertIsNotNone(SpectacularAPIView)

    def test_urlpatterns_structure(self):
        """Test the structure of urlpatterns."""
        from metrics_service.urls import urlpatterns

        self.assertIsInstance(urlpatterns, list)
        self.assertGreater(len(urlpatterns), 0)

        # Verify each pattern is a valid URL pattern
        for pattern in urlpatterns:
            self.assertTrue(hasattr(pattern, "pattern"), f"Pattern {pattern} should have 'pattern' attribute")

    def test_specific_url_patterns(self):
        """Test specific URL patterns are included."""
        from metrics_service.urls import urlpatterns

        # Convert patterns to strings for easier testing
        pattern_strings = []
        for pattern in urlpatterns:
            if hasattr(pattern, "pattern"):
                pattern_strings.append(str(pattern.pattern))

        # Check for expected patterns
        expected_patterns = [
            "",  # Core and health URLs
            "dashboard/",  # Dashboard
            "api/schema/",  # Schema
            "api/",  # API
            "api/v1/",  # Resource and version URLs
        ]

        for expected in expected_patterns:
            found = any(expected in p for p in pattern_strings)
            self.assertTrue(found, f"Expected pattern '{expected}' not found in {pattern_strings}")

    def test_url_pattern_types(self):
        """Test that URL patterns are of correct types."""
        from django.urls.resolvers import URLPattern, URLResolver

        from metrics_service.urls import urlpatterns

        for pattern in urlpatterns:
            self.assertTrue(
                isinstance(pattern, URLPattern | URLResolver), f"Pattern {pattern} should be URLPattern or URLResolver"
            )

    def test_module_level_imports(self):
        """Test module level imports in urls.py."""
        # Import the module to ensure all imports work
        import metrics_service.urls

        # Verify module has urlpatterns
        self.assertTrue(hasattr(metrics_service.urls, "urlpatterns"))

    def test_include_function_usage(self):
        """Test that include function is used properly."""
        from django.urls.resolvers import URLResolver

        from metrics_service.urls import urlpatterns

        # Find patterns that use include
        include_patterns = [p for p in urlpatterns if isinstance(p, URLResolver) and hasattr(p, "url_patterns")]

        # Should have at least some include patterns
        self.assertGreater(len(include_patterns), 0)

    def test_path_function_usage(self):
        """Test that path function is used properly."""
        from metrics_service.urls import urlpatterns

        # All patterns should have been created with path() function
        for pattern in urlpatterns:
            self.assertTrue(hasattr(pattern, "pattern"))
            # The pattern should have a regex attribute (created by path)
            self.assertTrue(hasattr(pattern.pattern, "_regex"))

    def test_spectacular_api_view_import(self):
        """Test SpectacularAPIView import and usage."""
        from drf_spectacular.views import SpectacularAPIView

        from metrics_service.urls import urlpatterns

        # Find the schema pattern
        schema_patterns = [
            p
            for p in urlpatterns
            if hasattr(p, "callback") and getattr(p.callback, "view_class", None) == SpectacularAPIView
        ]

        self.assertGreater(len(schema_patterns), 0, "Should have at least one SpectacularAPIView pattern")

    def test_apps_imports(self):
        """Test that app URL imports work."""
        # Test individual app URL imports
        import apps.api.urls
        import apps.core.urls
        import apps.dashboard.urls
        import apps.health.urls

        # Verify each has urlpatterns
        self.assertTrue(hasattr(apps.core.urls, "urlpatterns"))
        self.assertTrue(hasattr(apps.health.urls, "urlpatterns"))
        self.assertTrue(hasattr(apps.dashboard.urls, "urlpatterns"))
        self.assertTrue(hasattr(apps.api.urls, "urlpatterns"))

    def test_dynamic_config_imports(self):
        """Test ansible-base dynamic config imports."""
        try:
            from ansible_base.lib.dynamic_config.dynamic_urls import (
                api_version_urls,
                root_urls,
            )

            # If import succeeds, verify they're not None
            self.assertIsNotNone(api_version_urls)
            self.assertIsNotNone(root_urls)
        except ImportError:
            # Skip if ansible-base not available
            self.skipTest("ansible-base not available")

    def test_resource_registry_imports(self):
        """Test ansible-base resource registry imports."""
        try:
            from ansible_base.resource_registry.urls import (
                urlpatterns as resource_api_urls,
            )

            # If import succeeds, verify it's not None
            self.assertIsNotNone(resource_api_urls)
        except ImportError:
            # Skip if ansible-base not available
            self.skipTest("ansible-base resource registry not available")
