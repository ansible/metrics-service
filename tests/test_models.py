"""
Test models that don't require DAB dependencies.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class CommonModel(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class NamedCommonModel(CommonModel):
    name = models.CharField(max_length=512)
    description = models.TextField(blank=True, default="")

    class Meta:
        abstract = True


class AuditableModel(models.Model):
    class Meta:
        abstract = True


class User(AbstractUser, CommonModel, AuditableModel):
    """Test User model without DAB dependencies."""

    class Meta:
        app_label = "tests"


class Organization(NamedCommonModel):
    """Test Organization model without DAB dependencies."""

    users = models.ManyToManyField(
        User,
        related_name="member_of_organizations",
        blank=True,
    )

    admins = models.ManyToManyField(
        User,
        related_name="admin_of_organizations",
        blank=True,
    )

    class Meta:
        app_label = "tests"


class Team(NamedCommonModel):
    """Test Team model without DAB dependencies."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    users = models.ManyToManyField(User, related_name="teams", blank=True)
    admins = models.ManyToManyField(User, related_name="teams_administered", blank=True)

    class Meta:
        app_label = "tests"


class Task(NamedCommonModel, AuditableModel):
    """Test Task model for testing the task system."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("waiting_for_dependencies", "Waiting for Dependencies"),
    ]

    PRIORITY_CHOICES = [
        (1, "Low"),
        (2, "Normal"),
        (3, "High"),
        (4, "Critical"),
    ]

    function_name = models.CharField(max_length=255)
    task_data = models.JSONField(default=dict)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    cron_expression = models.CharField(max_length=100, null=True, blank=True)
    is_recurring = models.BooleanField(default=False)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="pending")
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=2)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    timeout_seconds = models.PositiveIntegerField(default=3600)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    result_data = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        app_label = "tests"

    def is_ready_to_run(self):
        """Check if task is ready to be executed."""
        from django.utils import timezone

        if self.status != "pending":
            return False

        # Check if dependencies are completed
        if self.dependencies.filter(
            prerequisite_task__status__in=["pending", "running", "waiting_for_dependencies"]
        ).exists():
            return False

        # Check if scheduled time has passed
        return not (self.scheduled_time and self.scheduled_time > timezone.now())

    def can_retry(self):
        """Check if task can be retried."""
        return self.attempts < self.max_attempts and self.status == "failed"


class TaskDependency(CommonModel):
    """Test TaskDependency model."""

    dependent_task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="dependencies")
    prerequisite_task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="dependents")
    required_status = models.CharField(max_length=30, choices=Task.STATUS_CHOICES, default="completed")

    class Meta:
        app_label = "tests"
        unique_together = ["dependent_task", "prerequisite_task"]
