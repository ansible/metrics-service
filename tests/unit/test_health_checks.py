"""
Tests for health check functions.
"""

from unittest.mock import Mock, patch

import pytest
from django.test import TestCase, override_settings

from apps.health.checks import HEALTH_CHECKS, check_dispatcherd, check_feature_flags


@pytest.mark.unit
class HealthCheckTestCase(TestCase):
    """Test cases for health check functions."""

    def test_health_checks_registry(self):
        """Test that health checks are properly registered."""
        self.assertIn("feature_flags", HEALTH_CHECKS)
        self.assertIn("dab_integration", HEALTH_CHECKS)
        self.assertIn("dispatcherd", HEALTH_CHECKS)

        # Verify the functions are callable
        self.assertTrue(callable(HEALTH_CHECKS["feature_flags"]))
        self.assertTrue(callable(HEALTH_CHECKS["dab_integration"]))
        self.assertTrue(callable(HEALTH_CHECKS["dispatcherd"]))

    @patch("apps.health.checks.settings")
    def test_check_feature_flags_success(self, mock_settings):
        """Test successful feature flags check."""
        mock_settings.FEATURE_FLAGS = {"ENABLE_NOTIFICATIONS": True, "ENABLE_ANALYTICS": False, "BETA_FEATURES": True}

        result = check_feature_flags()

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["feature_flags"], mock_settings.FEATURE_FLAGS)
        self.assertEqual(len(result["feature_flags"]), 3)
        self.assertIn("details", result)

    @patch("apps.health.checks.settings")
    def test_check_feature_flags_no_flags(self, mock_settings):
        """Test feature flags check with no flags configured."""
        mock_settings.FEATURE_FLAGS = {}

        result = check_feature_flags()

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["feature_flags"], {})
        self.assertIn("Found 0 feature flags", result["details"])

    @patch("apps.health.checks.settings")
    @patch("apps.health.checks.logger")
    def test_check_feature_flags_exception(self, mock_logger, mock_settings):
        """Test feature flags check with exception."""
        mock_settings.FEATURE_FLAGS = Mock(side_effect=Exception("Config error"))

        result = check_feature_flags()

        self.assertEqual(result["status"], "unhealthy")
        self.assertIn("error", result)
        self.assertEqual(result["details"], "Feature flags check failed")
        mock_logger.error.assert_called_once()

    @override_settings(DISPATCHERD_ENABLED=True)
    @patch("apps.health.checks.settings")
    def test_check_dispatcherd_enabled_success(self, mock_settings):
        """Test dispatcherd check when enabled."""
        mock_settings.DISPATCHERD_ENABLED = True
        mock_settings.DISPATCHERD_CONFIG = {"workers": 4, "timeout": 300}

        result = check_dispatcherd()

        self.assertEqual(result["status"], "healthy")
        self.assertTrue(result["enabled"])
        self.assertEqual(result["config"], mock_settings.DISPATCHERD_CONFIG)
        self.assertIn("details", result)
