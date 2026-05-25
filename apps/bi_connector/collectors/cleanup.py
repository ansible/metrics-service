"""
Cleanup tasks for BI connector billing collection storage.

Two separate cleanups because the data has different retention semantics:
- CollectionBatch is time-series (one row per run) — delete by age.
- StoredHostMetric is upserted (one row per hostname) — only delete hosts
  that were deleted in AWX and haven't been automated recently.
- StoredJobHostSummary / StoredIndirectAudit are time-series — delete by date.
"""

import logging
from datetime import timedelta

from django.utils.timezone import now

logger = logging.getLogger(__name__)


def cleanup_bi_collection_batches(task_data: dict | None = None, **kwargs) -> dict:
    """Delete CollectionBatch records older than retention_days (default 90)."""
    retention_days = (task_data or {}).get("retention_days", 90)
    cutoff = now() - timedelta(days=retention_days)
    from apps.bi_connector.models import CollectionBatch

    count, _ = CollectionBatch.objects.filter(created__lt=cutoff).delete()
    logger.info("Deleted %d CollectionBatch records older than %d days", count, retention_days)
    return {"status": "success", "deleted": count}


def cleanup_bi_stored_host_metrics(task_data: dict | None = None, **kwargs) -> dict:
    """
    Delete StoredHostMetric rows that are both deleted=True in AWX AND have not
    been automated in the past stale_days (default 365). Active hosts are never removed.
    """
    stale_days = (task_data or {}).get("stale_days", 365)
    cutoff = now() - timedelta(days=stale_days)
    from apps.bi_connector.models import StoredHostMetric

    count, _ = StoredHostMetric.objects.filter(deleted=True, last_automation__lt=cutoff).delete()
    logger.info("Deleted %d stale deleted StoredHostMetric records", count)
    return {"status": "success", "deleted": count}
