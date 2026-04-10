import calendar
import decimal
import logging
from datetime import datetime
from typing import Any, Self

import pytz
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from metrics_utility.library.collectors.dashboard import AWXJobType

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
DEFAULT_TIME_TAKEN_TO_CREATE_AUTOMATION_MINUTES = 60


def _month_range_iter(start_date, end_date):
    """
    Helper generator to iterate over each (year, month) tuple between start_date and end_date (inclusive).
    Advances month and year correctly, handling year rollover.
    """
    year, month = start_date.year, start_date.month
    while (year < end_date.year) or (year == end_date.year and month <= end_date.month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def _get_month_overlap_days(current_year, current_month, start_date, end_date):
    """
    Helper function to calculate the number of days in a month and the actual overlap range
    for a given start_date and end_date. Returns (month_days, month_start_day, month_end_day).
    """
    month_days = calendar.monthrange(current_year, current_month)[1]
    month_start_day = start_date.day if (current_year == start_date.year and current_month == start_date.month) else 1
    month_end_day = end_date.day if (current_year == end_date.year and current_month == end_date.month) else month_days
    return month_days, month_start_day, month_end_day


class SubscriptionCostObjectManager(models.Manager):
    @transaction.atomic
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

    def __str__(self) -> str:
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
                "monthly_subscription_cost": decimal.Decimal("5000.00"),
                "engineer_avg_hourly_rate": decimal.Decimal("60.00"),
                "include_template_creation_time_in_costs": True,
            },
        )
        if created:
            logger.info("Created default SubscriptionCost instance with default values.")
        return instance

    @property
    def cost_employee_per_minute(self) -> decimal.Decimal:
        """
        Calculate and return the cost of employee time per minute based on the average hourly rate.
        Ensures engineer_avg_hourly_rate is always a decimal.Decimal.
        """
        return decimal.Decimal(str(self.engineer_avg_hourly_rate)) / decimal.Decimal(60)

    def daily_subscription_cost(self, start: datetime | None = None, end: datetime | None = None) -> decimal.Decimal:
        """
        Calculate and return the daily subscription cost based on the monthly subscription cost.
        Assumes 30 days in a month for calculation.
        """
        now = datetime.now(pytz.utc)
        default_days_in_month = calendar.monthrange(now.year, now.month)[1]
        monthly_cost = decimal.Decimal(str(self.monthly_subscription_cost))
        default_daily_cost = monthly_cost / decimal.Decimal(default_days_in_month)

        if start is None or end is None:
            return default_daily_cost

        if start > end:
            start, end = end, start

        if start.year == end.year and start.month == end.month:
            days_in_month = calendar.monthrange(start.year, start.month)[1]
            return monthly_cost / decimal.Decimal(days_in_month)

        total_days = 0
        total_cost = decimal.Decimal(0)
        for current_year, current_month in _month_range_iter(start, end):
            month_days, month_start_day, month_end_day = _get_month_overlap_days(
                current_year, current_month, start, end
            )
            overlap_days = month_end_day - month_start_day + 1
            if overlap_days <= 0:
                continue
            proportional_cost = monthly_cost * decimal.Decimal(overlap_days) / decimal.Decimal(month_days)
            total_days += overlap_days
            total_cost += proportional_cost
        return total_cost / decimal.Decimal(total_days) if total_days > 0 else default_daily_cost

    def per_second_subscription_cost(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> decimal.Decimal:
        """
        Calculate and return the per-second subscription cost based on the daily subscription cost.
        """
        daily_cost = self.daily_subscription_cost(start=start, end=end)
        return daily_cost / decimal.Decimal(86400)  # 86400 seconds in a day


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

    def __str__(self) -> str:
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

    def __str__(self) -> str:
        """Return string representation of the template metadata."""
        return f"Metadata for {self.template_name} (ID: {self.template_id})"

    @classmethod
    def get_min_awx_id(cls) -> int:
        """
        Returns a negative integer for new AWX template IDs if none exist,
        otherwise returns the minimum existing template_id minus one.
        """
        min_id = cls.objects.aggregate(models.Min("template_id")).get("template_id__min", None)
        return min_id - 1 if min_id is not None and min_id < 0 else -1

    @classmethod
    def get_by_awx_id_or_name(cls, name: str, awx_id: int | None = None, elapsed: decimal.Decimal | None = None):
        """
        Retrieves TemplateMetadata by AWX ID or name. If not found, creates a new instance.
        Sets default manual and automation time estimates if not present.
        """
        instance = None

        if awx_id is not None:
            try:
                instance = cls.objects.get(template_id=awx_id)
            except cls.DoesNotExist:
                instance = None

        if instance is None:
            try:
                instance = cls.objects.get(template_name=name)
                # If the record was created with a synthetic negative placeholder ID and we
                # now have the real AWX ID, promote it so later ID-based lookups work correctly.
                if awx_id is not None and instance.template_id < 0:
                    instance.template_id = awx_id
                    instance.save(update_fields=["template_id"])
            except cls.DoesNotExist:
                instance = cls.objects.create(
                    template_name=name,
                    template_id=awx_id if awx_id is not None else cls.get_min_awx_id(),
                )
                logger.info(f"Created new TemplateMetadata '{instance}' from AWX data.")

        update_fields = []

        if elapsed is not None and instance.time_taken_manually_execute_minutes is None:
            # If we have elapsed time from AWX and no manual override, set a default estimate based on elapsed time
            # Default: 2x the elapsed time, with a minimum of 30 minutes
            estimated_manual_time = max(
                int(decimal.Decimal(elapsed / 60 * 2).quantize(decimal.Decimal(1), rounding=decimal.ROUND_UP)), 30
            )
            estimated_manual_time = min(
                estimated_manual_time, 1000000
            )  # Cap at a reasonable maximum to avoid overflow issues
            instance.time_taken_manually_execute_minutes = estimated_manual_time
            update_fields.append("time_taken_manually_execute_minutes")
            logger.debug(
                f"Set default manual execution time for TemplateMetadata '{instance}' to {estimated_manual_time} minutes based on elapsed time."
            )

        if instance.time_taken_create_automation_minutes is None:
            instance.time_taken_create_automation_minutes = DEFAULT_TIME_TAKEN_TO_CREATE_AUTOMATION_MINUTES
            update_fields.append("time_taken_create_automation_minutes")
            logger.debug(
                f"Set default automation creation time for TemplateMetadata '{instance}' to {DEFAULT_TIME_TAKEN_TO_CREATE_AUTOMATION_MINUTES} minutes."
            )

        if update_fields:
            instance.save(update_fields=update_fields)

        return instance


class JobStatusChoices(models.TextChoices):
    NEW = "new", "New"
    PENDING = "pending", "Pending"
    WAITING = "waiting", "Waiting"
    RUNNING = "running", "Running"
    SUCCESSFUL = "successful", "Successful"
    FAILED = "failed", "Failed"
    ERROR = "error", "Error"
    CANCELED = "canceled", "Canceled"


class JobDataFilterMethods:
    def before_date(self, dt: datetime | None) -> Self:
        if dt is not None:
            return self.filter(finished__lte=dt)
        return self

    def after_date(self, dt: datetime | None) -> Self:
        if dt is not None:
            return self.filter(finished__gte=dt)
        return self

    def organizations(self, ids: list[int] | None) -> Self:
        if ids:
            return self.filter(organization_id__in=ids)
        return self

    def templates(self, ids: list[int] | None) -> Self:
        if ids:
            return self.filter(template_id__in=ids)
        return self

    def projects(self, ids: list[int] | None) -> Self:
        if ids:
            return self.filter(project_id__in=ids)
        return self

    def labels(self, ids: list[int] | None) -> Self:
        if ids:
            labels_qs = JobLabel.objects.filter(label_id__in=ids).values_list("job_data_id", flat=True)
            return self.filter(id__in=labels_qs)
        return self


class JobDataQuerySet(JobDataFilterMethods, models.QuerySet):
    pass


class JobDataManager(JobDataFilterMethods, models.Manager):
    def get_queryset(self) -> JobDataQuerySet:
        return JobDataQuerySet(self.model, using=self._db)


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

    objects = JobDataManager()

    def __str__(self) -> str:
        return f"Job {self.job_id} - Template: {self.template_name} - Status: {self.status}"

    @classmethod
    def last_timestamp(cls) -> datetime | None:
        """Returns the latest 'awx_modified' timestamp from JobData, or None if no records exist."""
        latest_awx_modified = cls.objects.filter(awx_modified__isnull=False).aggregate(models.Max("awx_modified"))[
            "awx_modified__max"
        ]
        return latest_awx_modified

    @classmethod
    @transaction.atomic
    def create_or_update_from_awx(cls, awx_job: AWXJobType):
        """
        Creates or updates a JobData instance from AWX job, label, and host summary data.
        Updates related JobLabel and JobHostSummary records.
        """
        template_metadata = TemplateMetadata.get_by_awx_id_or_name(
            name=awx_job["name"], awx_id=awx_job["unified_job_template_id"], elapsed=awx_job["elapsed"]
        )
        labels = awx_job.get("labels", [])
        host_summaries = awx_job.get("host_summaries", [])

        model, created = cls.objects.update_or_create(
            job_id=awx_job["id"],
            defaults={
                "template_name": awx_job["name"],
                "template_id": awx_job["unified_job_template_id"],
                "project_id": awx_job["project_id"],
                "project_name": awx_job["project_name"],
                "organization_id": awx_job["organization_id"],
                "status": awx_job["status"],
                "started": awx_job["started"],
                "finished": awx_job["finished"],
                "elapsed": awx_job["elapsed"],
                "launched_by_id": awx_job["launched_by_id"],
                "launched_by_username": awx_job["launched_by_username"],
                "template_metadata": template_metadata,
                "awx_created": awx_job["created"],
                "awx_modified": awx_job["modified"],
                "num_hosts": awx_job["num_hosts"],
            },
        )

        if created:
            logger.info(f"Created new JobData {model.__str__()}")
            labels_dict = {}
            host_summaries_dict = {}
        else:
            labels_dict = {label_obj.label_id: label_obj for label_obj in JobLabel.objects.filter(job_data=model).all()}
            host_summaries_dict = {
                host_summary_obj.host_summary_id: host_summary_obj
                for host_summary_obj in JobHostSummary.objects.filter(job_data=model).all()
            }
            logger.info(f"Updated JobData {model.__str__()}")

        # Update JobLabel records for this job:
        # - Labels from AWX not in existing records are created
        # - Labels from AWX matching existing records are kept
        # - Existing records no longer in AWX labels are deleted
        if labels:
            labels_for_create = []
            for label_id in labels:
                label_obj = labels_dict.pop(label_id, None)
                if label_obj is None:
                    labels_for_create.append(JobLabel(job_data=model, label_id=label_id))
            if labels_for_create:
                JobLabel.objects.bulk_create(labels_for_create)
                logger.info(f"Created {len(labels_for_create)} new JobLabel records for JobData {model.__str__()}")
        if labels_dict:
            stale_label_pks = [o.pk for o in labels_dict.values()]
            deleted_count, _ = JobLabel.objects.filter(pk__in=stale_label_pks).delete()
            logger.info(f"Deleted {deleted_count} stale JobLabel records for JobData {model.__str__()}")

        # Update JobHostSummary records for this job:
        # - Host summaries from AWX not in existing records are created
        # - Host summaries from AWX matching existing records are updated
        # - Existing records no longer in AWX host summaries are deleted
        if host_summaries:
            host_summaries_for_create = []
            for awx_host_summary in host_summaries:
                host_summary_model = host_summaries_dict.pop(awx_host_summary["id"], None)
                if host_summary_model is not None:
                    host_summary_model.host_id = awx_host_summary["host_id"]
                    host_summary_model.host_name = awx_host_summary["host_name"]
                    host_summary_model.save()
                    logger.info(
                        f"Updated JobHostSummary for host '{host_summary_model.host_name}' (ID: {host_summary_model.host_id}) in JobData {model.__str__()}"
                    )
                else:
                    host_summaries_for_create.append(
                        JobHostSummary(
                            job_data=model,
                            host_id=awx_host_summary["host_id"],
                            host_name=awx_host_summary["host_name"],
                            host_summary_id=awx_host_summary["id"],
                        )
                    )
            if host_summaries_for_create:
                JobHostSummary.objects.bulk_create(host_summaries_for_create)
                logger.info(
                    f"Created {len(host_summaries_for_create)} new JobHostSummary records for JobData {model.__str__()}"
                )
        if host_summaries_dict:
            stale_summary_pks = [o.pk for o in host_summaries_dict.values()]
            deleted_count, _ = JobHostSummary.objects.filter(pk__in=stale_summary_pks).delete()
            logger.info(f"Deleted {deleted_count} stale JobHostSummary records for JobData {model.__str__()}")


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

    def __str__(self) -> str:
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

    host_name = models.CharField(max_length=512, db_index=True, help_text="Host name for display (from AWX)")

    class Meta:
        db_table = "dashboard_job_data_host_summary"
        verbose_name = "Job Data Host Summary"
        verbose_name_plural = "Job Data Host Summaries"
        indexes = [
            models.Index(fields=["job_data", "host_id"], name="dashboard_jhs_job_host_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.host_name}: {self.job_data.template_name}"

    @classmethod
    def unique_count(
        cls, start: datetime | None = None, end: datetime | None = None, options: dict[str, Any] | None = None
    ) -> int:
        """
        Returns the count of unique hosts across all JobData records.
        Filters by finished date range and additional options
        (organization, project, template, label) if provided in the options dict.
        """
        options = options or {}
        queryset = cls.objects

        # Apply date range filters
        if start is not None:
            queryset = queryset.filter(job_data__finished__gte=start)
        if end is not None:
            queryset = queryset.filter(job_data__finished__lte=end)

        # Mapping of option keys to their corresponding filter field
        filter_mapping = {
            "organization": "job_data__organization_id__in",
            "project": "job_data__project_id__in",
            "template": "job_data__template_id__in",
        }

        # Apply filters from options using the mapping
        for option_key, filter_field in filter_mapping.items():
            values = options.get(option_key)
            if values:
                queryset = queryset.filter(**{filter_field: values})

        # Handle labels separately (requires subquery)
        labels = options.get("label")
        if labels:
            labels_qs = JobLabel.objects.filter(label_id__in=labels).values_list("job_data_id", flat=True)
            queryset = queryset.filter(job_data_id__in=labels_qs)

        return queryset.values("host_name").distinct().count()
