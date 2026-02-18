"""
Common mixins for task-related models.
"""

from django.db import models


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

    def get_duration(self) -> float | None:
        if not self.started_at or not self.completed_at:
            return None

        return (self.completed_at - self.started_at).total_seconds()
