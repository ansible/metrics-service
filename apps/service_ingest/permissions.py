"""Feature flag permission for the service ingest endpoint."""

from rest_framework.permissions import BasePermission


class IsServiceIngestEnabled(BasePermission):
    """Returns 403 when the SERVICE_INGEST feature flag is disabled."""

    message = "Service ingest is not enabled. Set FEATURE[SERVICE_INGEST] = True."

    def has_permission(self, request, view):
        from apps.tasks.task_groups import get_feature_enabled_from_db

        return get_feature_enabled_from_db("SERVICE_INGEST")
