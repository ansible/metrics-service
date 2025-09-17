"""
API v1 views for metrics_service following Ansible Automation Platform (AAP) standards.

This module provides REST API ViewSets that implement comprehensive CRUD operations
for core resources including Users, Organizations, and Teams. The implementation
follows AAP conventions and integrates with Django Ansible Base (DAB) for RBAC,
authentication, and resource management.

ViewSets:
    UserViewSet: Complete user management with profile operations
    OrganizationViewSet: Organization management with membership handling
    TeamViewSet: Team management with hierarchical organization support

Features:
    - RESTful API design with proper HTTP status codes
    - Comprehensive filtering, searching, and ordering capabilities
    - OpenAPI documentation with detailed schemas
    - System auditor read-only access integration
    - DAB RBAC permission enforcement
    - Proper error handling and validation
    - Pagination support for large datasets

Authentication:
    Supports multiple authentication methods:
    - Session authentication for web interface
    - OAuth2 tokens for third-party integrations
    - JWT tokens for service-to-service communication

Security:
    - RBAC-based access control via DAB
    - System auditor read-only enforcement
    - Input validation and sanitization
    - Rate limiting ready (configurable)
    - Audit logging for all operations
"""

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


class UserViewSet(BaseViewSet, UserManagementMixin):
    """
    ViewSet for User model following AAP patterns.

    This ViewSet provides comprehensive user management functionality
    including password setting and profile management.
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer
    search_fields = ["username", "first_name", "last_name", "email"]
    filterset_fields = {
        "username": ["exact", "icontains"],
        "email": ["exact", "icontains"],
        "is_active": ["exact"],
        "is_superuser": ["exact"],
        "is_system_auditor": ["exact"],
        "created": ["gte", "lte"],
    }
    ordering_fields = ["username", "email", "first_name", "last_name", "created"]
    ordering = ["username"]

    @extend_schema(
        operation_id="users_me_retrieve",
        description="Get current user information",
        responses={200: UserSerializer},
    )
    @action(detail=False, methods=["get"])
    def me(self, request):
        """Return current user information."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @extend_schema(
        operation_id="users_set_password",
        description="Set user password",
        request={"password": "string"},
        responses={204: None},
    )
    @action(detail=True, methods=["post"])
    def set_password(self, request, pk=None):
        """Set password for a user."""
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
    including user and admin management.
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
