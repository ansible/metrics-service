"""
Base ViewSets for admin-only dashboard report endpoints.

Usage:
    class MyAdminViewSet(<optionalViewsetMixins>, BaseAdminViewSet):
        # Your viewset implementation here

    class MyGenericAdminViewSet(<optionalViewsetMixins>, GenericAdminViewSet):
        # Your viewset implementation here
"""

from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor
from rest_framework.viewsets import GenericViewSet, ViewSet


class BaseAdminViewSet(ViewSet):
    """Base ViewSet restricted to system admin or auditor users (non-generic, no queryset)."""

    permission_classes = [IsSystemAdminOrAuditor]


class GenericAdminViewSet(GenericViewSet):
    """Generic ViewSet restricted to system admin or auditor users (supports queryset and serializer)."""

    permission_classes = [IsSystemAdminOrAuditor]
