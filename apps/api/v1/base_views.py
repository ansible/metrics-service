"""
Base views to reduce code duplication in API views.
"""

from typing import Any

from ansible_base.lib.utils.views.django_app_api import AnsibleBaseDjangoAppApiView
from ansible_base.rbac.api.permissions import AnsibleBaseObjectPermissions
from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.response import Response

from apps.tasks.utils import log_task_execution


class BaseViewSet(AnsibleBaseDjangoAppApiView, viewsets.ModelViewSet):
    """
    Base ViewSet class with common functionality.

    This base class provides common ViewSet functionality that can be
    inherited by all model ViewSets to reduce code duplication.
    """

    permission_classes = [AnsibleBaseObjectPermissions]

    # Common ordering and filtering configurations
    ordering_fields = ["id", "created", "modified"]
    ordering = ["id"]

    def get_queryset(self) -> QuerySet:
        """
        Filter queryset based on user permissions.

        This method provides a standardized way to filter querysets based on
        user permissions, reducing duplication across all ViewSets.

        Returns:
            QuerySet: Filtered queryset based on user permissions
        """
        if hasattr(self.queryset.model, "access_qs"):
            return self.queryset.model.access_qs(self.request.user, queryset=self.queryset)
        return self.queryset

    def handle_exception(self, exc: Exception) -> Response:
        """
        Handle exceptions in a standardized way.

        This method provides consistent error handling across all ViewSets,
        reducing duplication of exception handling logic.

        Args:
            exc (Exception): The exception that occurred

        Returns:
            Response: Standardized error response
        """
        # Log the exception for debugging
        log_task_execution(task_name=self.__class__.__name__, operation="exception", details=str(exc), level="error")

        return super().handle_exception(exc)

    def perform_create(self, serializer: Any) -> None:
        """
        Perform object creation with common logic.

        This method provides a place to add common creation logic that should
        apply to all ViewSets, such as setting the creator.

        Args:
            serializer: The serializer instance

        Returns:
            None
        """
        # Set created_by field if it exists and user is authenticated
        if hasattr(serializer.Meta.model, "created_by") and self.request.user and self.request.user.is_authenticated:
            serializer.save(created_by=self.request.user)
        else:
            serializer.save()

    def perform_update(self, serializer: Any) -> None:
        """
        Perform object update with common logic.

        This method provides a place to add common update logic that should
        apply to all ViewSets, such as tracking modifications.

        Args:
            serializer: The serializer instance

        Returns:
            None
        """
        serializer.save()
