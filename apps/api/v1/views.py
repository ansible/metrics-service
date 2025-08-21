"""
API v1 views for metrics_service following AAP standards.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from ansible_base.oauth2_provider.permissions import OAuth2ScopePermission
from ansible_base.rbac.api.permissions import AnsibleBaseObjectPermissions
from ansible_base.lib.utils.views.django_app_api import AnsibleBaseDjangoAppApiView

from apps.core.models import Animal, Organization, Team, User
from .serializers import (
    AnimalSerializer,
    OrganizationSerializer,
    TeamSerializer,
    UserSerializer,
)


class UserViewSet(AnsibleBaseDjangoAppApiView, viewsets.ModelViewSet):
    """ViewSet for User model following AAP patterns."""

    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [OAuth2ScopePermission, AnsibleBaseObjectPermissions]
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

    def get_queryset(self):
        """Filter queryset based on user permissions."""
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


class OrganizationViewSet(AnsibleBaseDjangoAppApiView, viewsets.ModelViewSet):
    """ViewSet for Organization model following AAP patterns."""

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [OAuth2ScopePermission, AnsibleBaseObjectPermissions]
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
        """Filter queryset based on user permissions."""
        return Organization.access_qs(self.request.user, queryset=self.queryset)

    @extend_schema(
        operation_id="organizations_add_user",
        description="Add user to organization",
        request={"user_id": "integer"},
        responses={204: None},
    )
    @action(detail=True, methods=["post"])
    def add_user(self, request, pk=None):
        """Add user to organization."""
        organization = self.get_object()
        user_id = request.data.get("user_id")

        try:
            user = User.objects.get(id=user_id)
            organization.users.add(user)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    @extend_schema(
        operation_id="organizations_remove_user",
        description="Remove user from organization",
        request={"user_id": "integer"},
        responses={204: None},
    )
    @action(detail=True, methods=["post"])
    def remove_user(self, request, pk=None):
        """Remove user from organization."""
        organization = self.get_object()
        user_id = request.data.get("user_id")

        try:
            user = User.objects.get(id=user_id)
            organization.users.remove(user)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


class TeamViewSet(AnsibleBaseDjangoAppApiView, viewsets.ModelViewSet):
    """ViewSet for Team model following AAP patterns."""

    queryset = Team.objects.select_related("organization").all()
    serializer_class = TeamSerializer
    permission_classes = [OAuth2ScopePermission, AnsibleBaseObjectPermissions]
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

    def get_queryset(self):
        """Filter queryset based on user permissions."""
        return Team.access_qs(self.request.user, queryset=self.queryset)


class AnimalViewSet(AnsibleBaseDjangoAppApiView, viewsets.ModelViewSet):
    """ViewSet for Animal model following AAP patterns."""

    queryset = Animal.objects.select_related("owner").all()
    serializer_class = AnimalSerializer
    permission_classes = [OAuth2ScopePermission, AnsibleBaseObjectPermissions]
    search_fields = ["name", "owner__username"]
    filterset_fields = {
        "name": ["exact", "icontains"],
        "kind": ["exact"],
        "age": ["exact", "gte", "lte"],
        "owner": ["exact"],
        "owner__username": ["exact", "icontains"],
        "created": ["gte", "lte"],
        "modified": ["gte", "lte"],
    }
    ordering_fields = ["name", "kind", "age", "owner__username", "created", "modified"]
    ordering = ["name"]

    def get_queryset(self):
        """Filter queryset based on user permissions."""
        return Animal.access_qs(self.request.user, queryset=self.queryset)

    @extend_schema(
        operation_id="animals_feed",
        description="Feed the animal",
        request={"food": "string"},
        responses={200: {"message": "string"}},
    )
    @action(detail=True, methods=["post"])
    def feed(self, request, pk=None):
        """Custom action to feed an animal."""
        animal = self.get_object()
        food = request.data.get("food", "generic food")

        # Example custom logic
        message = f"{animal.name} has been fed {food}!"

        return Response({"message": message})

    @extend_schema(
        operation_id="animals_my_animals",
        description="Get animals owned by current user",
        responses={200: AnimalSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def my_animals(self, request):
        """Get animals owned by the current user."""
        animals = self.get_queryset().filter(owner=request.user)
        serializer = self.get_serializer(animals, many=True)
        return Response(serializer.data)
