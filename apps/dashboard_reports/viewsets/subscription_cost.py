"""ViewSet for viewing and updating the AAP subscription cost configuration."""

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.mixins import ListModelMixin, UpdateModelMixin
from rest_framework.request import Request
from rest_framework.response import Response

from apps.dashboard_reports.models import OrganizationDashboardSettings, SubscriptionCost
from apps.dashboard_reports.permissions import (
    DashboardReadPermission,
    get_dashboard_scope,
    is_dashboard_admin,
    resolve_selected_organization,
)
from apps.dashboard_reports.serializers import OrganizationDashboardSettingsSerializer, SubscriptionCostSerializer
from apps.dashboard_reports.viewsets.admin_viewsets import GenericAdminViewSet

ORGANIZATION_PARAMETER = OpenApiParameter(
    name="organization",
    type=OpenApiTypes.INT,
    location=OpenApiParameter.QUERY,
    required=False,
    description=(
        "AWX organization ID. Organization-scoped users must provide this; reads resolve their personal "
        "override with global values as fallback, and writes require the Organization Admin role."
    ),
)


@extend_schema_view(
    list=extend_schema(
        summary="Get a list of subscription costs.",
        description="Returns a list of subscription costs.",
        parameters=[ORGANIZATION_PARAMETER],
    ),
    update=extend_schema(
        summary="Update a specific subscription cost by ID.",
        description="Update a specific subscription cost by ID.",
        parameters=[ORGANIZATION_PARAMETER],
    ),
    partial_update=extend_schema(
        summary="Partially update a specific subscription cost by ID.",
        description="Partially update a specific subscription cost by ID.",
        parameters=[ORGANIZATION_PARAMETER],
    ),
)
class SubscriptionCostViewSet(ListModelMixin, UpdateModelMixin, GenericAdminViewSet):
    """
    ViewSet for retrieving subscription cost from metrics service database.

    Provides listing and updating subscription cost entries. This allows users (with correct permissions) to view and modify the cost of subscriptions as needed.

    Endpoints:
        GET /api/v1/dashboard_reports/subscription_costs/ - List subscription cost entries (without pagination)
        PUT /api/v1/dashboard_reports/subscription_costs/{id}/ - Update an existing subscription cost entry by ID

    Query Parameters:
        id (int): ID of the subscription cost entry to edit
    """

    versioning_class = None  # Disable versioning for this viewset
    serializer_class = SubscriptionCostSerializer
    pagination_class = None  # Disable pagination for this viewset
    permission_classes = [DashboardReadPermission]

    def get_queryset(self) -> QuerySet[SubscriptionCost]:
        """Return all SubscriptionCost records, ensuring the singleton exists."""
        SubscriptionCost.get()
        return SubscriptionCost.objects.all()

    def _selected_organization(self, *, require_edit: bool = False):
        scope = get_dashboard_scope(self.request.user)
        if scope.global_access:
            return None
        if self.request.query_params.get("organization"):
            return resolve_selected_organization(self.request, scope, require_edit=require_edit)
        raise serializers.ValidationError({"organization": "This endpoint requires an organization context."})

    @staticmethod
    def _resolved_values(global_cost, override, *, pk=1):
        return {
            "id": pk,
            "monthly_subscription_cost": (
                override.monthly_subscription_cost
                if override and override.monthly_subscription_cost is not None
                else global_cost.monthly_subscription_cost
            ),
            "engineer_avg_hourly_rate": (
                override.engineer_avg_hourly_rate
                if override and override.engineer_avg_hourly_rate is not None
                else global_cost.engineer_avg_hourly_rate
            ),
            "include_template_creation_time_in_costs": (
                override.include_template_creation_time_in_costs
                if override and override.include_template_creation_time_in_costs is not None
                else global_cost.include_template_creation_time_in_costs
            ),
        }

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return global settings or this user's resolved settings for one organization."""
        organization = self._selected_organization()
        global_cost = SubscriptionCost.get()
        if organization is None:
            return Response(self.get_serializer([global_cost], many=True).data)
        override = OrganizationDashboardSettings.objects.filter(
            user=request.user, organization_id=organization.id
        ).first()
        return Response([self._resolved_values(global_cost, override)])

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """
        Updates the cost of a subscription.
        """
        organization = self._selected_organization(require_edit=bool(request.query_params.get("organization")))
        if organization is not None:
            override, _ = OrganizationDashboardSettings.objects.get_or_create(
                user=request.user, organization_id=organization.id
            )
            serializer = OrganizationDashboardSettingsSerializer(override, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            for field, value in serializer.validated_data.items():
                setattr(override, field, value)
            override.save()
            resolved = self._resolved_values(SubscriptionCost.get(), override)
            return Response(resolved, status=status.HTTP_200_OK)

        if not is_dashboard_admin(request.user):
            raise PermissionDenied("Only system administrators may update global subscription settings.")
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
