"""
Task models for metrics_service.

This module contains all task-related models including task definitions,
executions, dependencies, and task chains for workflow management.
"""

from datetime import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone

# Import base classes and mixins from core
from apps.core.mixins import AccessControlMixin, StatusTrackingMixin

# Import base classes, handling both DAB and simple fallbacks
try:
    from ansible_base.activitystream.models import AuditableModel
    from ansible_base.lib.abstract_models import CommonModel, NamedCommonModel

    DAB_AVAILABLE = True
except ImportError:
    # Provide simple alternatives for immediate setup
    DAB_AVAILABLE = False

    # Simple base classes when DAB is not available
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


class Task(NamedCommonModel, AuditableModel, AccessControlMixin, StatusTrackingMixin):
    """
    Database model for scheduled tasks with enhanced tracking capabilities.

    This model provides comprehensive task scheduling and execution tracking
    with support for dependencies, recurring tasks, and detailed status monitoring.
    """

    class Meta:
        app_label = "tasks"
        ordering = ["id"]
        permissions = [("can_execute_task", "Can execute task")]

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

    # Task identification and metadata
    description = models.TextField(blank=True, default="", help_text="Task description")

    function_name = models.CharField(
        max_length=255, help_text="Name of the function to execute (must match TASK_FUNCTIONS)"
    )

    task_data = models.JSONField(default=dict, help_text="JSON data to pass to the task function")

    # Scheduling information
    scheduled_time = models.DateTimeField(
        null=True, blank=True, help_text="When the task should be executed (null for immediate execution)"
    )

    cron_expression = models.CharField(
        max_length=100, null=True, blank=True, help_text="Cron expression for recurring tasks (e.g., '0 2 * * *')"
    )

    is_recurring = models.BooleanField(
        default=False, help_text="Whether this task should repeat based on cron_expression"
    )

    is_system_task = models.BooleanField(
        default=False, help_text="Whether this is a system-defined task that cannot be easily deleted"
    )

    # Execution tracking
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="pending")

    priority = models.IntegerField(
        choices=PRIORITY_CHOICES, default=2, help_text="Task priority (higher numbers = higher priority)"
    )

    attempts = models.PositiveIntegerField(default=0, help_text="Number of execution attempts")

    max_attempts = models.PositiveIntegerField(default=3, help_text="Maximum number of retry attempts")

    timeout_seconds = models.PositiveIntegerField(default=3600, help_text="Task timeout in seconds")

    # Execution results (inherited from StatusTrackingMixin)
    result_data = models.JSONField(default=dict, blank=True, help_text="JSON result data from task execution")

    # Ownership and organization
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tasks",
        help_text="User who created this task",
    )

    def __str__(self):
        """
        Return string representation of the task.

        Returns:
            str: Task name, function name, and status
        """
        return f"{self.name} ({self.function_name}) - {self.get_status_display()}"

    def is_ready_to_run(self) -> bool:
        """
        Check if task is ready to be executed.

        Returns:
            bool: True if task is ready to run, False otherwise
        """
        if self.status != "pending":
            return False

        # Check if dependencies are completed
        if self.dependencies.filter(
            prerequisite_task__status__in=["pending", "running", "waiting_for_dependencies"]
        ).exists():
            return False

        # Check if scheduled time has passed
        return not (self.scheduled_time and self.scheduled_time > timezone.now())

    def can_retry(self) -> bool:
        """
        Check if task can be retried.

        Returns:
            bool: True if task can be retried, False otherwise
        """
        return self.attempts < self.max_attempts and self.status == "failed"

    def retry(self) -> bool:
        """
        Retry a failed task by resetting its status to pending.

        Returns:
            bool: True if task was successfully reset for retry, False otherwise
        """
        if not self.can_retry():
            return False

        self.status = "pending"
        self.error_message = ""
        self.started_at = None
        self.completed_at = None
        self.save()
        return True

    def can_delete(self) -> bool:
        """
        Check if task can be deleted.

        System tasks cannot be easily deleted to protect critical functionality.

        Returns:
            bool: True if task can be deleted, False if it's protected
        """
        return not self.is_system_task

    def can_modify(self) -> bool:
        """
        Check if task can be modified.

        System tasks have limited modification capabilities to prevent
        breaking critical system functionality.

        Returns:
            bool: True if task can be fully modified, False if restricted
        """
        return not self.is_system_task

    def get_next_run_time(self) -> datetime | None:
        """
        Calculate next run time for recurring tasks.

        Returns:
            datetime or None: Next run time for recurring tasks, None if not recurring
        """
        if not self.is_recurring or not self.cron_expression:
            return None

        try:
            from datetime import datetime

            from croniter import croniter

            cron = croniter(self.cron_expression, timezone.now())
            return cron.get_next(datetime)
        except ImportError:
            # croniter not available, return None
            return None
        except Exception:
            # Invalid cron expression
            return None


class TaskDependency(CommonModel):
    """
    Model to define task dependencies for chaining.

    This model allows creating dependencies between tasks to ensure
    proper execution order in complex workflows.
    """

    class Meta:
        app_label = "tasks"
        unique_together = ["dependent_task", "prerequisite_task"]
        verbose_name_plural = "Task Dependencies"

    dependent_task = models.ForeignKey(
        Task, on_delete=models.CASCADE, related_name="dependencies", help_text="Task that depends on another task"
    )

    prerequisite_task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="dependents",
        help_text="Task that must complete before dependent_task can run",
    )

    required_status = models.CharField(
        max_length=30,
        choices=Task.STATUS_CHOICES,
        default="completed",
        help_text="Required status of prerequisite task",
    )

    def __str__(self):
        """
        Return string representation of the task dependency.

        Returns:
            str: Dependency relationship description
        """
        return f"{self.dependent_task.name} depends on {self.prerequisite_task.name}"


class TaskExecution(CommonModel, AuditableModel):
    """
    Model to track individual task executions for history and debugging.

    This model provides detailed tracking of task execution attempts,
    including timing, results, and error information.
    """

    class Meta:
        app_label = "tasks"
        ordering = ["-started_at"]

    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, related_name="executions", help_text="The task that was executed"
    )

    status = models.CharField(max_length=30, choices=Task.STATUS_CHOICES)

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    worker_id = models.CharField(
        max_length=100, null=True, blank=True, help_text="ID of the worker that executed the task"
    )

    result_data = models.JSONField(default=dict, blank=True, help_text="JSON result data from this execution")

    error_message = models.TextField(blank=True, help_text="Error message if execution failed")

    execution_time_seconds = models.FloatField(
        null=True, blank=True, help_text="Time taken to execute the task in seconds"
    )

    def __str__(self):
        """
        Return string representation of the task execution.

        Returns:
            str: Task name and execution timestamp
        """
        return f"{self.task.name} execution at {self.started_at}"

    def save(self, *args, **kwargs):
        """
        Override save to calculate execution time automatically.

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            None
        """
        # Calculate execution time if completed
        if self.completed_at and self.started_at:
            self.execution_time_seconds = (self.completed_at - self.started_at).total_seconds()
        super().save(*args, **kwargs)


class TaskChain(NamedCommonModel, AuditableModel, AccessControlMixin):
    """
    Model to define named task chains for complex workflows.

    This model allows grouping tasks into ordered chains for executing
    complex workflows with specific sequencing requirements.
    """

    class Meta:
        app_label = "tasks"
        ordering = ["id"]

    tasks = models.ManyToManyField(
        Task, through="TaskChainMembership", related_name="chains", help_text="Tasks in this chain"
    )

    is_active = models.BooleanField(default=True, help_text="Whether this chain is active")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_chains"
    )

    def __str__(self):
        """
        Return string representation of the task chain.

        Returns:
            str: Task chain name
        """
        return self.name


class TaskChainMembership(CommonModel):
    """
    Through model for TaskChain to Task relationship with ordering.

    This model defines the order and relationship between tasks within
    a task chain, allowing for proper sequencing of workflow execution.
    """

    class Meta:
        app_label = "tasks"
        unique_together = ["chain", "task"]
        ordering = ["order"]

    chain = models.ForeignKey(TaskChain, on_delete=models.CASCADE)
    task = models.ForeignKey(Task, on_delete=models.CASCADE)

    order = models.PositiveIntegerField(help_text="Order of task in the chain (lower numbers run first)")

    def __str__(self):
        """
        Return string representation of the task chain membership.

        Returns:
            str: Chain name, task name, and order
        """
        return f"{self.chain.name} - {self.task.name} (order: {self.order})"
