"""
Settings API views — singleton GET/PATCH for runtime feature flag management.
"""

import json
import logging

from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dynamic_settings.models import Setting
from apps.dynamic_settings.registry import SETTINGS_REGISTRY
from apps.dynamic_settings.utils import log_setting_change

logger = logging.getLogger(__name__)

_SENSITIVE_SENTINEL = None  # returned in GET responses for sensitive settings


def _resolve_current_value(key: str, row: "Setting | None", defn) -> "bool | int | str | None":
    """Return the configured value: DB row > FEATURE dict > AAPFlag/settings attr > registry default.

    Returns None for sensitive settings — the actual value is never exposed via the API.

    Uses get_feature_enabled_from_db() as the fallback so that flags not in the FEATURE dict
    (e.g. INDIRECT_NODE_COLLECTION) correctly reflect a platform AAPFlag when one exists.
    """
    if defn.sensitive:
        return _SENSITIVE_SENTINEL

    if row and row.current_value:
        try:
            return json.loads(row.current_value)
        except (json.JSONDecodeError, ValueError):
            return row.current_value.lower() in ("true", "1", "yes", "on")

    # Lazy import — avoids a circular import at module load time while still reaching
    # the full resolution chain: FEATURE dict → settings attr → AAPFlag → default.
    if defn.type == "boolean":
        try:
            from apps.tasks.task_groups import get_feature_enabled_from_db

            return get_feature_enabled_from_db(key, default=defn.default)
        except Exception:
            return defn.default
    else:
        # For integer/string settings: check Django settings attr, then default
        from django.conf import settings as django_settings

        return getattr(django_settings, key, defn.default)


def _compute_effective_value(key: str, raw_values: dict) -> "bool | int | str | None":
    """Return the effective value accounting for the full requires chain.

    A flag's effective value is False when its own raw value is False OR when any flag it
    requires (directly or transitively) is effectively False. Sensitive settings return None.

    raw_values must contain resolved values for every key in SETTINGS_REGISTRY.
    """
    defn = SETTINGS_REGISTRY[key]
    if defn.sensitive:
        return _SENSITIVE_SENTINEL

    own = raw_values.get(key, defn.default)
    if not own:
        return own  # already False/falsy — no need to walk deps

    for req_key in defn.requires:
        if not _compute_effective_value(req_key, raw_values):
            return False

    return own


def _collect_dependency_warnings(raw_values: dict) -> dict[str, str]:
    """Return advisory messages for flags whose requires dependencies are not all satisfied.

    Only flags that are themselves enabled (value=True) but have a disabled required
    flag are reported — disabled flags with unsatisfied deps don't need a warning
    because they're already off.
    """
    messages: dict[str, str] = {}
    for key, defn in SETTINGS_REGISTRY.items():
        if defn.sensitive or not defn.requires:
            continue
        own = raw_values.get(key, defn.default)
        if not own:
            continue  # already off — no warning needed
        broken = [r for r in defn.requires if not raw_values.get(r, SETTINGS_REGISTRY[r].default)]
        if broken:
            messages[key] = f"{key} is enabled but will have no effect: required flag(s) disabled: {', '.join(broken)}."
    return messages


def _build_entry(key: str, defn, row: "Setting | None", raw_values: dict) -> dict:
    """Build the response dict for a single setting entry."""
    return {
        "value": raw_values[key],
        "effective_value": _compute_effective_value(key, raw_values),
        "default": defn.default,
        "type": defn.type,
        "label": defn.label,
        "description": defn.description,
        "requires": defn.requires,
        "modified": row.modified.isoformat() if row else None,
        "modified_by": row.last_modified_by.username if row and row.last_modified_by else None,
    }


def _validate_setting(key: str, value, defn, *, category: str | None = None) -> str | None:
    """Validate a single key/value pair against the registry.

    Returns an error string if invalid, None if valid.

    Args:
        key: The setting key from the request.
        value: The proposed new value.
        defn: The SettingDef for this key.
        category: When set, rejects keys whose category differs from this value.
        allowed_keys: When set, rejects keys not in this dict.
    """
    if defn.sensitive:
        return "This setting is sensitive and cannot be updated via the API."
    if category is not None and defn.category != category:
        return f"Setting '{key}' belongs to category '{defn.category}', not '{category}'."
    if defn.type == "boolean" and not isinstance(value, bool):
        return "Must be a boolean (true or false)."
    if defn.type == "integer":
        if not isinstance(value, int):
            return "Must be an integer."
        if defn.min_value is not None and value < defn.min_value:
            limit = "0 or greater" if defn.min_value == 0 else "a positive integer"
            return f"Must be {limit}."
    return None


def _validate_patch_data(data: dict, *, category: str | None = None) -> tuple[dict, dict]:
    """Validate a PATCH request body against the registry.

    Returns ``(errors, updates)`` where errors maps invalid keys to error messages
    and updates maps valid keys to their new values.  Unknown keys always produce
    an error.  When ``category`` is given, keys from other categories are rejected.
    """
    errors: dict = {}
    updates: dict = {}

    for key, value in data.items():
        if key not in SETTINGS_REGISTRY:
            hint = sorted(SETTINGS_REGISTRY) if category is None else f"the '{category}' category"
            errors[key] = f"Unknown setting. Valid keys: {hint}."
            continue
        defn = SETTINGS_REGISTRY[key]
        error = _validate_setting(key, value, defn, category=category)
        if error:
            errors[key] = error
        else:
            updates[key] = value

    return errors, updates


def _persist_updates(user, updates: dict) -> None:
    """Write validated updates to the Setting DB and emit log lines."""
    for key, value in updates.items():
        defn = SETTINGS_REGISTRY[key]
        try:
            old_row = Setting.objects.filter(setting_key=key).first()
            old_value = _resolve_current_value(key, old_row, defn)
        except Exception:
            old_value = defn.default
        log_setting_change(user, key, value, old_value)
        logger.info("Setting %s updated to %r by %s", key, value, user)


class SettingsView(APIView):
    """
    GET  /api/v1/settings/  — list all settings grouped by category with metadata.
    PATCH /api/v1/settings/ — update one or more settings by key.

    Only known keys from SETTINGS_REGISTRY are accepted. Changes take effect on the
    next scheduler tick (<=30s) without a restart.

    Each setting entry includes:
      value           — the configured value (DB row > FEATURE dict > AAPFlag > default)
      effective_value — value after propagating requires dependencies; False when any
                        required flag is disabled, regardless of this flag's own value
      requires        — list of flags that must be enabled for this flag to have effect
    """

    permission_classes = [IsSystemAdminOrAuditor]

    def get(self, request: Request) -> Response:
        db_settings = {s.setting_key: s for s in Setting.objects.all()}
        raw_values: dict = {
            key: _resolve_current_value(key, db_settings.get(key), defn) for key, defn in SETTINGS_REGISTRY.items()
        }

        result: dict = {}
        for key, defn in SETTINGS_REGISTRY.items():
            category = result.setdefault(defn.category, {})
            category[key] = _build_entry(key, defn, db_settings.get(key), raw_values)

        return Response(result)

    def patch(self, request: Request) -> Response:
        if not isinstance(request.data, dict):
            return Response({"detail": "Expected a JSON object."}, status=400)

        errors, updates = _validate_patch_data(request.data)

        if errors:
            return Response(errors, status=400)
        if not updates:
            return Response({"detail": "No valid settings provided."}, status=400)

        _persist_updates(request.user, updates)

        db_settings = {s.setting_key: s for s in Setting.objects.all()}
        raw_values = {k: _resolve_current_value(k, db_settings.get(k), d) for k, d in SETTINGS_REGISTRY.items()}
        warnings = _collect_dependency_warnings(raw_values)

        response = self.get(request)
        if warnings:
            response.data["warnings"] = warnings
        return response


class SettingsCategoryView(APIView):
    """
    GET  /api/v1/settings/<category>/  — all settings for a single category.
    PATCH /api/v1/settings/<category>/ — update settings within this category only.

    Returns 404 when the category name is not in SETTINGS_REGISTRY.
    PATCH rejects keys that belong to a different category with 400.
    """

    permission_classes = [IsSystemAdminOrAuditor]

    def _category_keys(self, category: str) -> dict:
        return {k: v for k, v in SETTINGS_REGISTRY.items() if v.category == category}

    def get(self, request: Request, category: str) -> Response:
        keys = self._category_keys(category)
        if not keys:
            return Response({"detail": f"Unknown settings category: {category!r}."}, status=404)

        db_settings = {s.setting_key: s for s in Setting.objects.filter(setting_key__in=keys)}
        raw_values = {
            key: _resolve_current_value(key, db_settings.get(key), defn) for key, defn in SETTINGS_REGISTRY.items()
        }

        result = {key: _build_entry(key, defn, db_settings.get(key), raw_values) for key, defn in keys.items()}
        return Response(result)

    def patch(self, request: Request, category: str) -> Response:
        keys = self._category_keys(category)
        if not keys:
            return Response({"detail": f"Unknown settings category: {category!r}."}, status=404)

        if not isinstance(request.data, dict):
            return Response({"detail": "Expected a JSON object."}, status=400)

        errors, updates = _validate_patch_data(request.data, category=category)

        if errors:
            return Response(errors, status=400)
        if not updates:
            return Response({"detail": "No valid settings provided."}, status=400)

        _persist_updates(request.user, updates)

        db_settings = {s.setting_key: s for s in Setting.objects.filter(setting_key__in=keys)}
        raw_values_all = {k: _resolve_current_value(k, db_settings.get(k), d) for k, d in SETTINGS_REGISTRY.items()}
        warnings = {k: v for k, v in _collect_dependency_warnings(raw_values_all).items() if k in keys}

        response = self.get(request, category)
        if warnings:
            response.data["warnings"] = warnings
        return response
