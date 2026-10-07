"""Analytics storage models (ANSTRAT-1587 / AAP-87799)."""

from __future__ import annotations

import hashlib
from datetime import datetime

from django.db import models

# Reuse the same DAB base classes / fallbacks as the tasks app.
try:
    from ansible_base.activitystream.models import AuditableModel
    from ansible_base.lib.abstract_models import CommonModel
except ImportError:  # pragma: no cover - simple fallback for setups without DAB

    class CommonModel(models.Model):
        created = models.DateTimeField(auto_now_add=True)
        modified = models.DateTimeField(auto_now=True)

        class Meta:
            abstract = True

    class AuditableModel(models.Model):
        class Meta:
            abstract = True


# Default origin for a local install.
LOCAL_SOURCE = "local"


class AnalyticsPayload(CommonModel, AuditableModel):
    """Raw pre-``prepare()`` collector payload for the analytics API.

    Every successful collection is retained, including repeated or unbounded windows. The
    ``payload`` holds the JSON-serialisable form of the collector's ``gather()`` output — a list
    of record dicts for DataFrame collectors, or a dict for the ``config`` snapshot collector.
    """

    class Meta:
        app_label = "analytics"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["created"]),
            models.Index(fields=["collector", "since"]),
            models.Index(fields=["collector", "until"]),
            models.Index(fields=["collector", "started_at"]),
        ]
        verbose_name = "Analytics Payload"
        verbose_name_plural = "Analytics Payloads"

    # Identification
    collector = models.CharField(max_length=128, help_text="Collector name (collector_type / API path segment)")

    source = models.CharField(
        max_length=64,
        default=LOCAL_SOURCE,
        help_text="Originating platform component, such as local, controller, eda, or hub.",
    )

    # Collection window as passed to the collector. Both nullable — some collectors
    # (snapshots such as config) do not accept a since/until window.
    since = models.DateTimeField(null=True, blank=True, help_text="`since` passed to the collector (inclusive), if any")
    until = models.DateTimeField(null=True, blank=True, help_text="`until` passed to the collector (exclusive), if any")

    # When the gather() call ran.
    started_at = models.DateTimeField(help_text="When collection (gather) started")
    finished_at = models.DateTimeField(help_text="When collection (gather) finished")

    # Data
    payload = models.JSONField(default=dict, help_text="Raw pre-prepare() gather() output, JSON-serialisable")

    def __str__(self) -> str:
        """Return a readable representation: collector + window (or 'snapshot')."""
        window = f"{self.since} → {self.until}" if self.since or self.until else "snapshot"
        return f"{self.collector} [{self.source}] ({window})"


class AnalyticsCollectionClaim(CommonModel, AuditableModel):
    """Coordinate one on-demand collection without changing payload row retention."""

    class Meta:
        app_label = "analytics"
        indexes = [
            models.Index(fields=["collector", "source", "status"]),
            models.Index(fields=["modified"]),
        ]
        verbose_name = "Analytics Collection Claim"
        verbose_name_plural = "Analytics Collection Claims"

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    # A digest gives the unique constraint a fixed size while the individual fields remain
    # inspectable. In particular, NULL bounds are represented explicitly in the digest.
    claim_key = models.CharField(max_length=64, unique=True)
    collector = models.CharField(max_length=128)
    source = models.CharField(max_length=64, default=LOCAL_SOURCE)
    since = models.DateTimeField(null=True, blank=True)
    until = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    task = models.ForeignKey(
        "tasks.Task",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="analytics_claims",
    )
    payload = models.ForeignKey(
        AnalyticsPayload,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="collection_claims",
    )
    error_message = models.TextField(blank=True, default="")

    @staticmethod
    def make_key(collector: str, source: str, since: datetime | None, until: datetime | None) -> str:
        """Return a stable key that distinguishes every nullable window bound."""
        parts = [collector, source]
        for bound in (since, until):
            parts.append("<null>" if bound is None else bound.isoformat())
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
