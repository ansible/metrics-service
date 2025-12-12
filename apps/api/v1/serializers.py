"""
API v1 serializers for metrics_service following AAP standards.
"""

from ansible_base.lib.serializers.common import CommonUserSerializer, NamedCommonModelSerializer
from ansible_base.rbac.api.related import RelatedAccessMixin
from rest_framework import serializers

from apps.core.models import Organization, Setting, Team, User

from .base_serializers import BaseModelSerializer


class OrganizationSerializer(RelatedAccessMixin, NamedCommonModelSerializer):
    class Meta:
        model = Organization
        fields = "__all__"


class TeamSerializer(RelatedAccessMixin, NamedCommonModelSerializer):
    class Meta:
        model = Team
        fields = "__all__"


class UserSerializer(CommonUserSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        exclude = ("user_permissions", "groups")
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user


class SettingSerializer(BaseModelSerializer):
    """
    Serializer for Setting model following AAP and Controller patterns.

    Supports RESTful PUT/PATCH operations on individual settings by key.
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
            "url": {"view_name": "api:v1:settings-detail"},
            "setting_key": {"help_text": "The unique key for this setting (e.g., 'DEBUG', 'SECRET_KEY')"},
            "current_value": {"help_text": "The current value of this setting (JSON serialized)"},
        }
