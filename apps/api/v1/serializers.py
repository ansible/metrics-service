"""
API v1 serializers for metrics_service following AAP standards.

This module provides serializers for the API v1 endpoints with reduced
code duplication through the use of base serializer classes and mixins.
"""

from rest_framework import serializers

from apps.core.models import Animal, Organization, Team, User

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


class TeamSerializer(BaseModelSerializer, CountFieldMixin):
    """
    Serializer for Team model following AAP patterns.

    This serializer provides team management functionality with hierarchical
    support and user/admin count fields for efficient data retrieval.
    """

    organization_name = serializers.CharField(source="organization.name", read_only=True)
    users_count = serializers.SerializerMethodField()
    admins_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            "id",
            "url",
            "name",
            "description",
            "organization",
            "organization_name",
            "team_parents",
            "users",
            "admins",
            "users_count",
            "admins_count",
            "created",
            "modified",
        ]

        read_only_fields = [
            "organization_name",
            "users_count",
            "admins_count",
        ]
        extra_kwargs = {
            "url": {"view_name": "api:v1:team-detail"},
            "organization": {"view_name": "api:v1:organization-detail"},
            "team_parents": {"view_name": "api:v1:team-detail"},
            "users": {"view_name": "api:v1:user-detail"},
            "admins": {"view_name": "api:v1:user-detail"},
        }


class AnimalSerializer(BaseModelSerializer, CountFieldMixin):
    """
    Serializer for Animal model following AAP patterns.

    This serializer provides animal management functionality with owner
    information and friend count fields for demonstration purposes.
    """

    owner_username = serializers.CharField(source="owner.username", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    friends_count = serializers.SerializerMethodField()

    class Meta:
        model = Animal
        fields = [
            "id",
            "url",
            "name",
            "kind",
            "kind_display",
            "age",
            "owner",
            "owner_username",
            "people_friends",
            "friends_count",
            "created",
            "modified",
        ]
        read_only_fields = [
            "owner_username",
            "kind_display",
            "friends_count",
        ]
        extra_kwargs = {
            "url": {"view_name": "api:v1:animal-detail"},
            "owner": {"view_name": "api:v1:user-detail"},
            "people_friends": {"view_name": "api:v1:user-detail"},
        }
