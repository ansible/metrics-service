"""
Custom permission classes for developer mode.

This module provides Django REST Framework permission classes that integrate
with Django Ansible Base (DAB) RBAC permission system.

Classes:
    DeveloperModeRequired: Permission class that only allows access when
        DEVELOPER_MODE_ENABLED is True.

Security Considerations:
    - Developer mode endpoints are only accessible when DEVELOPER_MODE_ENABLED is True

Usage:
    Apply to ViewSets that require developer mode:

    class TaskViewSet(BaseViewSet):
        permission_classes = [DeveloperModeRequired]
"""

from django.conf import settings
from rest_framework.permissions import BasePermission


class DeveloperModeRequired(BasePermission):
    """
    Permission class that only allows access when DEVELOPER_MODE_ENABLED is True.

    Use this for development/debugging endpoints that should not be accessible
    in production environments, such as the Tasks API and Dashboard.

    The setting can be controlled via:
    - Environment variable: METRICS_SERVICE_DEVELOPER_MODE_ENABLED=true
    - config/settings.yaml: DEVELOPER_MODE_ENABLED: true

    Example behavior:
        Developer Mode ON:  GET /api/v1/tasks/ → 200 OK
        Developer Mode OFF: GET /api/v1/tasks/ → 403 Forbidden

    Usage:
        class TaskViewSet(BaseViewSet):
            permission_classes = [DeveloperModeRequired]
    """

    message = "This endpoint is only available when developer mode is enabled."

    def has_permission(self, request, view):
        """Check if developer mode is enabled via Django settings."""
        developer_mode = getattr(settings, "DEVELOPER_MODE_ENABLED", False)
        return bool(developer_mode)

    def has_object_permission(self, request, view, obj):
        """Object-level permission check delegates to view-level check."""
        return self.has_permission(request, view)
