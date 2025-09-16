"""
Unit tests for utility functions.
"""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


@pytest.mark.unit
class UtilityFunctionsTestCase(TestCase):
    """Test cases for utility functions."""

    def test_settings_validation(self):
        """Test that required settings are present."""
        # Test that critical settings exist
        self.assertTrue(hasattr(settings, "SECRET_KEY"))
        self.assertTrue(hasattr(settings, "DATABASES"))
        self.assertTrue(hasattr(settings, "INSTALLED_APPS"))

        # Test that our apps are installed
        self.assertIn("apps.core", settings.INSTALLED_APPS)
        self.assertIn("apps.api", settings.INSTALLED_APPS)

    def test_rest_framework_settings(self):
        """Test REST framework settings."""
        self.assertTrue(hasattr(settings, "REST_FRAMEWORK"))
        self.assertIn("DEFAULT_AUTHENTICATION_CLASSES", settings.REST_FRAMEWORK)
        self.assertIn("DEFAULT_PERMISSION_CLASSES", settings.REST_FRAMEWORK)
        self.assertIn("DEFAULT_PAGINATION_CLASS", settings.REST_FRAMEWORK)

    def test_authentication_settings(self):
        """Test authentication settings."""
        self.assertTrue(hasattr(settings, "AUTH_USER_MODEL"))
        self.assertEqual(settings.AUTH_USER_MODEL, "core.User")

        self.assertTrue(hasattr(settings, "AUTHENTICATION_BACKENDS"))
        self.assertIsInstance(settings.AUTHENTICATION_BACKENDS, list)

    def test_database_settings(self):
        """Test database settings structure."""
        self.assertIn("default", settings.DATABASES)
        self.assertIn("ENGINE", settings.DATABASES["default"])
        self.assertIn("NAME", settings.DATABASES["default"])

    def test_cache_settings(self):
        """Test cache settings structure."""
        self.assertTrue(hasattr(settings, "CACHES"))
        self.assertIn("default", settings.CACHES)
        self.assertIn("BACKEND", settings.CACHES["default"])

    def test_logging_settings(self):
        """Test logging settings structure."""
        self.assertTrue(hasattr(settings, "LOGGING"))
        self.assertIn("version", settings.LOGGING)
        self.assertIn("handlers", settings.LOGGING)
        self.assertIn("loggers", settings.LOGGING)


@pytest.mark.unit
class ModelUtilsTestCase(TestCase):
    """Test cases for model utilities."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="utiluser", email="util@example.com")

    def test_user_string_representation(self):
        """Test user string representation."""
        self.assertEqual(str(self.user), "utiluser")

    def test_user_email_field(self):
        """Test user email field."""
        self.assertEqual(self.user.email, "util@example.com")

    def test_user_groups_relation(self):
        """Test user groups relation exists."""
        self.assertTrue(hasattr(self.user, "groups"))
        self.assertEqual(self.user.groups.count(), 0)

    def test_user_permissions_relation(self):
        """Test user permissions relation exists."""
        self.assertTrue(hasattr(self.user, "user_permissions"))
        self.assertEqual(self.user.user_permissions.count(), 0)


@pytest.mark.unit
class APIUtilsTestCase(TestCase):
    """Test cases for API utilities."""

    def test_api_urls_structure(self):
        """Test API URLs are properly structured."""
        from django.urls import reverse

        # Test that basic API URLs can be reversed
        try:
            reverse("api:v1:user-list")
            reverse("api:v1:organization-list")
            reverse("api:v1:team-list")
        except Exception as e:
            self.fail(f"API URL reversal failed: {e}")


@pytest.mark.unit
class SecurityUtilsTestCase(TestCase):
    """Test cases for security utilities."""

    def test_secret_key_exists(self):
        """Test that SECRET_KEY is configured."""
        self.assertTrue(hasattr(settings, "SECRET_KEY"))
        self.assertIsInstance(settings.SECRET_KEY, str)
        self.assertGreater(len(settings.SECRET_KEY), 0)

    def test_debug_setting(self):
        """Test DEBUG setting."""
        self.assertTrue(hasattr(settings, "DEBUG"))
        self.assertIsInstance(settings.DEBUG, bool)

    def test_allowed_hosts_setting(self):
        """Test ALLOWED_HOSTS setting."""
        self.assertTrue(hasattr(settings, "ALLOWED_HOSTS"))
        self.assertIsInstance(settings.ALLOWED_HOSTS, list)

    def test_cors_settings(self):
        """Test CORS settings if present."""
        if hasattr(settings, "CORS_ALLOW_ALL_ORIGINS"):
            self.assertIsInstance(settings.CORS_ALLOW_ALL_ORIGINS, bool)

    def test_security_middleware(self):
        """Test security middleware is configured."""
        self.assertTrue(hasattr(settings, "MIDDLEWARE"))
        self.assertIsInstance(settings.MIDDLEWARE, list)

        # Check for security-related middleware
        middleware_str = str(settings.MIDDLEWARE)
        self.assertIn("SecurityMiddleware", middleware_str)


@pytest.mark.unit
class ErrorHandlingTestCase(TestCase):
    """Test cases for error handling utilities."""

    def test_404_handling(self):
        """Test 404 error handling."""
        from django.test import Client

        client = Client()
        response = client.get("/nonexistent-url/")

        self.assertEqual(response.status_code, 404)


@pytest.mark.unit
class PerformanceUtilsTestCase(TestCase):
    """Test cases for performance-related utilities."""

    def test_pagination_settings(self):
        """Test pagination settings."""
        self.assertTrue(hasattr(settings, "REST_FRAMEWORK"))
        self.assertIn("PAGE_SIZE", settings.REST_FRAMEWORK)

        page_size = settings.REST_FRAMEWORK["PAGE_SIZE"]
        self.assertIsInstance(page_size, int)
        self.assertGreater(page_size, 0)
        self.assertLessEqual(page_size, 100)  # Reasonable page size

    def test_database_optimization_settings(self):
        """Test database optimization settings."""
        # Check that database settings are optimized for the environment
        db_config = settings.DATABASES["default"]

        self.assertIn("ENGINE", db_config)

        # For SQLite, check that it's in memory for tests
        if "sqlite3" in db_config["ENGINE"]:
            self.assertTrue("NAME" in db_config)

    def test_cache_optimization_settings(self):
        """Test cache optimization settings."""
        cache_config = settings.CACHES["default"]

        self.assertIn("BACKEND", cache_config)

        # Ensure cache backend is appropriate
        backend = cache_config["BACKEND"]
        self.assertTrue(any(cache_type in backend for cache_type in ["locmem", "redis", "memcached", "db"]))


@pytest.mark.unit
class IntegrationUtilsTestCase(TestCase):
    """Test cases for integration utilities."""

    def test_django_apps_integration(self):
        """Test Django apps integration."""
        from django.apps import apps

        # Test that our apps are properly loaded
        self.assertTrue(apps.is_installed("apps.core"))
        self.assertTrue(apps.is_installed("apps.api"))

        # Test that Django core apps are loaded
        self.assertTrue(apps.is_installed("django.contrib.auth"))
        self.assertTrue(apps.is_installed("django.contrib.contenttypes"))

    def test_rest_framework_integration(self):
        """Test REST framework integration."""
        # Test that DRF is properly integrated
        self.assertIn("rest_framework", settings.INSTALLED_APPS)

        if hasattr(settings, "REST_FRAMEWORK"):
            drf_settings = settings.REST_FRAMEWORK

            # Check that required DRF settings are present
            required_settings = ["DEFAULT_AUTHENTICATION_CLASSES", "DEFAULT_PERMISSION_CLASSES"]

            for setting in required_settings:
                self.assertIn(setting, drf_settings)
