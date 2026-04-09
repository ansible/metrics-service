import logging
from typing import Any

from ansible_base.rest_pagination import DefaultPaginator
from django.db import transaction
from django.db.models import QuerySet
from rest_framework import status
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, ListModelMixin, UpdateModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.dashboard_reports.models import FilterSet
from apps.dashboard_reports.serializers import FilterSetSerializer

logger = logging.getLogger(__name__)


class FilterSetsViewSet(ListModelMixin, CreateModelMixin, UpdateModelMixin, DestroyModelMixin, GenericViewSet):
    """
    ViewSet for retrieving and modifying filter sets from metrics service database.

    Provides listing and updating filter sets' entries. This allows users
    (with correct permissions) to view and modify the filter sets as needed.

    Each user can only see and modify their own filter sets.
    Only one filter set per user can be marked as default.

    Endpoints:
        GET    api/v1/dashboard_reports/filter_sets - list all filter sets (with pagination)
        POST   api/v1/dashboard_reports/filter_sets - create a new filter set entry
        PUT    api/v1/dashboard_reports/filter_sets/{id} - update a filter set entry
        PATCH  api/v1/dashboard_reports/filter_sets/{id} - partially update a filter set entry
        DELETE api/v1/dashboard_reports/filter_sets/{id} - delete a filter set entry

    Query Parameters:
        id (int): ID of the filter set entry to edit
        page (int): Page number for pagination
        page_size (int): Number of items per page for pagination
    """

    versioning_class = None  # Disable versioning for this viewset
    permission_classes = [IsAuthenticated]
    serializer_class = FilterSetSerializer
    pagination_class = DefaultPaginator

    def get_queryset(self) -> QuerySet[FilterSet]:
        return FilterSet.objects.filter(user=self.request.user)

    def perform_create(self, serializer: FilterSetSerializer) -> None:
        with transaction.atomic():
            if serializer.validated_data.get("is_default", False):
                FilterSet.objects.filter(user=self.request.user, is_default=True).update(is_default=False)
            serializer.save(user=self.request.user)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """
        Updates the filter set. (PUT method)
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            validated = serializer.validated_data
            if validated.get("is_default", False):
                FilterSet.objects.filter(user=self.request.user, is_default=True).exclude(pk=instance.pk).update(
                    is_default=False
                )
            serializer.save(user=self.request.user)

        return Response(serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """
        Partially updates the filter set. (PATCH method)
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            validated = serializer.validated_data
            if validated.get("is_default", False):
                FilterSet.objects.filter(user=self.request.user, is_default=True).exclude(pk=instance.pk).update(
                    is_default=False
                )
            serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """
        Deletes the filter set. (DELETE method)
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance: FilterSet) -> None:
        logger.info(f"Deleting filter set with id {instance.id} and name {instance.name}")
        instance.delete()
