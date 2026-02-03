"""
Base serializers to reduce code duplication in API serializers.
"""

from typing import Any

from rest_framework import serializers


# Base serializer class with common functionality; add an `url` field for links to work
class BaseModelSerializer(serializers.HyperlinkedModelSerializer):
    pass


class StatusFieldMixin:
    """
    Mixin to provide standardized status field handling.

    This mixin reduces duplication of status field setup across
    serializers that include status tracking fields.
    """

    started_at = serializers.DateTimeField(read_only=True, help_text="When the process started")
    completed_at = serializers.DateTimeField(read_only=True, help_text="When the process completed")
    error_message = serializers.CharField(read_only=True, help_text="Error message if process failed")

    def get_duration(self, obj: Any) -> float | None:
        return obj.get_duration()
