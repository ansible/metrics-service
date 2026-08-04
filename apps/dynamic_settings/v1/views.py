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


def _resolve_current_value(key: str, row: Setting | None, defn) -> bool | int | str | None:
    """Return the effective value: DB row > FEATURE dict > registry default."""
    if row and row.current_value:
        try:
            return json.loads(row.current_value)
        except (json.JSONDecodeError, ValueError):
            return row.current_value.lower() in ("true", "1", "yes", "on")

    from django.conf import settings as django_settings

    feature_dict = getattr(django_settings, "FEATURE", {})
    if key in feature_dict:
        return feature_dict[key]

    return defn.default


class SettingsView(APIView):
    """
    GET  /api/v1/settings/  — list all settings grouped by category with metadata.
    PATCH /api/v1/settings/ — update one or more settings by key.

    Only known keys from SETTINGS_REGISTRY are accepted. Changes take effect on the
    next scheduler tick (<=30s) without a restart.
    """

    permission_classes = [IsSystemAdminOrAuditor]

    def get(self, request: Request) -> Response:
        db_settings = {s.setting_key: s for s in Setting.objects.all()}
        result: dict = {}

        for key, defn in SETTINGS_REGISTRY.items():
            row = db_settings.get(key)
            current = _resolve_current_value(key, row, defn)
            category = result.setdefault(defn.category, {})
            category[key] = {
                "value": current,
                "default": defn.default,
                "type": defn.type,
                "label": defn.label,
                "description": defn.description,
                "parent_flag": defn.parent_flag,
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

        return self.get(request)
