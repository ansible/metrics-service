"""
Base views to reduce code duplication in API views.
"""

from ansible_base.lib.utils.views.django_app_api import AnsibleBaseDjangoAppApiView
from ansible_base.rbac.api.permissions import IsSystemAdminOrAuditor
from rest_framework import viewsets
from rest_framework.response import Response

from apps.tasks.utils import log_task_execution


class _TaskViewSetMixin:
    """Common permissions, ordering, and exception logging for task viewsets."""

    permission_classes = [IsSystemAdminOrAuditor]

    # Common ordering and filtering configurations
    ordering_fields = ["id", "created", "modified"]
    ordering = ["id"]

    # Keep the exception in task execution logs before DRF builds the response.
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


class BaseViewSet(_TaskViewSetMixin, AnsibleBaseDjangoAppApiView, viewsets.ModelViewSet):
    """Base viewset for task models with CRUD operations."""


class ReadOnlyBaseViewSet(_TaskViewSetMixin, AnsibleBaseDjangoAppApiView, viewsets.ReadOnlyModelViewSet):
    """Base viewset for task resources that only support list and retrieve."""
