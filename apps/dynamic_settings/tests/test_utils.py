"""
Unit tests for dynamic_settings utility functions.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.dynamic_settings.models import Setting
from apps.dynamic_settings.utils import log_setting_change, rollback_configuration_change
from tests.test_utils import get_test_password

User = get_user_model()


@pytest.mark.unit
@pytest.mark.django_db
class TestLogSettingChange(TestCase):
    """Test log_setting_change utility function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_log_setting_change_basic(self):
        """Test basic setting change logging."""
        result = log_setting_change(self.user, "TEST_SETTING", {"new": "value"})

        assert result is not None
        assert result.setting_key == "TEST_SETTING"
        assert result.last_modified_by == self.user

    def test_log_setting_change_with_old_value(self):
        """Test logging setting change with old value."""
        old_value = {"old": "value"}
        new_value = {"new": "value"}

        result = log_setting_change(self.user, "TEST_SETTING", new_value, old_value)

        assert result is not None
        assert result.setting_key == "TEST_SETTING"

    def test_log_setting_change_none_user(self):
        """Test logging setting change with None user."""
        result = log_setting_change(None, "TEST_SETTING", {"value": "test"})

        # Should handle None user gracefully
        assert result is not None
        assert result.last_modified_by is None

    def test_log_setting_change_sensitive_setting_redacted(self):
        """Test that sensitive settings are redacted."""
        result = log_setting_change(self.user, "SECRET_KEY", "super-secret-value")

        assert result is not None
        assert result.current_value == "***REDACTED***"

    def test_log_setting_change_update_existing(self):
        """Test updating an existing setting."""
        # Create initial setting
        log_setting_change(self.user, "UPDATE_TEST", "initial")

        # Update it
        result = log_setting_change(self.user, "UPDATE_TEST", "updated", "initial")

        assert result is not None
        assert '"updated"' in result.current_value
        assert '"initial"' in result.previous_value


@pytest.mark.unit
@pytest.mark.django_db
class TestRollbackConfigurationChange(TestCase):
    """Test rollback_configuration_change utility function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password=get_test_password()
        )

    def test_rollback_nonexistent_setting(self):
        """Test rollback of nonexistent setting."""
        result = rollback_configuration_change(99999, self.user)

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_rollback_sensitive_setting_rejected(self):
        """Test that rollback of sensitive settings is rejected."""
        setting = Setting.objects.create(
            setting_key="SECRET_KEY",
            current_value="***REDACTED***",
            previous_value="***REDACTED***",
            last_modified_by=self.user,
        )

        result = rollback_configuration_change(setting.id, self.user)

        assert result["success"] is False
        assert "sensitive" in result["error"].lower()

    @patch("metrics_service.settings.DYNACONF")
    def test_rollback_success(self, mock_dynaconf):
        """Test successful rollback."""
        setting = Setting.objects.create(
            setting_key="TEST_SETTING",
            current_value='"new_value"',
            previous_value='"old_value"',
            last_modified_by=self.user,
        )

        result = rollback_configuration_change(setting.id, self.user)

        assert result["success"] is True
        assert result["setting_key"] == "TEST_SETTING"
        assert result["rolled_back_to"] == "old_value"
        mock_dynaconf.set.assert_called_once_with("TEST_SETTING", "old_value")
