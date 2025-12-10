"""
API v1 viewsets for metrics_service following AAP standards.
"""

from ansible_base.lib.utils.views.django_app_api import AnsibleBaseDjangoAppApiView
from ansible_base.rbac.api.permissions import AnsibleBaseObjectPermissions
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.core.models import Organization, Team, User
from apps.core.permissions import SystemAuditorAwarePermissions
from apps.core.utils import log_setting_change
from metrics_service.settings import DYNACONF

from .serializers import OrganizationSerializer, TeamSerializer, UserSerializer


class UserViewSet(AnsibleBaseDjangoAppApiView, viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for User model following AAP patterns.

    This is a read-only viewset - users cannot be created/modified via API.
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [SystemAuditorAwarePermissions]
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

    def get_queryset(self):
        """Filter queryset based on user permissions using DAB patterns."""
        return User.access_qs(self.request.user, queryset=self.queryset)

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


class OrganizationViewSet(AnsibleBaseDjangoAppApiView, viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Organization model following AAP patterns.

    This is a read-only viewset - organizations cannot be created/modified via API.
    """

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [SystemAuditorAwarePermissions]
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

    def get_queryset(self):
        """Filter queryset based on user permissions using DAB patterns."""
        user = self.request.user
        return Organization.access_qs(user, queryset=self.queryset)

    @extend_schema(
        operation_id="organizations_users",
        description="Get users in organization",
        responses={200: UserSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def users(self, request, pk=None):
        """Get users in organization."""
        organization = self.get_object()
        users = organization.users.all()
        serializer = UserSerializer(users, many=True, context={"request": request})
        return Response(serializer.data)


class TeamViewSet(AnsibleBaseDjangoAppApiView, viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Team model following AAP patterns.

    This is a read-only viewset - teams cannot be created/modified via API.
    """

    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [SystemAuditorAwarePermissions]
    search_fields = ["name", "description"]
    filterset_fields = {
        "name": ["exact", "icontains"],
        "description": ["icontains"],
        "organization": ["exact"],
        "created": ["gte", "lte"],
        "modified": ["gte", "lte"],
    }
    ordering_fields = ["name", "created", "modified"]
    ordering = ["name"]

    def get_queryset(self):
        """Filter queryset based on user permissions using DAB patterns."""
        user = self.request.user
        return Team.access_qs(user, queryset=self.queryset)

    @extend_schema(
        operation_id="teams_users",
        description="Get users in team",
        responses={200: UserSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def users(self, request, pk=None):
        """Get users in team."""
        team = self.get_object()
        users = team.users.all()
        serializer = UserSerializer(users, many=True, context={"request": request})
        return Response(serializer.data)


class SettingView(AnsibleBaseDjangoAppApiView, viewsets.ViewSet):
    """
    ViewSet for viewing settings.

    This is a read-only viewset - settings can only be viewed by admin/auditor users.
    """

    permission_classes = [IsAdminUser, AnsibleBaseObjectPermissions]

    def _get_current_settings(self):
        """Helper to get serializable settings."""
        setting_dict = DYNACONF.to_dict()

        def serialize_value(value):
            from pathlib import Path

            if isinstance(value, Path):
                return str(value)
            elif isinstance(value, dict):
                return {k: serialize_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [serialize_value(item) for item in value]
            return value

        return serialize_value(setting_dict)

    @extend_schema(
        operation_id="settings_list",
        description="Get all configuration settings",
        responses={200: dict},
    )
    def list(self, request):
        """Get all current configuration settings from DYNACONF."""
        return Response(self._get_current_settings())
