"""
Utility functions for dynamic settings management.

This module provides functions for logging setting changes and
rolling back configuration changes.
"""

import json
import logging

from .models import Setting

logger = logging.getLogger(__name__)


def log_setting_change(user, setting_key: str, new_value, old_value=None):
    """
    Log a settings change to the database.

    Args:
        user: User making the change
        setting_key: The setting key being changed
        new_value: The new value
        old_value: Optional old value from DYNACONF (before the change)

    Returns:
        Setting object if successful, None if failed
    """

    # List of sensitive settings that should be redacted
    sensitive_settings = [
        "SECRET_KEY",
        "PASSWORD",
        "DATABASES",
        "JWT_SECRET",
        "API_KEY",
    ]

    # Check if this setting is sensitive
    is_sensitive = any(sensitive in setting_key.upper() for sensitive in sensitive_settings)

    # Redact sensitive values
    if is_sensitive:
        new_value_to_store = "***REDACTED***"
        old_value_to_store = "***REDACTED***" if old_value is not None else None
    else:
        # Convert values to JSON strings for storage
        try:
            new_value_to_store = json.dumps(new_value) if new_value is not None else None
        except (TypeError, ValueError):
            # If we can't convert to JSON, just convert to string
            new_value_to_store = str(new_value) if new_value is not None else None

        try:
            old_value_to_store = json.dumps(old_value) if old_value is not None else None
        except (TypeError, ValueError):
            # If we can't convert to JSON, just convert to string
            old_value_to_store = str(old_value) if old_value is not None else None

    try:
        setting, created = Setting.objects.get_or_create(
            setting_key=setting_key,
            defaults={
                "last_modified_by": user,
                "previous_value": old_value_to_store,  # Use the actual DYNACONF value
                "current_value": new_value_to_store,
            },
        )

        # If setting already existed, update it with new values
        if not created:
            # Use old_value if provided (actual DYNACONF value), otherwise use DB's current_value
            setting.previous_value = old_value_to_store if old_value is not None else setting.current_value
            setting.current_value = new_value_to_store
            setting.last_modified_by = user
            setting.save()

        logger.info(
            f"Setting change logged: {setting_key} changed to {new_value} by {user.username if user else 'System'}"
        )

        return setting

    except Exception as e:
        logger.error(f"Failed to log setting change for {setting_key}: {str(e)}")
        return None


def _parse_setting_value(value_str):
    """
    Helper to parse a setting value from JSON string.
    Returns the parsed value or the original string if parsing fails.
    """
    if not value_str:
        return None
    try:
        return json.loads(value_str)
    except (json.JSONDecodeError, TypeError):
        return value_str


def rollback_configuration_change(change_id, user):
    """
    Undo a settings change by its key id.
    """
    from metrics_service.settings import DYNACONF

    try:
        setting = Setting.objects.get(id=change_id)
    except Setting.DoesNotExist:
        logger.error(f"Configuration change with ID {change_id} not found")
        return {"success": False, "error": f"Configuration change with ID {change_id} not found"}

    # Check if we can actually rollback this setting
    if setting.previous_value == "***REDACTED***" or setting.current_value == "***REDACTED***":
        logger.warning(f"Cannot rollback sensitive setting: {setting.setting_key}")
        return {"success": False, "error": f"Cannot rollback sensitive setting: {setting.setting_key}"}

    try:
        # Parse values from JSON
        previous_value = _parse_setting_value(setting.previous_value)
        current_value = _parse_setting_value(setting.current_value)

        # Rollback - set it back to the old value!
        DYNACONF.set(setting.setting_key, previous_value)

        # Write new entry about the rollback to the db
        log_setting_change(
            user=user,
            setting_key=setting.setting_key,
            new_value=previous_value,
            old_value=current_value,  # The value before rollback
        )

        logger.info(
            f"Rolled back {setting.setting_key} to previous value {setting.previous_value} by {user.username if user else 'System'}"
        )

        return {
            "success": True,
            "setting_key": setting.setting_key,
            "rolled_back_to": previous_value,
            "message": f"Successfully rolled back {setting.setting_key}",
        }

    except Exception as e:
        logger.error(f"Failed to rollback configuration change {change_id}: {str(e)}")
        return {"success": False, "error": f"Failed to rollback: {str(e)}"}


# Define default feature flags - same as in initialize_default_settings
# default_value is the fallback, set the actual default in apps/settings/defaults.py
DEFAULT_SETTINGS = {
    "ANONYMIZED_DATA_COLLECTION": {
        "default_value": True,
        "description": "Enable anonymized data collection and transmission to Red Hat (includes metrics collection, rollup, anonymization, and sending)",
    },
}


def _remove_all_settings():
    deleted_count, _ = Setting.objects.all().delete()
    return deleted_count


def _remove_known_settings(including_changed=False):
    removed_count = 0

    for setting_key in DEFAULT_SETTINGS:
        if including_changed:
            # remove all known defaults regardless of modification status
            deleted_count, _ = Setting.objects.filter(setting_key=setting_key).delete()
        else:
            # default: only remove unchanged settings
            deleted_count, _ = Setting.objects.filter(setting_key=setting_key, previous_value=None).delete()

        if deleted_count > 0:
            logger.info(f"Removed setting '{setting_key}'")
            removed_count += deleted_count

    return removed_count


# uv run ./manage.py metrics_service remove-default-settings [--all-known] [--all-settings]
def remove_default_settings(all_known: bool = False, all_settings: bool = False):
    """
    Remove default feature flag settings from the database.

    Args:
        all_known: If True, remove all known default settings (ignores previous_value logic)
        all_settings: If True, remove all settings from database (ignores DEFAULT_SETTINGS known settings list)

    Default behavior (both False):
        Only removes settings that match DEFAULT_SETTINGS keys and have
        previous_value=None (indicating they haven't been modified by a user).
        Settings that have been modified (have a previous_value) are preserved.

    With all_known=True:
        Removes all settings in DEFAULT_SETTINGS, even if they have been modified.

    With all_settings=True:
        Removes ALL settings from the database, not just those in DEFAULT_SETTINGS.
        Takes precedence over all_known.
    """
    removed_count = _remove_all_settings() if all_settings else _remove_known_settings(all_known)

    if removed_count > 0:
        logger.info(f"Removed {removed_count} settings from database")
    else:
        logger.debug("No settings found to remove")

    return removed_count


# uv run ./manage.py metrics_service init-default-settings
def initialize_default_settings(overwrite: bool = False):
    """
    Initialize or update default feature flag settings in the database.

    Args:
        overwrite: If True, remove all known default settings before reinitializing
                   (passes all_known=True to remove_default_settings)

    This function removes unchanged default settings (those with previous_value=None)
    and recreates them with current values from configuration. Modified settings
    (those with a previous_value) are preserved and never overwritten, unless
    overwrite=True is specified.

    This ensures default settings stay in sync with configuration while respecting
    user modifications.
    """
    from django.conf import settings as django_settings

    # Remove existing defaults (all known if overwrite=True, otherwise just unchanged)
    remove_default_settings(all_known=overwrite)

    created_count = 0
    skipped_count = 0

    for setting_key, config in DEFAULT_SETTINGS.items():
        # Check if setting already exists
        existing = Setting.objects.filter(setting_key=setting_key).first()

        if existing:
            logger.debug(f"Setting '{setting_key}' already exists with value: {existing.current_value}")
            skipped_count += 1
            continue

        # Get default value from Django settings FEATURE_ENABLED dict, or use hardcoded default
        feature_enabled = getattr(django_settings, "FEATURE_ENABLED", {})
        default_value = feature_enabled.get(setting_key, config["default_value"])

        # Create the setting
        Setting.objects.create(
            setting_key=setting_key,
            current_value=json.dumps(default_value),
            previous_value=None,
            last_modified_by=None,  # System initialization
        )

        logger.info(
            f"Initialized setting '{setting_key}' with default value: {default_value} ({config['description']})"
        )
        created_count += 1

    if created_count > 0:
        logger.info(f"Initialized {created_count} default settings in database")
    if skipped_count > 0:
        logger.debug(f"Skipped {skipped_count} existing settings")
