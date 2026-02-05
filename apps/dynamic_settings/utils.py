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


# FIXME: why are these default not read from actual settings/defaults?
def initialize_default_settings():
    """
    Initialize default feature flag settings in the database on application startup.

    This ensures that all feature flags are visible in the database and can be
    easily discovered and modified by administrators.
    """
    from django.conf import settings as django_settings

    # Define default feature flags and their values
    default_settings = {
        "METRICS_COLLECTION_ENABLED": {
            "default_value": False,
            "description": "Enable hourly metrics collection with daily rollup and anonymization",
        },
        "ANONYMIZED_DATA_COLLECTION": {
            "default_value": True,
            "description": "Enable anonymous data collection for Red Hat",
        },
    }

    created_count = 0
    skipped_count = 0

    for setting_key, config in default_settings.items():
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
