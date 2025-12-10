"""
Core utility functions and helpers for the metrics service.
"""

import json
import logging
import uuid
from typing import Any

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_related_object_safely(instance: Any, field_name: str, default: Any = None) -> Any:
    """
    Safely get a related object from an instance.
    """
    try:
        return getattr(instance, field_name)
    except AttributeError:
        return default
    except instance.DoesNotExist:
        return default


def get_count_safely(queryset_or_manager: Any) -> int:
    """
    Safely get count from a queryset or manager.
    """
    try:
        count_result = queryset_or_manager.count()
        return int(count_result)
    except Exception as e:
        logger.warning(f"Error getting count: {e}")
        return 0


def build_error_response(
    message: str, details: dict[str, Any] | None = None, status_code: int = 400
) -> dict[str, Any]:
    """
    Build a standardized error response dictionary.
    """
    error_response = {
        "error": message,
        "status_code": status_code,
        "timestamp": timezone.now().isoformat(),
    }

    if details:
        error_response["details"] = details

    return error_response


def get_system_uuid() -> str:
    """
    Get system UUID from settings or generate a default one.
    """
    try:
        return getattr(settings, "SYSTEM_UUID", str(uuid.uuid4()))
    except Exception:
        return str(uuid.uuid4())


def is_system_auditor_user(user: Any) -> bool:
    """
    Check if user is a system auditor.
    """
    try:
        if hasattr(user, "is_system_auditor_user") and callable(user.is_system_auditor_user):
            return user.is_system_auditor_user()
        return False
    except Exception:
        return False


def format_task_data(data: Any) -> str:
    """
    Format task data for display.
    """
    try:
        if isinstance(data, str):
            return data
        return json.dumps(data, indent=2)
    except Exception:
        return str(data)


def log_setting_change(user, setting_key: str, new_value, old_value=None):
    """
    Log a settings change to the database.
    """
    from apps.core.models import Setting

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
            new_value_to_store = str(new_value) if new_value is not None else None

        try:
            old_value_to_store = json.dumps(old_value) if old_value is not None else None
        except (TypeError, ValueError):
            old_value_to_store = str(old_value) if old_value is not None else None

    try:
        setting, created = Setting.objects.get_or_create(
            setting_key=setting_key,
            defaults={
                "last_modified_by": user,
                "previous_value": old_value_to_store,
                "current_value": new_value_to_store,
            },
        )

        # If setting already existed, update it with new values
        if not created:
            setting.previous_value = (
                old_value_to_store if old_value is not None else setting.current_value
            )
            setting.current_value = new_value_to_store
            setting.last_modified_by = user
            setting.save()

        logger.info(
            f"Setting change logged: {setting_key} changed by "
            f"{user.username if user else 'System'}"
        )

        return setting

    except Exception as e:
        logger.error(f"Failed to log setting change for {setting_key}: {str(e)}")
        return None


def _parse_setting_value(value_str):
    """
    Helper to parse a setting value from JSON string.
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
    from apps.core.models import Setting
    from metrics_service.settings import DYNACONF

    try:
        setting = Setting.objects.get(id=change_id)
    except Setting.DoesNotExist:
        logger.error(f"Configuration change with ID {change_id} not found")
        return {"success": False, "error": f"Configuration change with ID {change_id} not found"}

    # Check if we can actually rollback this setting
    if setting.previous_value == "***REDACTED***" or setting.current_value == "***REDACTED***":
        logger.warning(f"Cannot rollback sensitive setting: {setting.setting_key}")
        return {
            "success": False,
            "error": f"Cannot rollback sensitive setting: {setting.setting_key}",
        }

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
            old_value=current_value,
        )

        logger.info(
            f"Rolled back {setting.setting_key} to previous value "
            f"by {user.username if user else 'System'}"
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
