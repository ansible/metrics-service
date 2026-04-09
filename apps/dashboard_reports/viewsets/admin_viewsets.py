from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor
from rest_framework.viewsets import GenericViewSet, ViewSet

"""
Base ViewSets for admin endpoints

Usage:
    class MyAdminViewSet(<optionalViewsetMixins>, BaseAdminViewSet):
        # Your viewset implementation here

    class MyGenericAdminViewSet(<optionalViewsetMixins>, GenericAdminViewSet):
        # Your viewset implementation here
"""


class BaseAdminViewSet(ViewSet):
    permission_classes = [IsSystemAdminOrAuditor]


class GenericAdminViewSet(GenericViewSet):
    permission_classes = [IsSystemAdminOrAuditor]
