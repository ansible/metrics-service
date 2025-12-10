"""
Base serializers to reduce code duplication in API serializers.
"""

from typing import Any

from rest_framework import serializers

from apps.core.utils import get_count_safely


class CountFieldMixin:
    """
    Mixin to provide standardized count field methods for serializers.
    """

    def get_users_count(self, obj: Any) -> int:
        """Return count of users associated with the object."""
        return get_count_safely(getattr(obj, "users", None))

    def get_admins_count(self, obj: Any) -> int:
        """Return count of admins associated with the object."""
        return get_count_safely(getattr(obj, "admins", None))

    def get_tasks_count(self, obj: Any) -> int:
        """Return count of tasks associated with the object."""
        return get_count_safely(getattr(obj, "tasks", None))


class StatusFieldMixin:
    """
    Mixin to provide standardized status field methods for serializers.
    """

    def get_status_display(self, obj: Any) -> str:
        """Return human-readable status display."""
        if hasattr(obj, "get_status_display"):
            return obj.get_status_display()
        return getattr(obj, "status", "unknown")


class BaseModelSerializer(serializers.HyperlinkedModelSerializer, CountFieldMixin):
    """
    Base serializer class with common functionality.
    """

    # Common field definitions
    COMMON_FIELDS = ["id", "url", "created", "modified"]

    @classmethod
    def build_common_fields(
        cls, model_fields: list[str], extra_fields: list[str] | None = None
    ) -> list[str]:
        """Build complete field list with common fields."""
        fields = cls.COMMON_FIELDS + model_fields
        if extra_fields:
            fields.extend(extra_fields)
        return fields

    @classmethod
    def build_extra_kwargs(
        cls, url_view_name: str, extra_kwargs: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Build extra_kwargs with common URL configuration."""
        kwargs = {"url": {"view_name": url_view_name}}
        if extra_kwargs:
            kwargs.update(extra_kwargs)
        return kwargs

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the serializer with common setup."""
        super().__init__(*args, **kwargs)
        self._setup_common_fields()

    def _setup_common_fields(self) -> None:
        """Set up common read-only fields that appear in most serializers."""
        common_readonly_fields = ["id", "url", "created", "modified"]

        if hasattr(self.Meta, "read_only_fields"):
            self.Meta.read_only_fields = list(
                set(list(self.Meta.read_only_fields) + common_readonly_fields)
            )
        else:
            self.Meta.read_only_fields = common_readonly_fields

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Common validation logic for all serializers."""
        return super().validate(attrs)

    def to_representation(self, instance: Any) -> dict[str, Any]:
        """Common representation logic for all serializers."""
        data = super().to_representation(instance)

        if getattr(self.Meta, "remove_null_values", False):
            return {key: value for key, value in data.items() if value is not None}

        return data
