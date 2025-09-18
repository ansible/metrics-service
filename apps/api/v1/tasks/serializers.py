"""
Task-related serializers for the API v1 endpoints.

This module provides serializers for task management functionality
converted from the manage_tasks.py command to REST API endpoints.
"""

import json

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.tasks.models import (
    Task,
    TaskExecution,
)

from ..base_serializers import BaseModelSerializer, StatusFieldMixin

User = get_user_model()


class TaskSerializer(BaseModelSerializer, StatusFieldMixin):
    """
    Main serializer for Task model with comprehensive functionality.

    This serializer provides task creation, scheduling, and monitoring
    capabilities for the dashboard interface and includes all fields
    needed for task management.
    """

    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    executions_count = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    can_retry = serializers.SerializerMethodField()
    is_ready_to_run = serializers.SerializerMethodField()
    next_run_time = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = BaseModelSerializer.build_common_fields(
            [
                "name",
                "function_name",
                "task_data",
                "scheduled_time",
                "cron_expression",
                "is_recurring",
                "status",
                "priority",
                "attempts",
                "max_attempts",
                "timeout_seconds",
                "result_data",
                "started_at",
                "completed_at",
                "error_message",
                "created_by",
            ],
            [
                "created_by_username",
                "executions_count",
                "duration",
                "can_retry",
                "is_ready_to_run",
                "next_run_time",
            ],
        )
        read_only_fields = [
            "created_by_username",
            "executions_count",
            "duration",
            "can_retry",
            "is_ready_to_run",
            "next_run_time",
            "status",
            "attempts",
            "result_data",
            "started_at",
            "completed_at",
            "error_message",
        ]
        extra_kwargs = BaseModelSerializer.build_extra_kwargs(
            "api:v1:tasks:task-detail",
            {
                "created_by": {"view_name": "api:v1:user-detail"},
                "scheduled_time": {"help_text": "ISO 8601 format datetime when task should run"},
                "task_data": {"help_text": "JSON data to pass to the task function"},
            },
        )

    def get_executions_count(self, obj) -> int:
        """Get count of task executions."""
        return obj.executions.count()

    def get_duration(self, obj) -> float | None:
        """Get task duration in seconds."""
        if hasattr(obj, "get_duration"):
            return obj.get_duration()
        return None

    def get_can_retry(self, obj) -> bool:
        """Check if task can be retried."""
        return obj.can_retry()

    def get_is_ready_to_run(self, obj) -> bool:
        """Check if task is ready to run."""
        return obj.is_ready_to_run()

    def get_next_run_time(self, obj):
        """Get next run time for recurring tasks."""
        next_time = obj.get_next_run_time()
        return next_time.isoformat() if next_time else None


class TaskCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating tasks via the API.

    This serializer handles task creation similar to the manage_tasks.py create
    command with validation and proper data handling.
    """

    user = serializers.CharField(required=False, help_text="Username of task creator (optional)")

    class Meta:
        model = Task
        fields = [
            "name",
            "function_name",
            "task_data",
            "scheduled_time",
            "cron_expression",
            "is_recurring",
            "priority",
            "max_attempts",
            "timeout_seconds",
            "user",
        ]
        extra_kwargs = {
            "scheduled_time": {
                "required": False,
                "help_text": "ISO 8601 format datetime. Leave empty for immediate execution.",
            },
            "task_data": {"required": False, "help_text": "JSON object with task parameters"},
            "cron_expression": {"required": False, "help_text": "Cron expression for recurring tasks"},
            "is_recurring": {"default": False},
            "priority": {"default": 2},
            "max_attempts": {"default": 3},
            "timeout_seconds": {"default": 3600},
        }

    def validate_function_name(self, value):
        """Validate that the function name exists in available task functions."""
        from apps.tasks.tasks import TASK_FUNCTIONS

        if value not in TASK_FUNCTIONS:
            available_functions = list(TASK_FUNCTIONS.keys())
            raise serializers.ValidationError(f"Invalid function name. Available functions: {available_functions}")
        return value

    def validate_cron_expression(self, value):
        """Validate cron expression format."""
        if value:
            try:
                from croniter import croniter

                croniter(value)
            except (ValueError, TypeError) as e:
                raise serializers.ValidationError(f"Invalid cron expression: {e}") from e
        return value

    def validate_task_data(self, value):
        """Validate task data is proper JSON if provided as string."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                raise serializers.ValidationError(f"Invalid JSON data: {e}") from e
        return value

    def validate_user(self, value):
        """Validate user exists if provided."""
        if value:
            try:
                return User.objects.get(username=value)
            except User.DoesNotExist as e:
                raise serializers.ValidationError(f"User '{value}' not found") from e
        return None

    def create(self, validated_data):
        """Create task with proper user assignment."""
        user = validated_data.pop("user", None)

        # Use provided user or request user
        if user:
            validated_data["created_by"] = user
        elif (hasattr(self.context.get("request"), "user") and
              self.context["request"].user and self.context["request"].user.is_authenticated):
            validated_data["created_by"] = self.context["request"].user

        return super().create(validated_data)


class TaskListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for task list endpoints.

    This serializer provides essential task information for list views,
    similar to the manage_tasks.py list command output.
    """

    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "name",
            "function_name",
            "status",
            "status_display",
            "priority",
            "priority_display",
            "created",
            "scheduled_time",
            "created_by_username",
        ]


class TaskCleanupSerializer(serializers.Serializer):
    """
    Serializer for task cleanup operations.

    This serializer handles the cleanup functionality from manage_tasks.py.
    """

    days = serializers.IntegerField(default=30, min_value=1, help_text="Number of days to keep completed tasks")
    dry_run = serializers.BooleanField(default=False, help_text="Show what would be deleted without actually deleting")


class TaskExecutionSerializer(BaseModelSerializer):
    """
    Serializer for TaskExecution model for execution tracking and monitoring.
    """

    task_name = serializers.CharField(source="task.name", read_only=True)
    task_function = serializers.CharField(source="task.function_name", read_only=True)
    duration = serializers.SerializerMethodField()

    class Meta:
        model = TaskExecution
        fields = BaseModelSerializer.build_common_fields(
            [
                "task",
                "status",
                "started_at",
                "completed_at",
                "worker_id",
                "result_data",
                "error_message",
                "execution_time_seconds",
            ],
            ["task_name", "task_function", "duration"],
        )
        read_only_fields = [
            "task_name",
            "task_function",
            "duration",
            "started_at",
            "completed_at",
            "execution_time_seconds",
        ]
        extra_kwargs = BaseModelSerializer.build_extra_kwargs(
            "api:v1:tasks:taskexecution-detail",
            {
                "task": {"view_name": "api:v1:tasks:task-detail"},
            },
        )

    def get_duration(self, obj) -> float | None:
        """Get execution duration in seconds."""
        if obj.started_at and obj.completed_at:
            return (obj.completed_at - obj.started_at).total_seconds()
        return None
