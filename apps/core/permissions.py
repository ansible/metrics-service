"""
Custom permission classes for develpment mode

Usage:
    Apply to ViewSets that require development mode:

    class TaskViewSet(BaseViewSet):
        permission_classes = [DeveloperModeRequired]
"""

from django.conf import settings
from rest_framework.permissions import BasePermission


class DeveloperModeRequired(BasePermission):
    """
    Permission class that only allows access when METRICS_SERVICE_MODE=development

    Used for endpoints that shouldn't be accessible in production, such as the Tasks API & Dashboard

    Example behavior:
        Developer Mode ON:  GET /api/v1/tasks/ → 200 OK
        Developer Mode OFF: GET /api/v1/tasks/ → 403 Forbidden

    Usage:
        class TaskViewSet(BaseViewSet):
            permission_classes = [DeveloperModeRequired]
    """

    message = "This endpoint is only available when development mode is enabled."

    def has_permission(self, request, view):
        """Check if development mode is enabled via Django settings."""
        return settings.MODE == "development"

    def has_object_permission(self, request, view, obj):
        """Object-level permission check delegates to view-level check."""
        return self.has_permission(request, view)
