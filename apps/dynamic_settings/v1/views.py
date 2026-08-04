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
    try:
        from apps.tasks.task_groups import get_feature_enabled_from_db

        return get_feature_enabled_from_db(key, default=defn.default)
    except Exception:
        return defn.default


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
            messages[key] = (
                f"{key} is enabled but will have no effect: "
                f"required flag(s) disabled: {', '.join(broken)}."
            )
    return messages


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

        # Resolve raw configured values for every key first so effective_value can
        # walk the dependency graph without making repeated DB queries.
        raw_values: dict = {
            key: _resolve_current_value(key, db_settings.get(key), defn)
            for key, defn in SETTINGS_REGISTRY.items()
        }

        result: dict = {}
        for key, defn in SETTINGS_REGISTRY.items():
            row = db_settings.get(key)
            category = result.setdefault(defn.category, {})
            category[key] = {
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

        return Response(result)

    def patch(self, request: Request) -> Response:
        if not isinstance(request.data, dict):
            return Response({"detail": "Expected a JSON object."}, status=400)

        errors: dict = {}
        updates: dict = {}

        for key, value in request.data.items():
            if key not in SETTINGS_REGISTRY:
                errors[key] = f"Unknown setting. Valid keys: {sorted(SETTINGS_REGISTRY)}."
                continue
            defn = SETTINGS_REGISTRY[key]
            if defn.sensitive:
                errors[key] = "This setting is sensitive and cannot be updated via the API."
                continue
            if defn.type == "boolean" and not isinstance(value, bool):
                errors[key] = "Must be a boolean (true or false)."
                continue
            if defn.type == "integer" and not isinstance(value, int):
                errors[key] = "Must be an integer."
                continue
            updates[key] = value

        if errors:
            return Response(errors, status=400)

        if not updates:
            return Response({"detail": "No valid settings provided."}, status=400)

        for key, value in updates.items():
            defn = SETTINGS_REGISTRY[key]
            try:
                old_row = Setting.objects.filter(setting_key=key).first()
                old_value = _resolve_current_value(key, old_row, defn)
            except Exception:
                old_value = defn.default
            log_setting_change(request.user, key, value, old_value)
            logger.info("Setting %s updated to %r by %s", key, value, request.user)

        # Recompute raw values (including the just-applied updates) to surface any
        # dependency warnings the caller should act on.
        db_settings = {s.setting_key: s for s in Setting.objects.all()}
        raw_values = {
            k: _resolve_current_value(k, db_settings.get(k), d) for k, d in SETTINGS_REGISTRY.items()
        }
        warnings = _collect_dependency_warnings(raw_values)

        response = self.get(request)
        if warnings:
            response.data["warnings"] = warnings
        return response
