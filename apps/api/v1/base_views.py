"""
Base views to reduce code duplication in API views.
"""

from typing import Any

from ansible_base.lib.utils.views.django_app_api import AnsibleBaseDjangoAppApiView
from ansible_base.rbac.api.permissions import AnsibleBaseObjectPermissions

from apps.core.permissions import SystemAuditorAwarePermissions
from django.db.models import QuerySet
from django.http import HttpRequest
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.utils import build_error_response
from apps.tasks.utils import log_task_execution


class BaseViewSet(AnsibleBaseDjangoAppApiView, viewsets.ModelViewSet):
    """
    Base ViewSet class with common functionality.

    This base class provides common ViewSet functionality that can be
    inherited by all model ViewSets to reduce code duplication.
    """

    permission_classes = [SystemAuditorAwarePermissions]

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


class UserManagementMixin:
    """
    Mixin to provide common user management actions.

    This mixin reduces duplication of user management functionality across
    ViewSets that need to manage user relationships (Organization, Team, etc.).
    """

    def _add_user_to_field(
        self, request: HttpRequest, field_name: str, success_message: str = "User added successfully"
    ) -> Response:
        """
        Generic method to add a user to a specific field.

        Args:
            request: The HTTP request
            field_name (str): Name of the field to add user to (e.g., 'users', 'admins')
            success_message (str): Success message to return

        Returns:
            Response: HTTP response
        """
        obj = self.get_object()
        user_id = request.data.get("user_id")

        if not user_id:
            error_response = build_error_response("user_id is required")
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.core.models import User

            user = User.objects.get(id=user_id)
            field = getattr(obj, field_name)
            field.add(user)

            return Response({"message": success_message, "user_id": user_id}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            error_response = build_error_response("User not found", status_code=404)
            return Response(error_response, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            error_response = build_error_response(f"Failed to add user: {str(e)}")
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

    def _remove_user_from_field(
        self, request: HttpRequest, field_name: str, success_message: str = "User removed successfully"
    ) -> Response:
        """
        Generic method to remove a user from a specific field.

        Args:
            request: The HTTP request
            field_name (str): Name of the field to remove user from (e.g., 'users', 'admins')
            success_message (str): Success message to return

        Returns:
            Response: HTTP response
        """
        obj = self.get_object()
        user_id = request.data.get("user_id")

        if not user_id:
            error_response = build_error_response("user_id is required")
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.core.models import User

            user = User.objects.get(id=user_id)
            field = getattr(obj, field_name)
            field.remove(user)

            return Response({"message": success_message, "user_id": user_id}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            error_response = build_error_response("User not found", status_code=404)
            return Response(error_response, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            error_response = build_error_response(f"Failed to remove user: {str(e)}")
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        operation_id="add_user",
        description="Add user to this object",
        request={"user_id": "integer"},
        responses={200: {"message": "string", "user_id": "integer"}},
    )
    @action(detail=True, methods=["post"])
    def add_user(self, request: HttpRequest, pk: Any = None) -> Response:
        """
        Add user to this object.

        Args:
            request: HTTP request containing user_id
            pk: Primary key of the object

        Returns:
            Response: Success or error response
        """
        return self._add_user_to_field(request, "users", "User added successfully")

    @extend_schema(
        operation_id="remove_user",
        description="Remove user from this object",
        request={"user_id": "integer"},
        responses={200: {"message": "string", "user_id": "integer"}},
    )
    @action(detail=True, methods=["post"])
    def remove_user(self, request: HttpRequest, pk: Any = None) -> Response:
        """
        Remove user from this object.

        Args:
            request: HTTP request containing user_id
            pk: Primary key of the object

        Returns:
            Response: Success or error response
        """
        return self._remove_user_from_field(request, "users", "User removed successfully")

    @extend_schema(
        operation_id="add_admin",
        description="Add admin to this object",
        request={"user_id": "integer"},
        responses={200: {"message": "string", "user_id": "integer"}},
    )
    @action(detail=True, methods=["post"])
    def add_admin(self, request: HttpRequest, pk: Any = None) -> Response:
        """
        Add admin to this object.

        Args:
            request: HTTP request containing user_id
            pk: Primary key of the object

        Returns:
            Response: Success or error response
        """
        return self._add_user_to_field(request, "admins", "Admin added successfully")

    @extend_schema(
        operation_id="remove_admin",
        description="Remove admin from this object",
        request={"user_id": "integer"},
        responses={200: {"message": "string", "user_id": "integer"}},
    )
    @action(detail=True, methods=["post"])
    def remove_admin(self, request: HttpRequest, pk: Any = None) -> Response:
        """
        Remove admin from this object.

        Args:
            request: HTTP request containing user_id
            pk: Primary key of the object

        Returns:
            Response: Success or error response
        """
        return self._remove_user_from_field(request, "admins", "Admin removed successfully")


class SearchFilterMixin:
    """
    Mixin to provide common search and filter configurations.

    This mixin reduces duplication of search and filter setup across
    ViewSets that need similar search/filter capabilities.
    """

    def get_search_fields(self) -> list[str]:
        """
        Get search fields based on model fields.

        This method automatically determines appropriate search fields
        based on the model, reducing configuration duplication.

        Returns:
            list: List of search field names
        """
        model = self.queryset.model
        search_fields = []

        # Add common text fields for searching
        for field in model._meta.fields:
            if field.name in ["name", "username", "email", "first_name", "last_name", "description"]:
                search_fields.append(field.name)

        # Add related field searches
        if hasattr(model, "owner"):
            search_fields.append("owner__username")
        if hasattr(model, "organization"):
            search_fields.append("organization__name")

        return search_fields

    def get_filterset_fields(self) -> dict[str, list[str]]:
        """
        Get filterset fields based on model fields.

        This method automatically determines appropriate filter fields
        based on the model, reducing configuration duplication.

        Returns:
            dict: Dictionary of filter field configurations
        """
        model = self.queryset.model
        filterset_fields = {}

        # Add common filter configurations
        for field in model._meta.fields:
            if field.name in ["name", "username", "email", "description"]:
                filterset_fields[field.name] = ["exact", "icontains"]
            elif field.name in ["is_active", "is_staff", "is_superuser"]:
                filterset_fields[field.name] = ["exact"]
            elif field.name in ["created", "modified", "date_joined"]:
                filterset_fields[field.name] = ["gte", "lte"]

        return filterset_fields
