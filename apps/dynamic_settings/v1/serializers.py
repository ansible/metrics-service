"""
Serializers for dynamic settings API v1.
"""

from rest_framework import serializers

from ..models import Setting


class SettingSerializer(serializers.ModelSerializer):
    """
    Serializer for Setting model following AAP and Controller patterns.

    Supports RESTful PUT/PATCH operations on individual settings by key.
    """

    class Meta:
        model = Setting
        fields = [
            "id",
            "setting_key",
            "current_value",
            "previous_value",
            "last_modified_by",
            "created",
            "modified",
        ]
        read_only_fields = [
            "id",
            "previous_value",
            "last_modified_by",
            "created",
            "modified",
        ]
        extra_kwargs = {
            "setting_key": {"help_text": "The unique key for this setting (e.g., 'DEBUG', 'SECRET_KEY')"},
            "current_value": {"help_text": "The current value of this setting (JSON serialized)"},
        }
