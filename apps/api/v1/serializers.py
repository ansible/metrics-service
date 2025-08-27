"""
API v1 serializers for metrics_service following AAP standards.
"""

from rest_framework import serializers

from apps.core.models import Animal, Organization, Team, User


class UserSerializer(serializers.HyperlinkedModelSerializer):
    """Serializer for User model following AAP patterns."""

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
            "id",
            "url",
            "date_joined",
            "last_login",
            "created",
            "modified",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
            "url": {"view_name": "api:v1:user-detail"},
        }

    def create(self, validated_data):
        """Create a new user with proper password hashing."""
        password = validated_data.pop("password", None)
        user = User.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        """Update user with proper password handling."""
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class OrganizationSerializer(serializers.HyperlinkedModelSerializer):
    """Serializer for Organization model following AAP patterns."""

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
            "id",
            "url",
            "created",
            "modified",
            "users_count",
            "admins_count",
        ]
        extra_kwargs = {
            "url": {"view_name": "api:v1:organization-detail"},
            "users": {"view_name": "api:v1:user-detail"},
            "admins": {"view_name": "api:v1:user-detail"},
        }

    def get_users_count(self, obj):
        """Return count of users in organization."""
        return obj.users.count()

    def get_admins_count(self, obj):
        """Return count of admins in organization."""
        return obj.admins.count()


class TeamSerializer(serializers.HyperlinkedModelSerializer):
    """Serializer for Team model following AAP patterns."""

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
            "id",
            "url",
            "organization_name",
            "created",
            "modified",
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

    def get_users_count(self, obj):
        """Return count of users in team."""
        return obj.users.count()

    def get_admins_count(self, obj):
        """Return count of admins in team."""
        return obj.admins.count()


class AnimalSerializer(serializers.HyperlinkedModelSerializer):
    """Serializer for Animal model following AAP patterns."""

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
            "id",
            "url",
            "owner_username",
            "kind_display",
            "friends_count",
            "created",
            "modified",
        ]
        extra_kwargs = {
            "url": {"view_name": "api:v1:animal-detail"},
            "owner": {"view_name": "api:v1:user-detail"},
            "people_friends": {"view_name": "api:v1:user-detail"},
        }

    def get_friends_count(self, obj):
        """Return count of people friends."""
        return obj.people_friends.count()
