"""ViewSet for viewing and updating the AAP subscription cost configuration."""

from typing import Any

from django.db.models import QuerySet
from rest_framework import status
from rest_framework.mixins import ListModelMixin, UpdateModelMixin
from rest_framework.request import Request
from rest_framework.response import Response

from apps.dashboard_reports.models import SubscriptionCost
from apps.dashboard_reports.serializers import SubscriptionCostSerializer
from apps.dashboard_reports.viewsets.admin_viewsets import GenericAdminViewSet


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

    def get_queryset(self) -> QuerySet[SubscriptionCost]:
        """Return all SubscriptionCost records, ensuring the singleton exists."""
        # TODO (Tech Preview): Creating the singleton here is a hidden write side-effect
        # on a read path — it fires on every GET, schema generation, and permission check.
        # At GA, guarantee the singleton via a management command or data migration instead.
        SubscriptionCost.get()
        return SubscriptionCost.objects.all()

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """
        Updates the cost of a subscription.
        """
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)
