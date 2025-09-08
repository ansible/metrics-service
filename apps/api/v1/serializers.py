"""
API v1 serializers for metrics_service following AAP standards.

This module provides serializers for the API v1 endpoints with reduced
code duplication through the use of base serializer classes and mixins.
"""

from rest_framework import serializers

from apps.core.models import Organization, User

from .base_serializers import BaseModelSerializer, CountFieldMixin, PasswordHandlingMixin


class UserSerializer(BaseModelSerializer, PasswordHandlingMixin):
    """
    Serializer for User model following AAP patterns.

    This serializer provides comprehensive user management functionality
    including password handling and standard field configurations.
    """

    class Meta:
        model = User
        fields = [
            "id",
            "url",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
            "created",
            "modified",
        ]
        read_only_fields = [
            "date_joined",
            "last_login",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
            "url": {"view_name": "api:v1:user-detail"},
        }


class OrganizationSerializer(BaseModelSerializer, CountFieldMixin):
    """
    Serializer for Organization model following AAP patterns.

    This serializer provides organization management functionality with
    user and admin count fields for efficient data retrieval.
    """

    users_count = serializers.SerializerMethodField()
    admins_count = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id",
            "url",
            "name",
            "description",
            "extra_field",
            "users",
            "admins",
            "users_count",
            "admins_count",
            "created",
            "modified",
        ]

        read_only_fields = [
            "users_count",
            "admins_count",
        ]
        extra_kwargs = {
            "url": {"view_name": "api:v1:organization-detail"},
            "users": {"view_name": "api:v1:user-detail"},
            "admins": {"view_name": "api:v1:user-detail"},
        }

    def get_related(self, obj):
        """Return related URLs for this organization."""
        request = self.context.get("request")
        if not request:
            return {}

        return {
            "users": request.build_absolute_uri(f"/api/v1/organizations/{obj.id}/users/"),
            # Future related endpoints can be added here, e.g.:
            # "teams": request.build_absolute_uri(f"/api/v1/organizations/{obj.id}/teams/"),
        }

    def get_object_role(self, obj):
        """
        Return object-level permissions for the current user using DAB permission system.

        Uses Django's has_perm() method which DAB extends to provide
        comprehensive permission checking including RBAC roles.
        """
        request = self.context.get("request")
        if not request or not request.user:
            return {"add": False, "edit": False, "delete": False}

        user = request.user
        app_label = obj._meta.app_label
        model_name = obj._meta.model_name

        # Use Django's permission system (which DAB extends automatically)
        permissions = {
            "add": user.has_perm(f"{app_label}.add_{model_name}"),
            "edit": user.has_perm(f"{app_label}.change_{model_name}", obj),
            "delete": user.has_perm(f"{app_label}.delete_{model_name}", obj),
        }

        return permissions
