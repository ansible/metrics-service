"""
Custom permission classes for handling system auditor RBAC.

This module provides Django REST Framework permission classes that integrate
system auditor functionality with Django Ansible Base (DAB) RBAC permission
system.
"""

from ansible_base.rbac.api.permissions import AnsibleBaseObjectPermissions
from rest_framework.permissions import SAFE_METHODS


class SystemAuditorAwarePermissions(AnsibleBaseObjectPermissions):
    """
    Permission class that's aware of system auditors but delegates
    most logic to DAB RBAC for other users.

    Use this when you want to maintain full DAB RBAC for regular users
    but add system auditor support.
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
