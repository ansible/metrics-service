"""
API v1 serializers for metrics_service following AAP standards.
"""

from rest_framework import serializers

from apps.core.models import Organization, Setting, Team, User

from .base_serializers import BaseModelSerializer, CountFieldMixin

view_name_org_detail = "organization-detail"


class UserSerializer(serializers.HyperlinkedModelSerializer):
    """Serializer for User model following AAP patterns."""

    confirm_password = serializers.CharField(
        write_only=True,
        required=False,
        help_text="Confirm password - must match the password field",
    )
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        required=False,
        allow_null=True,
        help_text="The organization this user belongs to",
    )

    class Meta:
        model = User
        fields = [
            "id",
            "url",
            "username",
            "password",
            "confirm_password",
            "email",
            "first_name",
            "last_name",
            "is_superuser",
            "is_system_auditor",
            "organization",
            "created",
            "modified",
        ]
        read_only_fields = [
            "id",
            "url",
            "created",
            "modified",
        ]
        extra_kwargs = {
            "password": {"write_only": True, "required": False},
            "url": {"view_name": "user-detail"},
        }

    def get_fields(self):
        """Override to make user type fields conditionally read-only based on permissions."""
        fields = super().get_fields()
        request = self.context.get("request")

        if request and request.user:
            user = request.user
            if not user.is_superuser:
                fields["is_superuser"].read_only = True
                fields["is_system_auditor"].read_only = True

        return fields

    def validate(self, data):
        """Validate that password and confirm_password match when both are provided."""
        password = data.get("password")
        confirm_password = data.get("confirm_password")

        if password and confirm_password:
            if password != confirm_password:
                raise serializers.ValidationError(
                    {"confirm_password": "Password and confirm password do not match."}
                )
        elif confirm_password and not password:
            raise serializers.ValidationError(
                {"password": "Password is required when providing password confirmation."}
            )

        return data

    def create(self, validated_data):
        """Create a new user with proper password hashing."""
        password = validated_data.pop("password", None)
        validated_data.pop("confirm_password", None)
        user = User.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        """Update user with proper password handling."""
        password = validated_data.pop("password", None)
        validated_data.pop("confirm_password", None)
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
    related = serializers.SerializerMethodField()
    object_role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id",
            "url",
            "name",
            "description",
            "extra_field",
            "users_count",
            "admins_count",
            "related",
            "object_role",
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
            "related",
            "object_role",
        ]
        extra_kwargs = {
            "url": {"view_name": view_name_org_detail},
        }

    def get_users_count(self, obj):
        """Return count of users in organization."""
        return obj.users.count()

    def get_admins_count(self, obj):
        """Return count of admins in organization."""
        return obj.admins.count()

    def get_related(self, obj):
        """Return related URLs for this organization."""
        request = self.context.get("request")
        if not request:
            return {}

        return {
            "users": request.build_absolute_uri(f"/v1/organizations/{obj.id}/users/"),
        }

    def get_object_role(self, obj):
        """Return object-level permissions for the current user using DAB permission system."""
        request = self.context.get("request")
        if not request or not request.user:
            return {"add": False, "edit": False, "delete": False}

        user = request.user
        app_label = obj._meta.app_label
        model_name = obj._meta.model_name

        permissions = {
            "add": user.has_perm(f"{app_label}.add_{model_name}"),
            "edit": user.has_perm(f"{app_label}.change_{model_name}", obj),
            "delete": user.has_perm(f"{app_label}.delete_{model_name}", obj),
        }

        return permissions


class TeamSerializer(BaseModelSerializer, CountFieldMixin):
    """
    Serializer for Team model following AAP patterns.
    """

    users_count = serializers.SerializerMethodField()
    admins_count = serializers.SerializerMethodField()

    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_url = serializers.HyperlinkedRelatedField(
        source="organization", view_name=view_name_org_detail, read_only=True
    )

    related = serializers.SerializerMethodField()
    object_role = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            "id",
            "url",
            "name",
            "description",
            "organization",
            "organization_name",
            "organization_url",
            "users_count",
            "admins_count",
            "related",
            "object_role",
            "created",
            "modified",
        ]
        read_only_fields = [
            "id",
            "url",
            "organization_name",
            "organization_url",
            "users_count",
            "admins_count",
            "related",
            "object_role",
            "created",
            "modified",
        ]
        extra_kwargs = {
            "url": {"view_name": "team-detail"},
            "organization": {"view_name": view_name_org_detail, "queryset": Organization.objects.all()},
        }

    def get_users_count(self, obj):
        """Return count of users in team."""
        return obj.users.count()

    def get_admins_count(self, obj):
        """Return count of admins in team."""
        return obj.admins.count()

    def get_related(self, obj):
        """Return related URLs for this team."""
        request = self.context.get("request")
        if not request:
            return {}

        return {
            "users": request.build_absolute_uri(f"/v1/teams/{obj.id}/users/"),
            "admins": request.build_absolute_uri(f"/v1/teams/{obj.id}/admins/"),
            "organization": request.build_absolute_uri(f"/v1/organizations/{obj.organization.id}/"),
        }

    def get_object_role(self, obj):
        """Return object-level permissions for the current user."""
        request = self.context.get("request")
        if not request or not request.user:
            return {"add": False, "edit": False, "delete": False}

        user = request.user
        app_label = obj._meta.app_label
        model_name = obj._meta.model_name

        permissions = {
            "add": user.has_perm(f"{app_label}.add_{model_name}"),
            "edit": user.has_perm(f"{app_label}.change_{model_name}", obj),
            "delete": user.has_perm(f"{app_label}.delete_{model_name}", obj),
        }

        return permissions


class SettingSerializer(BaseModelSerializer):
    """
    Serializer for Setting model following AAP and Controller patterns.
    """

    class Meta:
        model = Setting
        fields = [
            "id",
            "url",
            "setting_key",
            "current_value",
            "previous_value",
            "last_modified_by",
            "created",
            "modified",
        ]
        read_only_fields = [
            "id",
            "url",
            "previous_value",
            "last_modified_by",
            "created",
            "modified",
        ]
        extra_kwargs = {
            "url": {"view_name": "settings-detail"},
        }
