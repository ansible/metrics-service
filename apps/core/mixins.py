"""
Common mixins and base classes for reducing code duplication.
"""

from django.db import models


class AccessControlMixin:
    """
    Mixin to provide standardized access control functionality.

    This mixin provides a common implementation of the access_qs method
    that can be used across multiple models to reduce code duplication.
    """

    @classmethod
    def access_qs(cls, user, queryset=None):
        """
        Return queryset filtered by user permissions.

        This is a fallback implementation when DAB is not fully available.
        In production, this would implement proper RBAC when DAB is fully configured.

        Args:
            user: The user requesting access
            queryset: Optional base queryset to filter (defaults to all objects)

        Returns:
            QuerySet: Filtered queryset based on user permissions
        """
        if queryset is None:
            queryset = cls.objects.all()

        # For now, return all objects - in production this would implement proper RBAC
        # When DAB is fully configured, this method would be provided by the DAB base class
        return queryset


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

    def mark_started(self):
        """
        Mark the process as started with current timestamp.

        Returns:
            None
        """
        from django.utils import timezone

        self.started_at = timezone.now()
        self.save(update_fields=["started_at"])

    def mark_completed(self, error_message=""):
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

    def get_duration(self):
        """
        Calculate the duration of the process in seconds.

        Returns:
            float: Duration in seconds, or None if not completed
        """
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class UserRelatedMixin(models.Model):
    """
    Abstract mixin for models that have user and admin relationships.

    This mixin provides common user/admin relationship fields that can be
    used across Organization, Team, and similar models.
    """

    users = models.ManyToManyField("User", blank=True, help_text="Users associated with this object")

    admins = models.ManyToManyField("User", blank=True, help_text="Administrators of this object")

    class Meta:
        abstract = True

    def get_users_count(self):
        """
        Get the count of users associated with this object.

        Returns:
            int: Number of users
        """
        return self.users.count()

    def get_admins_count(self):
        """
        Get the count of admins associated with this object.

        Returns:
            int: Number of admins
        """
        return self.admins.count()

    def add_user(self, user):
        """
        Add a user to this object.

        Args:
            user: User instance to add

        Returns:
            None
        """
        self.users.add(user)

    def remove_user(self, user):
        """
        Remove a user from this object.

        Args:
            user: User instance to remove

        Returns:
            None
        """
        self.users.remove(user)

    def add_admin(self, user):
        """
        Add an admin to this object.

        Args:
            user: User instance to add as admin

        Returns:
            None
        """
        self.admins.add(user)

    def remove_admin(self, user):
        """
        Remove an admin from this object.

        Args:
            user: User instance to remove as admin

        Returns:
            None
        """
        self.admins.remove(user)
