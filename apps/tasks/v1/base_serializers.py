"""
Base serializers to reduce code duplication in API serializers.
"""

from typing import Any

from rest_framework import serializers

from apps.tasks.api_utils import get_count_safely


class CountFieldMixin:
    """
    Mixin to provide standardized count field methods for serializers.

    This mixin reduces duplication of count field implementations across
    multiple serializers that need to count related objects.
    """

    def get_users_count(self, obj: Any) -> int:
        """
        Return count of users associated with the object.

        Args:
            obj: The model instance being serialized

        Returns:
            int: Number of users
        """
        return get_count_safely(getattr(obj, "users", None))

    def get_admins_count(self, obj: Any) -> int:
        """
        Return count of admins associated with the object.

        Args:
            obj: The model instance being serialized

        Returns:
            int: Number of admins
        """
        return get_count_safely(getattr(obj, "admins", None))

    def get_friends_count(self, obj: Any) -> int:
        """
        Return count of friends associated with the object.

        Args:
            obj: The model instance being serialized

        Returns:
            int: Number of friends
        """
        return get_count_safely(getattr(obj, "people_friends", None))

    def get_tasks_count(self, obj: Any) -> int:
        """
        Return count of tasks associated with the object.

        Args:
            obj: The model instance being serialized

        Returns:
            int: Number of tasks
        """
        return get_count_safely(getattr(obj, "tasks", None))

    def get_executions_count(self, obj: Any) -> int:
        """
        Return count of executions associated with the object.

        Args:
            obj: The model instance being serialized

        Returns:
            int: Number of executions
        """
        return get_count_safely(getattr(obj, "executions", None))


class BaseModelSerializer(serializers.HyperlinkedModelSerializer, CountFieldMixin):
    """
    Base serializer class with common functionality.

    This base class provides common serializer functionality that can be
    inherited by all model serializers to reduce code duplication.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize the serializer with common setup.

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments
        """
        super().__init__(*args, **kwargs)
        self._setup_common_fields()

    def _setup_common_fields(self) -> None:
        """
        Set up common read-only fields that appear in most serializers.

        This method automatically marks common fields as read-only to reduce
        duplication across serializer Meta classes.

        Returns:
            None
        """
        common_readonly_fields = ["id", "url", "created", "modified"]

        if hasattr(self.Meta, "read_only_fields"):
            # Extend existing read_only_fields
            self.Meta.read_only_fields = list(set(list(self.Meta.read_only_fields) + common_readonly_fields))
        else:
            # Set read_only_fields if not already defined
            self.Meta.read_only_fields = common_readonly_fields

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """
        Common validation logic for all serializers.

        This method provides a place to add validation logic that should
        apply to all serializers, reducing duplication.

        Args:
            attrs (dict): Attributes to validate

        Returns:
            dict: Validated attributes
        """
        # Add any common validation logic here
        return super().validate(attrs)

    def to_representation(self, instance: Any) -> dict[str, Any]:
        """
        Common representation logic for all serializers.

        This method provides a place to add representation logic that should
        apply to all serializers, such as filtering null values.

        Args:
            instance: The model instance being serialized

        Returns:
            dict: Serialized representation
        """
        data = super().to_representation(instance)

        # Remove null values from representation if configured
        if getattr(self.Meta, "remove_null_values", False):
            return {key: value for key, value in data.items() if value is not None}

        return data

    @classmethod
    def build_common_fields(cls, base_fields: list[str], extra_fields: list[str] | None = None) -> list[str]:
        """
        Build common field lists for serializer Meta classes.

        Args:
            base_fields (list): Base fields specific to the model
            extra_fields (list): Additional fields to include

        Returns:
            list: Complete field list
        """
        fields = ["id", "url"] + base_fields + ["created", "modified"]

        if extra_fields:
            # Insert extra fields before timestamps
            fields = fields[:-2] + extra_fields + fields[-2:]

        return fields

    @classmethod
    def build_extra_kwargs(
        cls, view_name: str, additional_kwargs: dict[str, str] | None = None
    ) -> dict[str, dict[str, str]]:
        """
        Build common extra_kwargs for serializer Meta classes.

        Args:
            view_name (str): The view name for the URL field
            additional_kwargs (dict): Additional kwargs to merge

        Returns:
            dict: Complete extra_kwargs dictionary
        """
        kwargs = {"url": {"view_name": view_name}}

        if additional_kwargs:
            kwargs.update(additional_kwargs)

        return kwargs


class PasswordHandlingMixin:
    """
    Mixin to provide standardized password handling in serializers.

    This mixin reduces duplication of password handling logic across
    serializers that need to manage password fields.
    """

    def create(self, validated_data: dict[str, Any]) -> Any:
        """
        Create a new instance with proper password hashing.

        Args:
            validated_data (dict): Validated data for creating the instance

        Returns:
            Model instance: The created instance
        """
        password = validated_data.pop("password", None)
        instance = super().create(validated_data)

        if password and hasattr(instance, "set_password"):
            instance.set_password(password)
            instance.save()

        return instance

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:
        """
        Update an instance with proper password handling.

        Args:
            instance: The instance to update
            validated_data (dict): Validated data for updating the instance

        Returns:
            Model instance: The updated instance
        """
        password = validated_data.pop("password", None)

        # Update all other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Handle password separately
        if password and hasattr(instance, "set_password"):
            instance.set_password(password)

        instance.save()
        return instance


class TimestampFieldMixin:
    """
    Mixin to provide standardized timestamp field handling.

    This mixin reduces duplication of timestamp field setup across
    serializers that include created/modified timestamps.
    """

    created = serializers.DateTimeField(read_only=True, help_text="When this object was created")
    modified = serializers.DateTimeField(read_only=True, help_text="When this object was last modified")


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
        """
        Return the duration of the process in seconds.

        Args:
            obj: The model instance being serialized

        Returns:
            float or None: Duration in seconds, or None if not completed
        """
        if hasattr(obj, "get_duration"):
            return obj.get_duration()
        return None


class ValidationMixin:
    """
    Mixin to provide common validation methods for serializers.

    This mixin reduces duplication of validation logic across serializers
    that need to validate JSON fields, cron expressions, and other common data types.
    """

    def validate_json_field(self, value: Any, field_name: str = "task_data") -> Any:
        """
        Validate that a field contains valid JSON data.

        Accepts either a dict/list (already parsed JSON) or a string that will be
        parsed as JSON. This is useful for fields that accept JSON input.

        Args:
            value: The value to validate (string or dict/list)
            field_name: Name of the field being validated (for error messages)

        Returns:
            dict or list: The parsed JSON data

        Raises:
            serializers.ValidationError: If the JSON is invalid
        """
        import json

        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                raise serializers.ValidationError(f"Invalid JSON data in {field_name}: {e}") from e
        # Already a dict or list, return as-is
        return value

    def validate_cron_expression(self, value: str | None) -> str | None:
        """
        Validate that a cron expression is syntactically correct.

        Uses the croniter library to validate the cron expression format.
        Returns None if value is None or empty.

        Args:
            value: The cron expression to validate

        Returns:
            str or None: The validated cron expression

        Raises:
            serializers.ValidationError: If the cron expression is invalid
        """
        if value:
            try:
                from croniter import croniter

                croniter(value)
            except (ValueError, TypeError) as e:
                raise serializers.ValidationError(f"Invalid cron expression: {e}") from e
        return value


class TaskFieldMixin:
    """
    Mixin to provide task-related SerializerMethodFields.

    This mixin reduces duplication of task permission and status check methods
    across task-related serializers.
    """

    def get_can_retry(self, obj: Any) -> bool:
        """
        Check if the task can be retried.

        Args:
            obj: The task instance being serialized

        Returns:
            bool: True if task can be retried, False otherwise
        """
        if hasattr(obj, "can_retry"):
            return obj.can_retry()
        return False

    def get_can_delete(self, obj: Any) -> bool:
        """
        Check if the task can be deleted.

        Args:
            obj: The task instance being serialized

        Returns:
            bool: True if task can be deleted, False otherwise
        """
        if hasattr(obj, "can_delete"):
            return obj.can_delete()
        return False

    def get_can_modify(self, obj: Any) -> bool:
        """
        Check if the task can be modified.

        Args:
            obj: The task instance being serialized

        Returns:
            bool: True if task can be modified, False otherwise
        """
        if hasattr(obj, "can_modify"):
            return obj.can_modify()
        return False
