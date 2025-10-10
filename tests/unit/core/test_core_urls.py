"""
Unit tests for core app URLs.
"""

from django.contrib.auth import views as auth_views
from django.test import TestCase
from django.urls import resolve, reverse


class CoreURLsTestCase(TestCase):
    """Test cases for core app URL patterns."""

    def test_login_url_pattern(self):
        """Test login URL pattern resolves correctly."""
        url = reverse("login")
        self.assertEqual(url, "/login/")

        resolver = resolve("/login/")
        self.assertEqual(resolver.func.view_class, auth_views.LoginView)
        self.assertEqual(resolver.url_name, "login")

    def test_logout_url_pattern(self):
        """Test logout URL pattern resolves correctly."""
        url = reverse("logout")
        self.assertEqual(url, "/logout/")

        resolver = resolve("/logout/")
        self.assertEqual(resolver.func.view_class, auth_views.LogoutView)
        self.assertEqual(resolver.url_name, "logout")

    def test_login_view_configuration(self):
        """Test login view is configured with correct template."""
        resolver = resolve("/login/")
        view_instance = resolver.func.view_class()
        self.assertEqual(view_instance.template_name, "registration/login.html")

    def test_logout_view_configuration(self):
        """Test logout view is configured with correct next page."""
        resolver = resolve("/logout/")
        view_instance = resolver.func.view_class()
        self.assertEqual(view_instance.next_page, "/login/")

    def test_url_patterns_import(self):
        """Test that urlpatterns can be imported from core.urls."""
        from apps.core.urls import urlpatterns

        self.assertIsInstance(urlpatterns, list)
        self.assertGreater(len(urlpatterns), 0)

    def test_auth_views_import(self):
        """Test auth views import in urls module."""
        from apps.core import urls

        # This ensures the import statement is executed
        self.assertTrue(hasattr(urls, "auth_views"))

    def test_path_import(self):
        """Test path import in urls module."""
        from apps.core import urls

        # This ensures the import statement is executed
        self.assertTrue(hasattr(urls, "path"))
