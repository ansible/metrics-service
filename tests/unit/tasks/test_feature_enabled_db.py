"""
Unit tests for database-driven feature enabled functionality.

Tests the new feature enabled system that stores settings in the database
with fallback to Django settings and defaults.
"""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.tasks.task_groups import (
    get_feature_enabled_from_db,
)
from tests.test_utils import get_test_password

User = get_user_model()


class TestFeatureEnabledDB(TestCase):
    """Test database-driven feature enabled functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_get_feature_enabled_from_db_no_setting(self):
        """Test getting feature enabled when no database setting exists."""
        # Should return default when no setting in DB or Django settings
        result = get_feature_enabled_from_db("NONEXISTENT_SETTING", default=True)
        assert result is True

        result = get_feature_enabled_from_db("NONEXISTENT_SETTING", default=False)
        assert result is False

    @override_settings(FEATURE_ENABLED={"TEST_SETTING": True})
    def test_get_feature_enabled_from_django_settings(self):
        """Test getting feature enabled from Django settings when no DB setting."""
        result = get_feature_enabled_from_db("TEST_SETTING", default=False)
        assert result is True

    def test_get_feature_enabled_from_db_json_value(self):
        """Test getting feature enabled from database with JSON value."""
        from apps.dynamic_settings.models import Setting

        # Create a setting with JSON boolean value
        Setting.objects.create(
            setting_key="JSON_TEST_SETTING", current_value=json.dumps(True), last_modified_by=self.user
        )

        result = get_feature_enabled_from_db("JSON_TEST_SETTING", default=False)
        assert result is True

        # Test with False JSON value
        Setting.objects.filter(setting_key="JSON_TEST_SETTING").update(current_value=json.dumps(False))

        result = get_feature_enabled_from_db("JSON_TEST_SETTING", default=True)
        assert result is False

    def test_get_feature_enabled_from_db_string_value(self):
        """Test getting feature enabled from database with string boolean value."""
        from apps.dynamic_settings.models import Setting

        # Test various string representations of True
        for true_value in ["true", "True", "TRUE", "1", "yes", "YES", "on", "ON"]:
            Setting.objects.update_or_create(
                setting_key="STRING_TEST_SETTING", defaults={"current_value": true_value, "last_modified_by": self.user}
            )

            result = get_feature_enabled_from_db("STRING_TEST_SETTING", default=False)
            assert result is True, f"Failed for value: {true_value}"

        # Test various string representations of False
        for false_value in ["false", "False", "FALSE", "0", "no", "NO", "off", "OFF"]:
            Setting.objects.update_or_create(
                setting_key="STRING_TEST_SETTING",
                defaults={"current_value": false_value, "last_modified_by": self.user},
            )

            result = get_feature_enabled_from_db("STRING_TEST_SETTING", default=True)
            assert result is False, f"Failed for value: {false_value}"

    def test_get_feature_enabled_from_db_invalid_json(self):
        """Test getting feature enabled when database has invalid JSON."""
        from apps.dynamic_settings.models import Setting

        # Create setting with invalid JSON
        Setting.objects.create(
            setting_key="INVALID_JSON_SETTING", current_value="invalid json {", last_modified_by=self.user
        )

        # Should treat as string boolean and return False (invalid string)
        result = get_feature_enabled_from_db("INVALID_JSON_SETTING", default=True)
        assert result is False

    @patch("apps.tasks.task_groups.logger")
    def test_get_feature_enabled_from_db_exception(self, mock_logger):
        """Test getting feature enabled when database query raises exception."""
        with patch("apps.dynamic_settings.models.Setting.objects.filter", side_effect=Exception("DB Error")):
            result = get_feature_enabled_from_db("ERROR_SETTING", default=True)
            assert result is True
            mock_logger.warning.assert_called_once()
