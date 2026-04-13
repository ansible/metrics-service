"""ViewSet for retrieving and updating AWX job template metadata (time estimates)."""

from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor
from django.db.models import QuerySet
from rest_framework.mixins import RetrieveModelMixin, UpdateModelMixin
from rest_framework.viewsets import GenericViewSet

from apps.dashboard_reports.models import TemplateMetadata
from apps.dashboard_reports.serializers import TemplateMetadataSerializer


class TemplateMetadataViewSet(RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    """
    ViewSet for retrieving template metadata from metrics service database.

    Endpoints:
        GET    api/v1/dashboard_reports/template_metadata/{id}/ - Get template metadata
        PUT    api/v1/dashboard_reports/template_metadata/{id}/ - Update template metadata
        PATCH  api/v1/dashboard_reports/template_metadata/{id}/ - Partially update template metadata
    """

    permission_classes = [IsSystemAdminOrAuditor]
    versioning_class = None
    pagination_class = None
    serializer_class = TemplateMetadataSerializer

    def get_queryset(self) -> QuerySet[TemplateMetadata]:
        """Return all TemplateMetadata records."""
        return TemplateMetadata.objects.all()
