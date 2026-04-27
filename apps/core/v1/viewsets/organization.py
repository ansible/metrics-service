from apps.core.models import Organization
from apps.core.v1.serializers import OrganizationSerializer

from .base import BaseViewSet


class OrganizationViewSet(BaseViewSet):
    """CRUD viewset for Organization resources with RBAC filtering."""

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
