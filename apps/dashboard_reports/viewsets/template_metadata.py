from django.db.models import QuerySet
from rest_framework.mixins import DestroyModelMixin, RetrieveModelMixin, UpdateModelMixin

from apps.dashboard_reports.models import TemplateMetadata
from apps.dashboard_reports.serializers import TemplateMetadataSerializer
from apps.dashboard_reports.viewsets.admin_viewsets import GenericAdminViewSet


class TemplateMetadataViewSet(RetrieveModelMixin, UpdateModelMixin, DestroyModelMixin, GenericAdminViewSet):
    """
    ViewSet for retrieving template metadata from metrics service database.

    Endpoints:
        GET    api/v1/dashboard_reports/templates/{id}/metadata/ - Get template metadata
        PUT    api/v1/dashboard_reports/templates/{id}/metadata/ - Update template metadata
        PATCH  api/v1/dashboard_reports/templates/{id}/metadata/ - Partially update template metadata
        DELETE api/v1/dashboard_reports/templates/{id}/metadata/ - Template reverts to system defaults
    """

    versioning_class = None
    pagination_class = None
    serializer_class = TemplateMetadataSerializer
    lookup_field = "template_id"
    lookup_url_kwarg = "pk"

    def get_queryset(self) -> QuerySet[TemplateMetadata]:
        return TemplateMetadata.objects.all()

    def perform_destroy(self, instance: TemplateMetadata) -> None:
        """Clear user overrides, reverting the template to system defaults."""

        instance.time_taken_manually_execute_minutes = None
        instance.time_taken_create_automation_minutes = None
        instance.save(
            update_fields=[
                "time_taken_manually_execute_minutes",
                "time_taken_create_automation_minutes",
            ]
        )
