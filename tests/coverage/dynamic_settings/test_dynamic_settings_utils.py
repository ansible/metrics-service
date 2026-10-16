"""
Unit tests for apps/dynamic_settings/utils.py.
Targets 0% → ~90% coverage.
"""

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# initialize_default_settings
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_initialize_default_settings_runs_without_error():
    """initialize_default_settings completes without raising (no-op when no true rows exist)."""
    from apps.dynamic_settings.utils import initialize_default_settings

    initialize_default_settings()  # idempotent — safe to call multiple times
    initialize_default_settings()


@pytest.mark.unit
@pytest.mark.django_db
def test_initialize_default_settings_deletes_redundant_true_row():
    """Upgrade failsafe: any `true` row for a FEATURE flag is deleted so that
    METRICS_SERVICE_FEATURE__<KEY>=false takes effect without a DB update."""
    import json

    from django.test import override_settings

    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import initialize_default_settings

    # Simulate old init-default-settings having written True into the DB
    Setting.objects.update_or_create(
        setting_key="ANONYMIZED_DATA_COLLECTION",
        defaults={"current_value": json.dumps(True)},
    )

    with override_settings(FEATURE={"ANONYMIZED_DATA_COLLECTION": True}):
        initialize_default_settings()

    # Row is gone — env var (or static default) now applies at runtime
    assert not Setting.objects.filter(setting_key="ANONYMIZED_DATA_COLLECTION").exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_initialize_default_settings_keeps_false_row():
    """`false` rows are an explicit opt-out and must survive upgrade."""
    import json

    from django.test import override_settings

    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import initialize_default_settings

    Setting.objects.update_or_create(
        setting_key="ANONYMIZED_DATA_COLLECTION",
        defaults={"current_value": json.dumps(False)},
    )

    with override_settings(FEATURE={"ANONYMIZED_DATA_COLLECTION": True}):
        initialize_default_settings()

    row = Setting.objects.get(setting_key="ANONYMIZED_DATA_COLLECTION")
    assert json.loads(row.current_value) is False  # opt-out preserved


@pytest.mark.unit
@pytest.mark.django_db
def test_initialize_default_settings_cleanup_exception_does_not_propagate():
    """DB errors during cleanup are swallowed and logged — they must not raise."""

    from django.test import override_settings

    from apps.dynamic_settings.utils import initialize_default_settings

    with (
        override_settings(FEATURE={"SOME_FLAG": True}),
        patch("apps.dynamic_settings.utils.Setting.objects.filter", side_effect=Exception("db error")),
    ):
        initialize_default_settings()  # must not raise


# ---------------------------------------------------------------------------
# remove_default_settings
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.django_db
def test_remove_default_settings_removes_unchanged():
    """AAP-77009: remove_default_settings is a no-op for keys not in DEFAULT_SETTINGS.
    Use all_settings=True to remove all settings regardless."""
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import remove_default_settings

    Setting.objects.get_or_create(
        setting_key="METRICS_COLLECTION", defaults={"current_value": "true", "previous_value": None}
    )

    # DEFAULT_SETTINGS is empty — nothing removed by the "known defaults" path
    removed = remove_default_settings()
    assert removed == 0
    assert Setting.objects.filter(setting_key="METRICS_COLLECTION").exists()

    # all_settings=True removes everything unconditionally
    removed_all = remove_default_settings(all_settings=True)
    assert removed_all >= 1
    assert not Setting.objects.filter(setting_key="METRICS_COLLECTION").exists()


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
    """AAP-77009: all_known=True only removes keys present in DEFAULT_SETTINGS.
    Since DEFAULT_SETTINGS is empty, METRICS_COLLECTION is left untouched."""
    from apps.dynamic_settings.models import Setting
    from apps.dynamic_settings.utils import remove_default_settings

    Setting.objects.update_or_create(
        setting_key="METRICS_COLLECTION",
        defaults={"current_value": "false", "previous_value": '"true"'},
    )

    removed = remove_default_settings(all_known=True)
    assert removed == 0
    # Not in DEFAULT_SETTINGS → not touched
    assert Setting.objects.filter(setting_key="METRICS_COLLECTION").exists()


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
