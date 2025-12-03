"""
Custom permission classes for handling system auditor RBAC and developer mode.

This module provides Django REST Framework permission classes that integrate
system auditor functionality with Django Ansible Base (DAB) RBAC permission
system. The implementation ensures that system auditors receive appropriate
read-only access to all resources while maintaining full DAB RBAC functionality
for regular users.

Classes:
    SystemAuditorAwarePermissions: Hybrid permission class that maintains DAB RBAC
        for regular users while providing system auditors with read-only access
        to all resources.
    DeveloperModeRequired: Permission class that only allows access when
        DEVELOPER_MODE_ENABLED is True.

Permission Flow:
    1. Anonymous users: Denied access
    2. Superusers: Full access (admin privileges)
    3. System auditors: Read-only access to all resources
    4. Regular users: Standard DAB RBAC permission evaluation

Security Considerations:
    - System auditors can only perform safe HTTP methods (GET, HEAD, OPTIONS)
    - Write operations (POST, PUT, PATCH, DELETE) are explicitly denied for system auditors
    - All permission checks are performed at both view and object levels
    - Integrates seamlessly with existing DAB RBAC infrastructure
    - Developer mode endpoints are only accessible when DEVELOPER_MODE_ENABLED is True

Usage:
    Apply to ViewSets that need system auditor support:

    class MyViewSet(BaseViewSet):
        permission_classes = [SystemAuditorAwarePermissions]

    Apply to ViewSets that require developer mode:

    class TaskViewSet(BaseViewSet):
        permission_classes = [DeveloperModeRequired]
"""

from ansible_base.rbac.api.permissions import AnsibleBaseObjectPermissions
from rest_framework.permissions import SAFE_METHODS, BasePermission

from metrics_service.settings import DYNACONF


class SystemAuditorAwarePermissions(AnsibleBaseObjectPermissions):
    """
    Permission class that's aware of system auditors but delegates
    most logic to DAB RBAC for other users.

    Use this when you want to maintain full DAB RBAC for regular users
    but add system auditor support.

    Example behavior:

    System Auditor: GET /api/v1/organizations/ → 200 OK (read-only)
    System Auditor: POST /api/v1/organizations/ → 403 Forbidden
    Regular User: Full DAB RBAC logic applies
    """

    def has_permission(self, request, view):
        """Grant system auditors read-only access, use DAB RBAC for others."""
        user = request.user

        # Anonymous users
        if not user or not user.is_authenticated:
            return False

        # System administrators have full access via superuser check
        if user.is_superuser:
            return True

        # System auditors have read-only access
        if hasattr(user, "is_system_auditor") and getattr(user, "is_system_auditor", False):
            return request.method in SAFE_METHODS

        # For regular users, use DAB RBAC
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        """Grant system auditors read-only object access, use DAB RBAC for others."""
        user = request.user

        # System administrators have full access
        if user.is_superuser:
            return True

        # System auditors have read-only access to all objects
        if hasattr(user, "is_system_auditor_user") and user.is_system_auditor_user():
            return request.method in SAFE_METHODS

        # For regular users, use DAB RBAC
        return super().has_object_permission(request, view, obj)


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
        """Check if developer mode is enabled via DYNACONF."""
        developer_mode = DYNACONF.get("DEVELOPER_MODE_ENABLED", False)
        return bool(developer_mode)

    def has_object_permission(self, request, view, obj):
        """Object-level permission check delegates to view-level check."""
        return self.has_permission(request, view)
