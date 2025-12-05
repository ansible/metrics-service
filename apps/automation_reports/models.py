"""
Automation Reports Data Models

Simplified models based on ansible/automation-reports for storing AWX/Controller job data.
Data is collected directly from the source database via SQL and stored in SQLite.

Key Differences from Original:
- No Cluster model (assumes single source)
- No sync/scheduling logic (collection handled by tasks)
- Optimized for SQLite storage
- Focused on reporting data only
"""

import decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class BaseTimestampModel(models.Model):
    """Base model with automatic timestamp fields."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class JobStatusChoices(models.TextChoices):
    """Job execution status choices."""

    NEW = "new", "New"
    PENDING = "pending", "Pending"
    WAITING = "waiting", "Waiting"
    RUNNING = "running", "Running"
    SUCCESSFUL = "successful", "Successful"
    FAILED = "failed", "Failed"
    ERROR = "error", "Error"
    CANCELED = "canceled", "Canceled"


class JobTypeChoices(models.TextChoices):
    """Job type choices."""

    JOB = "job", "Job"
    PLAYBOOK_RUN = "playbook_run", "Playbook Run"


class JobLaunchTypeChoices(models.TextChoices):
    """Job launch method choices."""

    MANUAL = "manual", "Manual"
    RELAUNCH = "relaunch", "Relaunch"
    CALLBACK = "callback", "Callback"
    SCHEDULED = "scheduled", "Scheduled"
    DEPENDENCY = "dependency", "Dependency"
    WORKFLOW = "workflow", "Workflow"
    WEBHOOK = "webhook", "Webhook"
    SYNC = "sync", "Sync"
    SCM = "scm", "SCM Update"


class JobRunTypeChoices(models.TextChoices):
    """Job run mode choices."""

    RUN = "run", "Run"
    CHECK = "check", "Check"
    SCAN = "scan", "Scan"


# =============================================================================
# Core Entity Models
# =============================================================================


class Organization(BaseTimestampModel):
    """
    Organization from AWX/Controller.

    Maps to main_organization table in AWX database.
    """

    external_id = models.IntegerField(unique=True, db_index=True, help_text="ID from source AWX database")
    name = models.CharField(max_length=255, unique=True, db_index=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "ar_organization"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Inventory(BaseTimestampModel):
    """
    Inventory from AWX/Controller.

    Maps to main_inventory table in AWX database.
    """

    external_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(null=True, blank=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="inventories", null=True, blank=True
    )

    class Meta:
        db_table = "ar_inventory"
        ordering = ["name"]
        unique_together = [["name", "organization"]]

    def __str__(self):
        return self.name


class Project(BaseTimestampModel):
    """
    Project from AWX/Controller.

    Maps to main_project table in AWX database.
    """

    external_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(null=True, blank=True)
    scm_type = models.CharField(max_length=50, null=True, blank=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="projects", null=True, blank=True
    )

    class Meta:
        db_table = "ar_project"
        ordering = ["name"]
        unique_together = [["name", "organization"]]

    def __str__(self):
        return self.name


class JobTemplate(BaseTimestampModel):
    """
    Job Template from AWX/Controller.

    Maps to main_jobtemplate table in AWX database.
    Includes time calculation fields for ROI calculations.
    """

    external_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(null=True, blank=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="job_templates", null=True, blank=True
    )

    # Time calculation fields for ROI
    time_taken_manually_execute_minutes = models.BigIntegerField(
        default=60,  # Default: 1 hour to execute manually
        validators=[MinValueValidator(1), MaxValueValidator(1000000)],
        help_text="Estimated time to execute this task manually (in minutes)",
    )
    time_taken_create_automation_minutes = models.BigIntegerField(
        default=240,  # Default: 4 hours to create automation
        validators=[MinValueValidator(1), MaxValueValidator(1000000)],
        help_text="Estimated time to create the automation (in minutes)",
    )

    class Meta:
        db_table = "ar_job_template"
        ordering = ["name"]
        unique_together = [["name", "organization"]]

    def __str__(self):
        if self.organization:
            return f"{self.organization.name}:{self.name}"
        return self.name


class ExecutionEnvironment(BaseTimestampModel):
    """
    Execution Environment from AWX/Controller.

    Maps to main_executionenvironment table in AWX database.
    """

    external_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    description = models.TextField(null=True, blank=True)
    image = models.CharField(max_length=1024, null=True, blank=True)

    class Meta:
        db_table = "ar_execution_environment"
        ordering = ["name"]

    def __str__(self):
        return self.name


class InstanceGroup(BaseTimestampModel):
    """
    Instance Group from AWX/Controller.

    Maps to main_instancegroup table in AWX database.
    """

    external_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    is_container_group = models.BooleanField(default=False)

    class Meta:
        db_table = "ar_instance_group"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Label(BaseTimestampModel):
    """
    Label from AWX/Controller.

    Maps to main_label table in AWX database.
    """

    external_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="labels", null=True, blank=True
    )

    class Meta:
        db_table = "ar_label"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Host(BaseTimestampModel):
    """
    Host from AWX/Controller.

    Maps to main_host table in AWX database.
    """

    external_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(null=True, blank=True)
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name="hosts", null=True, blank=True)

    class Meta:
        db_table = "ar_host"
        ordering = ["name"]
        unique_together = [["name", "inventory"]]

    def __str__(self):
        return self.name


class AAPUser(BaseTimestampModel):
    """
    User from AWX/Controller.

    Maps to main_user table in AWX database.
    """

    external_id = models.IntegerField(unique=True, db_index=True)
    username = models.CharField(max_length=255, unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    user_type = models.CharField(max_length=20, default="normal")  # normal, system_auditor, system_administrator

    class Meta:
        db_table = "ar_user"
        ordering = ["username"]

    def __str__(self):
        return self.username

    @property
    def full_name(self):
        """Return full name or username."""
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.username


# =============================================================================
# Job Data Models
# =============================================================================


class Job(BaseTimestampModel):
    """
    Job execution record from AWX/Controller.

    Maps to main_job and main_unifiedjob tables in AWX database.
    Contains all job execution details including status, timing, and host counts.
    """

    external_id = models.IntegerField(unique=True, db_index=True, help_text="Job ID from source AWX database")

    # Job type and status
    type = models.CharField(choices=JobTypeChoices.choices, default=JobTypeChoices.JOB, max_length=20)
    job_type = models.CharField(choices=JobRunTypeChoices.choices, default=JobRunTypeChoices.RUN, max_length=20)
    launch_type = models.CharField(
        choices=JobLaunchTypeChoices.choices, default=JobLaunchTypeChoices.MANUAL, max_length=20
    )
    status = models.CharField(
        choices=JobStatusChoices.choices, default=JobStatusChoices.SUCCESSFUL, max_length=25, db_index=True
    )

    # Job identification
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(null=True, blank=True)

    # Foreign keys to related entities
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name="jobs")
    job_template = models.ForeignKey(JobTemplate, on_delete=models.CASCADE, null=True, blank=True, related_name="jobs")
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, null=True, blank=True, related_name="jobs")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name="jobs")
    execution_environment = models.ForeignKey(
        ExecutionEnvironment, on_delete=models.CASCADE, null=True, blank=True, related_name="jobs"
    )
    instance_group = models.ForeignKey(
        InstanceGroup, on_delete=models.CASCADE, null=True, blank=True, related_name="jobs"
    )
    launched_by = models.ForeignKey(
        AAPUser, on_delete=models.CASCADE, null=True, blank=True, related_name="jobs_launched"
    )

    # Timing fields
    started = models.DateTimeField(null=True, blank=True, db_index=True)
    finished = models.DateTimeField(null=True, blank=True, db_index=True)
    elapsed = models.DecimalField(max_digits=15, decimal_places=3, default=decimal.Decimal(0))

    # Status flags
    failed = models.BooleanField(default=False, db_index=True)

    # Original timestamps from AWX
    created = models.DateTimeField(null=True, blank=True)
    modified = models.DateTimeField(null=True, blank=True)

    # Host counts
    num_hosts = models.IntegerField(default=0, help_text="Total hosts targeted")
    changed_hosts_count = models.IntegerField(default=0)
    dark_hosts_count = models.IntegerField(default=0)
    failures_hosts_count = models.IntegerField(default=0)
    ok_hosts_count = models.IntegerField(default=0)
    processed_hosts_count = models.IntegerField(default=0)
    skipped_hosts_count = models.IntegerField(default=0)
    failed_hosts_count = models.IntegerField(default=0)
    ignored_hosts_count = models.IntegerField(default=0)
    rescued_hosts_count = models.IntegerField(default=0)

    class Meta:
        db_table = "ar_job"
        ordering = ["-finished"]
        indexes = [
            models.Index(fields=["status", "finished"]),
            models.Index(fields=["job_template", "finished"]),
            models.Index(fields=["organization", "finished"]),
            models.Index(fields=["started"]),
        ]

    def __str__(self):
        return f"Job {self.external_id}: {self.name} ({self.status})"

    @property
    def is_successful(self):
        """Return True if job was successful."""
        return self.status == JobStatusChoices.SUCCESSFUL

    @property
    def is_failed(self):
        """Return True if job failed."""
        return self.status in [JobStatusChoices.FAILED, JobStatusChoices.ERROR]

    @property
    def duration_minutes(self):
        """Return job duration in minutes."""
        if self.elapsed:
            return float(self.elapsed) / 60.0
        return 0.0


class JobLabel(BaseTimestampModel):
    """
    Many-to-many relationship between Jobs and Labels.

    Maps to main_job_labels table in AWX database.
    """

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="labels")
    label = models.ForeignKey(Label, on_delete=models.CASCADE, related_name="jobs")

    class Meta:
        db_table = "ar_job_label"
        unique_together = [["job", "label"]]

    def __str__(self):
        return f"{self.label.name}: {self.job.name}"


class JobHostSummary(BaseTimestampModel):
    """
    Per-host execution summary for a job.

    Maps to main_jobhostsummary table in AWX database.
    Contains detailed execution stats for each host in the job.
    """

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="host_summaries")
    host = models.ForeignKey(Host, on_delete=models.CASCADE, related_name="job_summaries", null=True, blank=True)
    host_name = models.CharField(max_length=255, db_index=True)

    # Task execution counts
    changed = models.IntegerField(default=0)
    dark = models.IntegerField(default=0)
    failures = models.IntegerField(default=0)
    ok = models.IntegerField(default=0)
    processed = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    failed = models.BooleanField(default=False)
    ignored = models.IntegerField(default=0)
    rescued = models.IntegerField(default=0)

    # Original timestamps from AWX
    created = models.DateTimeField()
    modified = models.DateTimeField()

    class Meta:
        db_table = "ar_job_host_summary"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["job", "host_name"]),
            models.Index(fields=["host", "created"]),
        ]
        unique_together = [["job", "host_name"]]

    def __str__(self):
        return f"{self.job.name} - {self.host_name}"

    @property
    def total_tasks(self):
        """Return total number of tasks executed."""
        return self.ok + self.changed + self.failures + self.skipped


# =============================================================================
# Collection Metadata Models
# =============================================================================


class CollectionRun(BaseTimestampModel):
    """
    Tracks automation reports data collection runs.

    Records metadata about each time data is collected from the source database.
    """

    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("running", "Running"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="running",
    )

    # Collection parameters
    source_database = models.CharField(max_length=100, default="awx")
    date_from = models.DateTimeField(null=True, blank=True)
    date_to = models.DateTimeField(null=True, blank=True)

    # Collection results
    jobs_collected = models.IntegerField(default=0)
    organizations_collected = models.IntegerField(default=0)
    job_templates_collected = models.IntegerField(default=0)
    hosts_collected = models.IntegerField(default=0)

    # Error tracking
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "ar_collection_run"
        ordering = ["-started_at"]

    def __str__(self):
        return f"Collection Run {self.id} - {self.status}"

    def mark_completed(self, **counts):
        """Mark collection as completed with count statistics."""
        self.status = "completed"
        self.completed_at = timezone.now()
        for key, value in counts.items():
            setattr(self, key, value)
        self.save()

    def mark_failed(self, error_message: str):
        """Mark collection as failed with error message."""
        self.status = "failed"
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save()

    @property
    def duration_seconds(self):
        """Return collection duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
