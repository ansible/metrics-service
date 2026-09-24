"""ViewSet for retrieving and updating AWX job template metadata (time estimates)."""

import copy

from django.db.models import QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.mixins import RetrieveModelMixin, UpdateModelMixin
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.dashboard_reports.models import JobData, OrganizationTemplateMetadataOverride, TemplateMetadata
from apps.dashboard_reports.permissions import (
    DashboardReadPermission,
    get_dashboard_scope,
    is_dashboard_admin,
    resolve_selected_organization,
)
from apps.dashboard_reports.serializers import TemplateMetadataSerializer

ORGANIZATION_PARAMETER = OpenApiParameter(
    name="organization",
    type=OpenApiTypes.INT,
    location=OpenApiParameter.QUERY,
    required=False,
    description=(
        "AWX organization ID. Organization-scoped users must provide this; reads resolve their personal "
        "template estimate with the global estimate as fallback, and writes require the Organization Admin role."
    ),
)


@extend_schema_view(
    retrieve=extend_schema(
        summary="Get specific template metadata ID.",
        description="Returns a specific template metadata by ID.",
        parameters=[ORGANIZATION_PARAMETER],
    ),
    update=extend_schema(
        summary="Update a specific template metadata by ID.",
        description="Update a specific template metadata by ID.",
        parameters=[ORGANIZATION_PARAMETER],
    ),
    partial_update=extend_schema(
        summary="Partially update a specific template metadata by ID.",
        description="Partially update a specific template metadata by ID.",
        parameters=[ORGANIZATION_PARAMETER],
    ),
)
class TemplateMetadataViewSet(RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    """
    ViewSet for retrieving template metadata from metrics service database.

    Endpoints:
        GET    api/v1/dashboard_reports/template_metadata/{id}/ - Get template metadata
        PUT    api/v1/dashboard_reports/template_metadata/{id}/ - Update template metadata
        PATCH  api/v1/dashboard_reports/template_metadata/{id}/ - Partially update template metadata
    """

    permission_classes = [DashboardReadPermission]
    versioning_class = None
    pagination_class = None
    # `organization` is an access-scope parameter, not a TemplateMetadata model field.
    filter_backends = []
    serializer_class = TemplateMetadataSerializer

    def get_queryset(self) -> QuerySet[TemplateMetadata]:
        """Return templates represented by jobs in the selected accessible organization."""
        scope = get_dashboard_scope(self.request.user)
        if scope.global_access:
            return TemplateMetadata.objects.all()
        if not self.request.query_params.get("organization"):
            raise serializers.ValidationError({"organization": "This endpoint requires an organization context."})
        organization = resolve_selected_organization(self.request, scope)
        template_ids = JobData.objects.filter(
            organization_ansible_id=organization.ansible_id, template_metadata_id__isnull=False
        ).values_list("template_metadata_id", flat=True)
        return TemplateMetadata.objects.filter(pk__in=template_ids)

    def _selected_organization(self, *, require_edit=False):
        scope = get_dashboard_scope(self.request.user)
        if scope.global_access:
            return None
        if self.request.query_params.get("organization"):
            return resolve_selected_organization(self.request, scope, require_edit=require_edit)
        raise serializers.ValidationError({"organization": "This endpoint requires an organization context."})

    def _serialize_resolved(self, instance, organization):
        """Apply private organization estimates over the shared fallback values for this response."""
        if organization is not None:
            override = OrganizationTemplateMetadataOverride.objects.filter(
                user=self.request.user, organization_id=organization.id, template_id=instance.template_id
            ).first()
            if override:
                instance = copy.copy(instance)
                for field in (
                    "time_taken_manually_execute_minutes",
                    "time_taken_create_automation_minutes",
                ):
                    value = getattr(override, field)
                    if value is not None:
                        setattr(instance, field, value)
        return self.get_serializer(instance).data

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        organization = self._selected_organization()
        instance = self.get_object()
        return Response(self._serialize_resolved(instance, organization))

    def update(self, request: Request, *args, **kwargs) -> Response:
        organization = self._selected_organization(require_edit=bool(request.query_params.get("organization")))
        if organization is None and not is_dashboard_admin(request.user):
            raise PermissionDenied("Only system administrators may update global template estimates.")
        instance = self.get_object()
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        if organization is None:
            self.perform_update(serializer)
            return Response(serializer.data, status=status.HTTP_200_OK)

        override, _ = OrganizationTemplateMetadataOverride.objects.get_or_create(
            user=request.user, organization_id=organization.id, template_id=instance.template_id
        )
        for field, value in serializer.validated_data.items():
            setattr(override, field, value)
        override.save()
        return Response(self._serialize_resolved(instance, organization), status=status.HTTP_200_OK)
