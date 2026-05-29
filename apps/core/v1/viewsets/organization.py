from drf_spectacular.utils import extend_schema, extend_schema_view

from apps.core.models import Organization
from apps.core.v1.serializers import OrganizationSerializer

from .base import BaseViewSet


@extend_schema_view(
    list=extend_schema(
        summary="List organizations.",
        description="Returns a list of organizations.",
    ),
)
class OrganizationViewSet(BaseViewSet):
    """CRUD viewset for Organization resources with RBAC filtering."""

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
