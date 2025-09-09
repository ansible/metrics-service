"""
API v1 views for metrics_service following AAP standards.

This module provides ViewSets for the API v1 endpoints with reduced
code duplication through the use of base ViewSet classes and mixins.
"""

from typing import Any

from django.http import HttpRequest
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.models import Organization, Team, User

from .base_views import BaseViewSet, UserManagementMixin
from .serializers import (
    OrganizationSerializer,
    TeamSerializer,
    UserSerializer,
)


class UserViewSet(BaseViewSet):
    """
    ViewSet for User model following AAP patterns.

    This ViewSet provides comprehensive user management functionality
    including current user information and password management.
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer
    search_fields = ["username", "first_name", "last_name", "email"]
    filterset_fields = {
        "username": ["exact", "icontains"],
        "email": ["exact", "icontains"],
        "is_active": ["exact"],
        "is_staff": ["exact"],
        "is_superuser": ["exact"],
        "date_joined": ["gte", "lte"],
    }
    ordering_fields = ["username", "email", "first_name", "last_name", "date_joined"]
    ordering = ["username"]

    @extend_schema(
        operation_id="users_me_retrieve",
        description="Get current user information",
        responses={200: UserSerializer},
    )
    @action(detail=False, methods=["get"])
    def me(self, request: HttpRequest) -> Response:
        """
        Return current user information.

        Returns:
            Response: Serialized current user data
        """
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @extend_schema(
        operation_id="users_set_password",
        description="Set user password",
        request={"password": "string"},
        responses={204: None},
    )
    @action(detail=True, methods=["post"])
    def set_password(self, request: HttpRequest, pk: Any = None) -> Response:
        """
        Set password for a user.

        Args:
            request: HTTP request containing password data
            pk: Primary key of the user

        Returns:
            Response: Success or error response
        """
        user = self.get_object()
        password = request.data.get("password")

        if not password:
            return Response({"error": "Password is required"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrganizationViewSet(BaseViewSet, UserManagementMixin):
    """
    ViewSet for Organization model following AAP patterns.

    This ViewSet provides comprehensive organization management functionality
    including user and admin management through the UserManagementMixin.
    """

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    search_fields = ["name", "description"]
    filterset_fields = {
        "name": ["exact", "icontains"],
        "description": ["icontains"],
        "extra_field": ["exact", "icontains", "isnull"],
        "created": ["gte", "lte"],
        "modified": ["gte", "lte"],
    }
    ordering_fields = ["name", "created", "modified"]
    ordering = ["name"]


class TeamViewSet(BaseViewSet, UserManagementMixin):
    """
    ViewSet for Team model following AAP patterns.

    This ViewSet provides comprehensive team management functionality
    including hierarchical support and user/admin management.
    """

    queryset = Team.objects.select_related("organization").all()
    serializer_class = TeamSerializer
    search_fields = ["name", "description", "organization__name"]
    filterset_fields = {
        "name": ["exact", "icontains"],
        "description": ["icontains"],
        "organization": ["exact"],
        "organization__name": ["exact", "icontains"],
        "created": ["gte", "lte"],
        "modified": ["gte", "lte"],
    }
    ordering_fields = ["name", "organization__name", "created", "modified"]
    ordering = ["organization__name", "name"]
