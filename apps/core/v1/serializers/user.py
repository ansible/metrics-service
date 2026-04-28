from ansible_base.lib.serializers.common import CommonUserSerializer
from rest_framework import serializers

from apps.core.models import User


class UserSerializer(CommonUserSerializer):
    """Serializer for the User model, handling password hashing on create and update."""

    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        """Serializer meta configuration for UserSerializer."""

        model = User
        exclude = ("user_permissions", "groups")
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def create(self, validated_data):
        """Create a user, hashing the password if provided."""
        password = validated_data.pop("password", None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        """Update a user, hashing the password if provided."""
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user
