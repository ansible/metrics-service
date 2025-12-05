"""
Django models for metrics storage in SQLite database.

This module defines the data model for storing metrics collected from
the metrics-utility library. Data is stored in a dedicated SQLite database
(metricsStorage.sqlite) separate from the main application database.
"""

from django.db import models
from django.utils import timezone


class CollectionRun(models.Model):
    """
    Represents a single metrics collection run.

    Tracks when collection started, completed, and overall status.
    Links to all MetricData records created during this run.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    metrics_collected = models.IntegerField(default=0)
    collectors_run = models.JSONField(
        default=list, help_text="List of collector names that were run (e.g., ['config', 'job_host_summary'])"
    )
    parameters_used = models.JSONField(
        default=dict, help_text="Parameters passed to the collection task (database, since, until, etc.)"
    )
    error_message = models.TextField(blank=True, help_text="Error message if collection failed")

    class Meta:
        db_table = "collection_runs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["-started_at", "status"]),
        ]

    def __str__(self):
        return f"CollectionRun {self.id} - {self.status} at {self.started_at}"

    def mark_completed(self, metrics_count=0):
        """Mark the collection run as completed."""
        self.status = "completed"
        self.completed_at = timezone.now()
        self.metrics_collected = metrics_count
        self.save(using="metrics_storage")

    def mark_failed(self, error_message=""):
        """Mark the collection run as failed with an error message."""
        self.status = "failed"
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save(using="metrics_storage")


class MetricType(models.Model):
    """
    Represents a type of metric collector.

    Examples: 'config', 'job_host_summary', 'main_host', 'anonymized_rollups', etc.
    """

    name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=50, default="general", help_text="Category of metric (e.g., 'controller', 'anonymized', 'system')"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "metric_types"
        ordering = ["name"]

    def __str__(self):
        return self.name


class MetricData(models.Model):
    """
    Stores the actual metrics data collected from each collector.

    Each record represents data from one collector during one collection run.
    The actual metrics are stored in the 'data' JSONField for flexibility.
    """

    collection_run = models.ForeignKey(
        CollectionRun,
        on_delete=models.CASCADE,
        related_name="metrics",
        help_text="The collection run this metric belongs to",
    )
    metric_type = models.ForeignKey(
        MetricType,
        on_delete=models.PROTECT,
        related_name="metrics",
        help_text="Type of collector that produced this metric",
    )
    collected_at = models.DateTimeField(default=timezone.now, db_index=True)
    data = models.JSONField(help_text="The actual metrics data collected (structure varies by metric_type)")
    data_size_bytes = models.IntegerField(
        default=0, help_text="Size of the data field in bytes (for monitoring storage)"
    )
    collection_duration_ms = models.IntegerField(
        null=True, blank=True, help_text="How long the collection took in milliseconds"
    )
    was_successful = models.BooleanField(default=True, help_text="Whether the collection was successful")
    error_message = models.TextField(blank=True, help_text="Error message if collection failed")

    class Meta:
        db_table = "metric_data"
        ordering = ["-collected_at"]
        indexes = [
            models.Index(fields=["-collected_at", "metric_type"]),
            models.Index(fields=["collection_run", "metric_type"]),
            models.Index(fields=["was_successful"]),
        ]

    def __str__(self):
        return f"{self.metric_type.name} - {self.collected_at}"

    def save(self, *args, **kwargs):
        """Override save to calculate data size automatically."""
        if self.data:
            import json

            self.data_size_bytes = len(json.dumps(self.data).encode("utf-8"))
        super().save(*args, **kwargs)


class MetricSource(models.Model):
    """
    Represents a source system that metrics are collected from.

    This could be an AWX/Controller instance, a host, or any other identifiable source.
    """

    SOURCE_TYPE_CHOICES = [
        ("controller", "Automation Controller"),
        ("host", "Host"),
        ("service", "Service"),
        ("cluster", "Cluster"),
        ("other", "Other"),
    ]

    source_type = models.CharField(max_length=50, choices=SOURCE_TYPE_CHOICES, default="controller", db_index=True)
    source_id = models.CharField(max_length=255, help_text="Unique identifier for the source (e.g., UUID, hostname)")
    source_name = models.CharField(max_length=255, blank=True, help_text="Human-readable name for the source")
    metadata = models.JSONField(default=dict, help_text="Additional metadata about the source")
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "metric_sources"
        unique_together = [["source_type", "source_id"]]
        ordering = ["-last_seen"]
        indexes = [
            models.Index(fields=["source_type", "source_id"]),
        ]

    def __str__(self):
        return f"{self.source_type}: {self.source_name or self.source_id}"
