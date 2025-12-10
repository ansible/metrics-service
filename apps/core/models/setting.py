"""Setting model for configuration with rollback capability."""

from ansible_base.activitystream.models import AuditableModel
from ansible_base.lib.abstract_models.common import CommonModel
from django.db import models

from .mixins import AccessControlMixin


class Setting(CommonModel, AuditableModel, AccessControlMixin):
    """
    Stores configuration settings with rollback capability.
    """

    class Meta:
        app_label = "core"
        ordering = ["-modified"]  # Show newest changes first
        indexes = [
            models.Index(fields=["setting_key", "-modified"]),
            models.Index(fields=["last_modified_by", "-modified"]),
        ]

    # WHO changed it
    last_modified_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="configuration_changes",
        help_text="The user who made this configuration change.",
    )

    # WHAT was changed
    setting_key = models.CharField(
        max_length=255,
        help_text="The name of the setting that was changed",
        unique=True,
    )

    previous_value = models.TextField(
        blank=True,
        null=True,
        help_text="The previous value of the setting (JSON serialized).",
    )

    current_value = models.TextField(
        blank=True,
        null=True,
        help_text="The new value of the setting (JSON serialized).",
    )

    @classmethod
    def access_qs(cls, user, queryset=None):
        """
        Return queryset filtered by user permissions.
        Only system admins and auditors should see config changes.
        """
        if queryset is None:
            queryset = cls.objects.all()

        # Only superusers and system auditors can view config changes
        if user.is_superuser or getattr(user, "is_system_auditor", False):
            return queryset

        # Regular users cannot see config changes
        return queryset.none()

    def __str__(self):
        """String representation showing who changed what and when."""
        user_name = self.last_modified_by.username if self.last_modified_by else "System"
        return f"{user_name} changed {self.setting_key} at {self.modified}"
