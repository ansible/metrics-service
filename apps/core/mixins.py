"""
Common mixins and base classes for reducing code duplication.
"""

from django.db import models


class TimestampMixin(models.Model):
    """
    Abstract mixin to add created and modified timestamp fields.

    This mixin provides standardized timestamp functionality that can be
    used across multiple models.
    """

    created = models.DateTimeField(auto_now_add=True, help_text="When this object was created")
    modified = models.DateTimeField(auto_now=True, help_text="When this object was last modified")

    class Meta:
        abstract = True


class StatusTrackingMixin(models.Model):
    """
    Abstract mixin for models that need status tracking with timestamps.

    This mixin provides common status tracking fields and methods that can be
    used across multiple models that need to track status changes.
    """

    started_at = models.DateTimeField(null=True, blank=True, help_text="When the process started")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="When the process completed")
    error_message = models.TextField(blank=True, help_text="Error message if process failed")

    class Meta:
        abstract = True

    def mark_started(self) -> None:
        """
        Mark the process as started with current timestamp.

        Returns:
            None
        """
        from django.utils import timezone

        self.started_at = timezone.now()
        self.save(update_fields=["started_at"])

    def mark_completed(self, error_message: str = "") -> None:
        """
        Mark the process as completed with current timestamp.

        Args:
            error_message (str): Optional error message if the process failed

        Returns:
            None
        """
        from django.utils import timezone

        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=["completed_at", "error_message"])

    def get_duration(self) -> float | None:
        """
        Calculate the duration of the process in seconds.

        Returns:
            float: Duration in seconds, or None if not completed
        """
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
