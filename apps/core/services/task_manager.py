"""
Task management service.

Handles all task-related operations including creation, listing, cancellation,
and retry functionality.
"""

import json
from datetime import datetime
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.utils import timezone

from apps.tasks.models import Task

User = get_user_model()


class TaskManager:
    """Manages task operations for the metrics service."""

    def __init__(self, output_formatter):
        """
        Initialize the task manager.

        Args:
            output_formatter: OutputFormatter instance for consistent output
        """
        self.output = output_formatter

    def create_task(self, options: dict[str, Any]) -> Task:
        """
        Create a new task.

        Args:
            options: Dictionary containing task creation options

        Returns:
            Created Task instance

        Raises:
            CommandError: If task creation fails
        """
        try:
            # Parse task data
            task_data = self._parse_task_data(options.get("data"))

            # Parse scheduled time
            scheduled_time = self._parse_scheduled_time(options.get("scheduled_time"))

            # Get user
            user = self._get_user(options.get("user"))

            # Create task
            task = Task.objects.create(
                name=options["name"],
                function_name=options["function"],
                task_data=task_data,
                description=options.get("description", ""),
                scheduled_time=scheduled_time,
                cron_expression=options.get("cron"),
                is_recurring=options.get("recurring", False),
                priority=options["priority"],
                created_by=user,
            )

            self.output.success(f"Created task {task.id}: {task.name}")
            return task

        except Exception as e:
            raise CommandError(f"Failed to create task: {e}") from e

    def _parse_task_data(self, data_str: str | None) -> dict[str, Any]:
        """Parse JSON task data from string."""
        if not data_str:
            return {}

        try:
            return json.loads(data_str)
        except json.JSONDecodeError as err:
            raise CommandError("Invalid JSON in --data argument") from err

    def _parse_scheduled_time(self, time_str: str | None) -> datetime | None:
        """Parse scheduled time from string."""
        if not time_str:
            return None

        try:
            scheduled_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            return timezone.make_aware(scheduled_time)
        except ValueError as err:
            raise CommandError("Invalid scheduled_time format. Use YYYY-MM-DD HH:MM:SS") from err

    def _get_user(self, username: str | None) -> User | None:
        """Get user by username."""
        if not username:
            return None

        try:
            return User.objects.get(username=username)
        except User.DoesNotExist as err:
            raise CommandError(f"User '{username}' not found") from err
