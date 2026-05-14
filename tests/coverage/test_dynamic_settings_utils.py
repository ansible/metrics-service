"""
Unit tests for apps/dynamic_settings/utils.py.
Targets 0% → ~90% coverage.
"""

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# _parse_setting_value
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_parse_setting_value_valid_json_string():
    from apps.dynamic_settings.utils import _parse_setting_value

    assert _parse_setting_value('"hello"') == "hello"


@pytest.mark.unit
def test_parse_setting_value_valid_json_bool_true():
    from apps.dynamic_settings.utils import _parse_setting_value

    assert _parse_setting_value("true") is True


@pytest.mark.unit
def test_parse_setting_value_valid_json_bool_false():
    from apps.dynamic_settings.utils import _parse_setting_value

    assert _parse_setting_value("false") is False


@pytest.mark.unit
def test_parse_setting_value_valid_json_number():
    from apps.dynamic_settings.utils import _parse_setting_value

    assert _parse_setting_value("42") == 42


@pytest.mark.unit
def test_parse_setting_value_invalid_json_returns_string():
    from apps.dynamic_settings.utils import _parse_setting_value

    assert _parse_setting_value("not-json") == "not-json"


@pytest.mark.unit
def test_parse_setting_value_none_returns_none():
    from apps.dynamic_settings.utils import _parse_setting_value

    assert _parse_setting_value(None) is None


@pytest.mark.unit
def test_parse_setting_value_empty_string_returns_none():
    from apps.dynamic_settings.utils import _parse_setting_value

    assert _parse_setting_value("") is None


# ---------------------------------------------------------------------------
# initialize_default_settings
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_initialize_default_settings_creates_records():
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import DEFAULT_SETTINGS, initialize_default_settings

    # Ensure fresh state
    Setting.objects.filter(setting_key__in=DEFAULT_SETTINGS.keys()).delete()

    initialize_default_settings()

    for key in DEFAULT_SETTINGS:
        assert Setting.objects.filter(setting_key=key).exists(), f"Missing setting: {key}"


@pytest.mark.unit
@pytest.mark.django_db
def test_initialize_default_settings_skips_existing():
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import DEFAULT_SETTINGS, initialize_default_settings

    Setting.objects.filter(setting_key__in=DEFAULT_SETTINGS.keys()).delete()
    initialize_default_settings()
    count_after_first = Setting.objects.filter(setting_key__in=DEFAULT_SETTINGS.keys()).count()

    # Second call should not duplicate
    initialize_default_settings()
    count_after_second = Setting.objects.filter(setting_key__in=DEFAULT_SETTINGS.keys()).count()
    assert count_after_second == count_after_first


@pytest.mark.unit
@pytest.mark.django_db
def test_initialize_default_settings_overwrite_recreates():
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import DEFAULT_SETTINGS, initialize_default_settings

    Setting.objects.filter(setting_key__in=DEFAULT_SETTINGS.keys()).delete()
    initialize_default_settings()
    # Should complete without error
    initialize_default_settings(overwrite=True)
    # Settings should still exist
    for key in DEFAULT_SETTINGS:
        assert Setting.objects.filter(setting_key=key).exists()


# ---------------------------------------------------------------------------
# remove_default_settings
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_remove_default_settings_removes_unchanged():
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import remove_default_settings

    Setting.objects.get_or_create(setting_key="METRICS_COLLECTION", defaults={"current_value": "true", "previous_value": None})

    removed = remove_default_settings()
    assert removed >= 1
    assert not Setting.objects.filter(setting_key="METRICS_COLLECTION", previous_value=None).exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_remove_default_settings_preserves_modified():
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import remove_default_settings

    Setting.objects.update_or_create(
        setting_key="METRICS_COLLECTION",
        defaults={"current_value": "false", "previous_value": '"true"'},
    )

    remove_default_settings(all_known=False)
    # Modified setting (previous_value != None) should be preserved
    assert Setting.objects.filter(setting_key="METRICS_COLLECTION").exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_remove_default_settings_all_known_removes_modified():
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import remove_default_settings

    Setting.objects.update_or_create(
        setting_key="METRICS_COLLECTION",
        defaults={"current_value": "false", "previous_value": '"true"'},
    )

    remove_default_settings(all_known=True)
    assert not Setting.objects.filter(setting_key="METRICS_COLLECTION").exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_remove_default_settings_all_settings_removes_all():
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import remove_default_settings

    Setting.objects.create(setting_key="CUSTOM_SETTING", current_value="value")
    Setting.objects.get_or_create(setting_key="METRICS_COLLECTION", defaults={"current_value": "true"})

    removed = remove_default_settings(all_settings=True)
    assert Setting.objects.count() == 0
    assert removed >= 2


# ---------------------------------------------------------------------------
# log_setting_change
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_log_setting_change_creates_record(user):
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import log_setting_change

    result = log_setting_change(user, "MY_NEW_SETTING", "new_value")

    assert result is not None
    setting = Setting.objects.get(setting_key="MY_NEW_SETTING")
    assert setting.current_value == '"new_value"'  # JSON encoded
    assert setting.last_modified_by == user


@pytest.mark.unit
@pytest.mark.django_db
def test_log_setting_change_updates_existing(user):
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import log_setting_change

    # Create first
    log_setting_change(user, "UPDATE_SETTING", "first_value")
    # Update with new value — old current_value becomes previous_value
    log_setting_change(user, "UPDATE_SETTING", "second_value", old_value="first_value")

    setting = Setting.objects.get(setting_key="UPDATE_SETTING")
    assert '"second_value"' in setting.current_value
    assert '"first_value"' in setting.previous_value


@pytest.mark.unit
@pytest.mark.django_db
def test_log_setting_change_redacts_sensitive(user):
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import log_setting_change

    result = log_setting_change(user, "SECRET_KEY", "super_secret_value")

    setting = Setting.objects.get(setting_key="SECRET_KEY")
    assert setting.current_value == "***REDACTED***"


@pytest.mark.unit
@pytest.mark.django_db
def test_log_setting_change_redacts_password(user):
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import log_setting_change

    log_setting_change(user, "DATABASE_PASSWORD", "my_password")
    setting = Setting.objects.get(setting_key="DATABASE_PASSWORD")
    assert setting.current_value == "***REDACTED***"


# ---------------------------------------------------------------------------
# rollback_configuration_change
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_rollback_configuration_change_success(user):
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import rollback_configuration_change

    setting = Setting.objects.create(
        setting_key="ROLLBACK_FLAG",
        current_value='"false"',
        previous_value='"true"',
        last_modified_by=user,
    )

    with patch("metrics_service.settings.DYNACONF") as mock_dynaconf:
        result = rollback_configuration_change(setting.id, user)

    assert result["success"] is True
    assert result["setting_key"] == "ROLLBACK_FLAG"


@pytest.mark.unit
@pytest.mark.django_db
def test_rollback_configuration_change_not_found(user):
    from apps.dynamic_settings.utils import rollback_configuration_change

    result = rollback_configuration_change(99999, user)
    assert result["success"] is False
    assert "not found" in result["error"]


@pytest.mark.unit
@pytest.mark.django_db
def test_rollback_configuration_change_blocked_for_sensitive(user):
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import rollback_configuration_change

    setting = Setting.objects.create(
        setting_key="REDACTED_SETTING",
        current_value="***REDACTED***",
        previous_value="***REDACTED***",
        last_modified_by=user,
    )

    result = rollback_configuration_change(setting.id, user)
    assert result["success"] is False
    assert "sensitive" in result["error"].lower()
