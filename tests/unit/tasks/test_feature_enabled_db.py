"""
Unit tests for database-driven feature enabled functionality.

Tests the new feature enabled system that stores settings in the database
with fallback to Django settings and defaults.
"""

import json
from unittest.mock import MagicMock, patch

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


class TestFeatureEnabledAAPFlagFallback(TestCase):
    """Test AAPFlag is used as the second fallback in get_feature_enabled_from_db.

    Priority chain:
      1. dynamic_settings.Setting  (runtime DB override)
      2. AAPFlag.value             (YAML-seeded default)
      3. settings.FEATURE_ENABLED  (Django settings)
      4. default argument
    """

    def _make_mock_flag(self, value: str) -> MagicMock:
        flag = MagicMock()
        flag.value = value
        return flag

    def _patch_aap_flag(self, flag_instance):
        """Patch AAPFlag at its source module so the local import inside the function picks it up."""
        return patch("ansible_base.feature_flags.models.AAPFlag", **{"objects.filter.return_value.first.return_value": flag_instance})

    # ------------------------------------------------------------------
    # AAPFlag fallback — basic true / false
    # ------------------------------------------------------------------

    def test_aap_flag_true_returns_true(self):
        """Returns True when AAPFlag.value is 'True' and no Setting exists."""
        with self._patch_aap_flag(self._make_mock_flag("True")):
            assert get_feature_enabled_from_db("MY_FLAG", default=False) is True

    def test_aap_flag_false_returns_false(self):
        """Returns False when AAPFlag.value is 'False' and no Setting exists."""
        with self._patch_aap_flag(self._make_mock_flag("False")):
            assert get_feature_enabled_from_db("MY_FLAG", default=True) is False

    def test_aap_flag_string_variants(self):
        """AAPFlag.value truthy strings are all accepted."""
        for truthy in ("true", "True", "TRUE", "1", "yes", "on"):
            with self._patch_aap_flag(self._make_mock_flag(truthy)):
                assert get_feature_enabled_from_db("MY_FLAG", default=False) is True, truthy

        for falsy in ("false", "False", "0", "no", "off"):
            with self._patch_aap_flag(self._make_mock_flag(falsy)):
                assert get_feature_enabled_from_db("MY_FLAG", default=True) is False, falsy

    # ------------------------------------------------------------------
    # Name mapping: setting_name → FEATURE_<setting_name>_ENABLED
    # ------------------------------------------------------------------

    def test_aap_flag_queried_with_correct_name(self):
        """AAPFlag is looked up using the FEATURE_<setting_name>_ENABLED convention."""
        mock_aap_flag_class = MagicMock()
        mock_aap_flag_class.objects.filter.return_value.first.return_value = None

        with patch("ansible_base.feature_flags.models.AAPFlag", mock_aap_flag_class):
            get_feature_enabled_from_db("DASHBOARD_COLLECTION", default=False)

        mock_aap_flag_class.objects.filter.assert_called_once_with(
            name="FEATURE_DASHBOARD_COLLECTION_ENABLED", condition="boolean"
        )

    # ------------------------------------------------------------------
    # Priority: Setting > AAPFlag > FEATURE_ENABLED > default
    # ------------------------------------------------------------------

    def test_dynamic_setting_takes_precedence_over_aap_flag(self):
        """A dynamic_settings.Setting overrides the AAPFlag value."""
        from apps.dynamic_settings.models import Setting
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(username="prio_test", password="x")  # noqa: S106
        Setting.objects.create(setting_key="PRIO_FLAG", current_value=json.dumps(True), last_modified_by=user)

        # AAPFlag disagrees — says False
        with self._patch_aap_flag(self._make_mock_flag("False")):
            result = get_feature_enabled_from_db("PRIO_FLAG", default=False)

        assert result is True  # Setting wins

    @override_settings(FEATURE_ENABLED={"FALLBACK_FLAG": True})
    def test_aap_flag_takes_precedence_over_feature_enabled_settings(self):
        """AAPFlag value takes priority over settings.FEATURE_ENABLED."""
        # AAPFlag says False; settings says True — AAPFlag wins
        with self._patch_aap_flag(self._make_mock_flag("False")):
            result = get_feature_enabled_from_db("FALLBACK_FLAG", default=True)

        assert result is False

    @override_settings(FEATURE_ENABLED={"SETTINGS_FLAG": True})
    def test_feature_enabled_settings_used_when_no_aap_flag(self):
        """settings.FEATURE_ENABLED is used when AAPFlag returns None."""
        with self._patch_aap_flag(None):
            result = get_feature_enabled_from_db("SETTINGS_FLAG", default=False)

        assert result is True

    def test_default_used_when_nothing_found(self):
        """default argument is returned when Setting, AAPFlag, and FEATURE_ENABLED all miss."""
        with self._patch_aap_flag(None), override_settings(FEATURE_ENABLED={}):
            assert get_feature_enabled_from_db("NONEXISTENT", default=True) is True
            assert get_feature_enabled_from_db("NONEXISTENT", default=False) is False

    # ------------------------------------------------------------------
    # Exception resilience
    # ------------------------------------------------------------------

    def test_aap_flag_exception_falls_through_to_settings(self):
        """An exception inside the AAPFlag block falls through to FEATURE_ENABLED."""
        mock_aap_flag_class = MagicMock()
        mock_aap_flag_class.objects.filter.side_effect = Exception("registry unavailable")

        with patch("ansible_base.feature_flags.models.AAPFlag", mock_aap_flag_class), override_settings(
            FEATURE_ENABLED={"ERR_FLAG": True}
        ):
            result = get_feature_enabled_from_db("ERR_FLAG", default=False)

        assert result is True
