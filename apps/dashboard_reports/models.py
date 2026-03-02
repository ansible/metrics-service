import decimal
import logging

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction

# Import base classes, handling both DAB and simple fallbacks
try:
    from ansible_base.lib.abstract_models import CommonModel

    DAB_AVAILABLE = True
except ImportError:
    # Provide simple alternative when DAB is not available
    DAB_AVAILABLE = False

    class CommonModel(models.Model):
        created = models.DateTimeField(auto_now_add=True)
        modified = models.DateTimeField(auto_now=True)

        class Meta:
            abstract = True


logger = logging.getLogger(__name__)


@transaction.atomic
class SubscriptionCostObjectManager(models.Manager):
    def create(self, **kwargs):
        """
        Override create to ensure only one SubscriptionCost instance exists.
        If an instance already exists, update it instead of creating a new one.
        """
        instance, _ = self.update_or_create(pk=1, defaults=kwargs)
        return instance


class SubscriptionCost(CommonModel):
    """
    Stores subscription cost information for the AAP subscription, including monthly cost and average engineer hourly rate.
    This is used for cost calculations in the dashboard reports.

    There should typically only be one record in this table, which can be updated as needed when subscription costs change.
    """

    monthly_subscription_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(decimal.Decimal("0.00"))],
        help_text="Monthly subscription cost for AAP subscription",
    )

    engineer_avg_hourly_rate = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(decimal.Decimal("0.00"))],
        help_text="Average hourly rate for engineers performing manual tasks (used for cost calculations in reports)",
    )

    include_template_creation_time_in_costs = models.BooleanField(
        default=True,
        help_text="Include template creation time in cost calculations. If false, costs related to template creation time will be excluded.",
    )

    class Meta:
        db_table = "dashboard_subscription_cost"
        verbose_name = "Subscription Cost"
        verbose_name_plural = "Subscription Costs"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pk=1),
                name="dashboard_subscription_cost_singleton_pk",
            ),
        ]

    objects = SubscriptionCostObjectManager()

    def __str__(self):
        return f"SubscriptionCost: Monthly={self.monthly_subscription_cost}, Engineer Hourly Rate={self.engineer_avg_hourly_rate}"

    @classmethod
    def get(cls):
        """
        Returns the single SubscriptionCost instance, or creates a default one if it doesn't exist.
        """

        # TODO - In the future,
        #  we may want to pull these default values from settings
        instance, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                "monthly_subscription_cost": decimal.Decimal(5000.00),
                "engineer_avg_hourly_rate": decimal.Decimal(60.00),
                "include_template_creation_time_in_costs": True,
            },
        )
        if created:
            logger.info("Created default SubscriptionCost instance with default values.")
        return instance


class FilterSet(CommonModel):
    """
    Saved filter configurations (saved views) for dashboard filtering.

    Allows users to save commonly-used filter combinations for quick access.
    Users can have multiple filter sets, but only one can be marked as default.

    Example:
        filter_set = FilterSet.objects.create(
            name="Last 30 days - Production",
            filters={'organizations': [1, 2], 'date_range': 'last_30_days'}
        )
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="filter_sets",
        help_text="User who created this filter set",
    )

    name = models.CharField(
        max_length=255, db_index=True, help_text='Display name for this filter set (e.g. "Last 30 days")'
    )

    filters = models.JSONField(
        help_text="Filter configuration: {organizations: [], projects: [], labels: [], date_range: {}}"
    )

    is_default = models.BooleanField(
        default=False, help_text="Whether this is the user's default filter set (only one allowed per user)"
    )

    class Meta:
        db_table = "dashboard_filter_set"
        verbose_name = "Filter Set"
        verbose_name_plural = "Filter Sets"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["user", "is_default"], name="dashboard_fs_user_default_idx"),
            models.Index(fields=["user", "-modified"], name="dashboard_fs_user_mod_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "is_default"],
                condition=models.Q(is_default=True),
                name="one_default_per_user",
                violation_error_message="User can only have one default filter set",
            )
        ]

    def __str__(self):
        return self.name


class TemplateMetadata(CommonModel):
    """
    Stores metadata for AWX job templates, including name, description, and time estimates.
    Used for reporting and cost calculations.
    """

    template_id = models.IntegerField(
        unique=True,
        db_index=True,
        help_text="AWX job template ID (from AWX database main_jobtemplate table)",
    )

    template_name = models.CharField(max_length=512, db_index=True, help_text="Template name for display (from AWX)")

    time_taken_manually_execute_minutes = models.BigIntegerField(
        null=True, blank=True, help_text="User override: Estimated time to perform this task manually (minutes)"
    )

    time_taken_create_automation_minutes = models.BigIntegerField(
        null=True, blank=True, help_text="User override: Estimated time spent creating this automation (minutes)"
    )

    class Meta:
        db_table = "dashboard_template_metadata"
        ordering = ["template_name"]
        verbose_name = "Template Metadata"
        verbose_name_plural = "Template Metadata"

    def __str__(self):
        """Return string representation of the template metadata."""
        return f"Metadata for {self.template_name} (ID: {self.template_id})"


class JobStatusChoices(models.TextChoices):
    NEW = "new", "New"
    PENDING = "pending", "Pending"
    WAITING = "waiting", "Waiting"
    RUNNING = "running", "Running"
    SUCCESSFUL = "successful", "Successful"
    FAILED = "failed", "Failed"
    ERROR = "error", "Error"
    CANCELED = "canceled", "Canceled"


class JobData(CommonModel):
    """
    Stores AWX job execution data for reporting, including status, timing, host counts, and related template/project/org info.
    """

    job_id = models.IntegerField(
        unique=True,
        db_index=True,
        help_text="AWX job ID (from AWX database main_unifiedjob table)",
    )

    template_name = models.CharField(max_length=512, help_text="Job template name (from AWX)")

    template_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="AWX template ID",
    )

    project_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="AWX project ID",
    )

    project_name = models.CharField(
        max_length=512, null=True, blank=True, help_text="Project name for display (from AWX)"
    )

    organization_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="AWX organization ID",
    )

    status = models.CharField(
        choices=JobStatusChoices.choices, default=JobStatusChoices.SUCCESSFUL, max_length=25, db_index=True
    )

    started = models.DateTimeField(
        null=True,
        default=None,
        help_text="Job start timestamp (from AWX database main_unifiedjob table)",
    )
    finished = models.DateTimeField(
        null=True,
        default=None,
        db_index=True,
        help_text="Job finish timestamp (from AWX database main_unifiedjob table)",
    )
    elapsed = models.DecimalField(
        max_digits=15,
        decimal_places=3,
        help_text="Job elapsed time in seconds (from AWX database main_unifiedjob table)",
    )

    num_hosts = models.PositiveIntegerField(
        default=0, help_text="Number of hosts involved in the job (calculated from AWX job host summaries)"
    )

    launched_by_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="AWX user ID of the user who launched the job (from AWX database main_unifiedjob table)",
    )

    launched_by_username = models.CharField(
        max_length=512,
        null=True,
        blank=True,
        help_text="AWX username of the user who launched the job (from AWX database main_unifiedjob table)",
    )

    template_metadata = models.ForeignKey(
        TemplateMetadata,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jobs",
        help_text="Reference to TemplateMetadata for this job's template",
    )

    awx_created = models.DateTimeField(help_text="Creation timestamp from AWX", null=True, blank=True)
    awx_modified = models.DateTimeField(help_text="Modification timestamp from AWX", null=True, blank=True)

    class Meta:
        db_table = "dashboard_job_data"
        ordering = ["-started"]
        verbose_name = "Job Data"
        verbose_name_plural = "Jobs Data"
        indexes = [
            models.Index(fields=["template_id"], name="dashboard_jd_template_idx"),
            models.Index(fields=["project_id"], name="dashboard_jd_project_idx"),
            models.Index(fields=["organization_id"], name="dashboard_jd_organization_idx"),
        ]

    def __str__(self):
        return f"Job {self.job_id} - Template: {self.template_name} - Status: {self.status}"


class JobLabel(CommonModel):
    """
    Stores label associations for a JobData instance (AWX job).
    Using for filtering and reporting based on AWX labels.
    """

    job_data = models.ForeignKey(JobData, on_delete=models.CASCADE, related_name="labels")
    label_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="AWX label ID",
    )

    class Meta:
        db_table = "dashboard_job_data_label"
        verbose_name = "Job Data Label"
        verbose_name_plural = "Job Data Labels"
        indexes = [
            models.Index(fields=["job_data", "label_id"], name="dashboard_jl_job_label_idx"),
        ]

    def __str__(self):
        return f"{self.job_data.template_name}: {self.label_id}"


class JobHostSummary(CommonModel):
    """
    Stores host summary statistics for a JobData instance (AWX job).
    Used for host-level reporting and unique host counts.
    """

    job_data = models.ForeignKey(JobData, on_delete=models.CASCADE, related_name="host_summaries")
    host_summary_id = models.IntegerField(
        unique=True,
        null=True,
        blank=True,
        help_text="AWX host summary ID (from AWX database main_hostsummary table)",
    )
    host_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="AWX host ID (from AWX database main_host table)",
    )

    host_name = models.TextField(max_length=512, db_index=True, help_text="Host name for display (from AWX)")

    class Meta:
        db_table = "dashboard_job_data_host_summary"
        verbose_name = "Job Data Host Summary"
        verbose_name_plural = "Job Data Host Summaries"
        indexes = [
            models.Index(fields=["job_data", "host_id"], name="dashboard_jhs_job_host_idx"),
        ]

    def __str__(self):
        return f"{self.host_name}: {self.job_data.template_name}"
