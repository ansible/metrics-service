"""Unit tests for Setting model."""

import pytest
from django.contrib.auth import get_user_model

from apps.core.models import Setting

User = get_user_model()


@pytest.mark.unit
@pytest.mark.django_db
class TestSettingModel:
    """Test cases for Setting model."""

    def test_create_setting(self, user):
        """Test setting can be created."""
        setting = Setting.objects.create(
            setting_key="TEST_KEY", current_value="hello", last_modified_by=user, source="api"
        )
        assert setting.setting_key == "TEST_KEY"

    def test_setting_update(self, user):
        """Test setting saves previous value when updated."""
        # Create setting "first"
        setting = Setting.objects.create(
            setting_key="TEST_KEY", current_value="first", previous_value=None, last_modified_by=user, source="api"
        )

        setting.previous_value = setting.current_value
        setting.current_value = "second"
        setting.save()

        # Reload from database
        setting.refresh_from_db()

        # Check previous was saved
        assert setting.previous_value == "first"
        assert setting.current_value == "second"

    def test_setting_string_representation(self, user):
        """Test setting string shows username and key."""
        setting = Setting.objects.create(
            setting_key="TEST_KEY", current_value="test", last_modified_by=user, source="api"
        )

        result = str(setting)
        assert "testuser" in result
        assert "TEST_KEY" in result

    def test_setting_access_qs_regular_user(self, user):
        """Test regular users can't see settings."""
        # Create setting
        Setting.objects.create(setting_key="SECRET", current_value="secret", last_modified_by=user, source="api")

        # Make a regular (not admin) user
        from django.contrib.auth import get_user_model

        User = get_user_model()
        regular_user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="password",
            is_superuser=False,
            is_system_auditor=False,
        )

        # Check they can't see it
        queryset = Setting.access_qs(regular_user)
        assert queryset.count() == 0  # Regular users see nothing.
