"""
Storage models for BI connector billing data collection.

StoredHostMetric, StoredJobHostSummary, StoredIndirectAudit hold data collected
from AWX via metrics-utility billing collectors and are served by BI Layer 1 API.
CollectionBatch tracks every collection run (scheduled or backfill) for the UI.
"""

from django.db import models

# FK string reused across StoredHostMetric, StoredJobHostSummary, StoredIndirectAudit
_COLLECTION_BATCH_FK = "bi_connector.CollectionBatch"

try:
    from ansible_base.lib.abstract_models import CommonModel
except ImportError:

    class CommonModel(models.Model):
        """Minimal fallback base model used when django-ansible-base is not installed."""

        created = models.DateTimeField(auto_now_add=True)
        modified = models.DateTimeField(auto_now=True)

        class Meta:
            """Mark as abstract so no DB table is created."""

            abstract = True


class CollectionBatch(CommonModel):
    """
    Tracks a single billing data collection run (scheduled or backfill).

    Created at the start of each run and updated as the run progresses.
    Other stored models FK here to record which batch imported each row.
    """

    BATCH_TYPE_CHOICES = [
        ("scheduled", "Scheduled"),
        ("backfill", "Backfill"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    collector_type = models.CharField(max_length=128, db_index=True)
    batch_type = models.CharField(max_length=16, choices=BATCH_TYPE_CHOICES, default="scheduled")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending", db_index=True)
    since = models.DateTimeField(null=True, blank=True)
    until = models.DateTimeField(null=True, blank=True)
    records_imported = models.PositiveBigIntegerField(default=0)
    cursor = models.JSONField(
        default=dict
    )  # stores resume position e.g. {"last_committed": "2024-01-15T06:00:00+00:00"}
    task = models.ForeignKey(
        "tasks.Task",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="collection_batches",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        """Default ordering and DB indexes for CollectionBatch."""

        ordering = ["-created"]
        indexes = [
            models.Index(fields=["status", "-created"]),
            models.Index(fields=["collector_type", "-created"]),
        ]

    def __str__(self) -> str:
        """Return a human-readable representation of this batch."""
        return f"CollectionBatch({self.collector_type}/{self.batch_type} status={self.status})"


class StoredHostMetric(CommonModel):
    """
    One row per hostname, upserted from AWX main_hostmetric.

    AWX enforces UNIQUE on main_hostmetric.hostname so each hostname maps to
    exactly one row here.  Rows are upserted (update_or_create) on each
    scheduled collection run.
    """

    hostname = models.CharField(max_length=512, unique=True, db_index=True)
    host_id = models.BigIntegerField(null=True, blank=True)
    first_automation = models.DateTimeField(null=True, blank=True)
    last_automation = models.DateTimeField(null=True, blank=True)
    automated_counter = models.PositiveIntegerField(default=0)
    deleted_counter = models.PositiveIntegerField(default=0)
    last_deleted = models.DateTimeField(null=True, blank=True)
    deleted = models.BooleanField(default=False)
    ansible_product_serial = models.CharField(max_length=255, null=True, blank=True)
    ansible_machine_id = models.CharField(max_length=255, null=True, blank=True)
    ansible_host_variable = models.CharField(max_length=512, null=True, blank=True)
    ansible_connection_variable = models.CharField(max_length=512, null=True, blank=True)
    collection_batch = models.ForeignKey(
        _COLLECTION_BATCH_FK,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        """DB indexes for StoredHostMetric to support BI query patterns."""

        indexes = [
            models.Index(fields=["last_automation"]),
            models.Index(fields=["first_automation"]),
            models.Index(fields=["deleted"]),
        ]

    def __str__(self) -> str:
        """Return a human-readable representation of this host metric record."""
        return f"StoredHostMetric({self.hostname})"


class StoredJobHostSummary(CommonModel):
    """
    One row per AWX job-host summary, upserted from AWX main_jobhostsummary.

    summary_id mirrors AWX main_jobhostsummary.id and is the natural deduplication
    key — rows are upserted via update_or_create(summary_id=...).
    """

    summary_id = models.BigIntegerField(unique=True, db_index=True)  # AWX main_jobhostsummary.id
    host_id = models.BigIntegerField(null=True, blank=True)
    job_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    host_name = models.CharField(max_length=512, null=True, blank=True)
    organization_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    inventory_id = models.BigIntegerField(null=True, blank=True)
    modified = models.DateTimeField(null=True, blank=True, db_index=True)
    collection_batch = models.ForeignKey(
        _COLLECTION_BATCH_FK,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        """DB indexes for StoredJobHostSummary to support BI query patterns."""

        indexes = [
            models.Index(fields=["modified"]),
            models.Index(fields=["job_id"]),
            models.Index(fields=["organization_id"]),
        ]

    def __str__(self) -> str:
        """Return a human-readable representation of this job-host summary record."""
        return f"StoredJobHostSummary(summary_id={self.summary_id})"


class StoredIndirectAudit(CommonModel):
    """
    One row per AWX indirect managed node audit entry.

    audit_id mirrors AWX main_indirectmanagednodeaudit.id and is the natural
    deduplication key — rows are upserted via update_or_create(audit_id=...).
    Available from AWX 2.6+.
    """

    audit_id = models.BigIntegerField(unique=True, db_index=True)  # AWX main_indirectmanagednodeaudit.id
    host_id = models.BigIntegerField(null=True, blank=True)
    job_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    organization_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    created = models.DateTimeField(null=True, blank=True, db_index=True)
    collection_batch = models.ForeignKey(
        _COLLECTION_BATCH_FK,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        """DB indexes for StoredIndirectAudit to support BI query patterns."""

        indexes = [
            models.Index(fields=["created"]),
            models.Index(fields=["job_id"]),
        ]

    def __str__(self) -> str:
        """Return a human-readable representation of this indirect audit record."""
        return f"StoredIndirectAudit(audit_id={self.audit_id})"
