"""
Billing data collection task for BI connector stored models.

Uses metrics-utility billing collectors to read from the AWX DB and write
to StoredHostMetric, StoredJobHostSummary, and StoredIndirectAudit.

500k-row flush: accumulate up to FLUSH_EVERY records from 10k-row extractor
batches, then bulk_create(update_conflicts=True) for idempotent upserts.
A CollectionBatch tracks progress so backfills resume after failure.
"""

import logging
from datetime import UTC, datetime

import pandas as pd
from django.utils.timezone import now

from apps.tasks.utils import get_db_connection, parse_datetime_string

logger = logging.getLogger(__name__)

FLUSH_EVERY = 500_000


# ---------------------------------------------------------------------------
# Internal flush helper
# ---------------------------------------------------------------------------


def _flush(records: list, model_class, unique_fields: list[str], update_fields: list[str]) -> int:
    """
    Bulk-upsert *records* into *model_class* using update_conflicts=True.

    Returns the number of records flushed.
    """
    if not records:
        return 0
    model_class.objects.bulk_create(
        records,
        update_conflicts=True,
        unique_fields=unique_fields,
        update_fields=update_fields,
    )
    count = len(records)
    records.clear()
    return count


# ---------------------------------------------------------------------------
# DataFrame row converters
# ---------------------------------------------------------------------------


def _safe_dt(value):
    """
    Coerce a pandas value to a timezone-aware datetime, or None.

    - NaT / None / NaN → None
    - Naive datetime → make UTC-aware
    - Already-aware datetime → pass through
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    # pandas Timestamp
    if hasattr(value, "to_pydatetime"):
        dt = value.to_pydatetime()
        if pd.isna(dt):
            return None
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return None


def _df_row_to_host_metric(row: "pd.Series", batch) -> "StoredHostMetric":  # noqa: F821
    """Convert a pandas Series from a host-metric DataFrame to a StoredHostMetric instance."""
    from apps.bi_connector.models import StoredHostMetric

    return StoredHostMetric(
        hostname=row.get("hostname") or row.get("name") or "",
        host_id=row.get("id"),
        first_automation=_safe_dt(row.get("first_automation")),
        last_automation=_safe_dt(row.get("last_automation")),
        automated_counter=row.get("automated_counter") or 0,
        deleted_counter=row.get("deleted_counter") or 0,
        last_deleted=_safe_dt(row.get("last_deleted")),
        deleted=bool(row.get("deleted", False)),
        ansible_product_serial=row.get("ansible_product_serial") or "",
        ansible_machine_id=row.get("ansible_machine_id") or "",
        ansible_host_variable=row.get("ansible_host_variable") or "",
        ansible_connection_variable=row.get("ansible_connection_variable") or "",
        collection_batch=batch,
    )


# ---------------------------------------------------------------------------
# Per-collector private implementations
# ---------------------------------------------------------------------------


def _collect_host_metric_snapshot(conn, since, until, batch) -> int:
    """
    Collect current host-metric snapshot via ExtractorControllerDB.

    Yields batches of a host_metric DataFrame, converts to StoredHostMetric,
    and flushes when the pending buffer reaches FLUSH_EVERY rows.
    """
    from metrics_utility.automation_controller_billing.extract.extractor_controller_db import (
        ExtractorControllerDB,
    )

    opt_since = since if since is not None else datetime(2000, 1, 1, tzinfo=UTC)
    extractor = ExtractorControllerDB({"opt_since": opt_since})

    pending: list = []
    total_flushed = 0

    for batch_data in extractor.iter_batches():
        df: pd.DataFrame = batch_data.get("host_metric")
        if df is None or df.empty:
            continue

        for _, row in df.iterrows():
            pending.append(_df_row_to_host_metric(row, batch))

        if len(pending) >= FLUSH_EVERY:
            flushed = _flush(
                pending,
                __import__("apps.bi_connector.models", fromlist=["StoredHostMetric"]).StoredHostMetric,
                unique_fields=["hostname"],
                update_fields=[
                    "host_id",
                    "first_automation",
                    "last_automation",
                    "automated_counter",
                    "deleted_counter",
                    "last_deleted",
                    "deleted",
                    "ansible_product_serial",
                    "ansible_machine_id",
                    "ansible_host_variable",
                    "ansible_connection_variable",
                    "collection_batch_id",
                    "modified",
                ],
            )
            total_flushed += flushed
            if batch is not None:
                batch.cursor = {"flushed_rows": total_flushed}
                batch.records_imported = total_flushed
                batch.save(update_fields=["cursor", "records_imported", "modified"])

    # Final flush of remaining records
    if pending:
        from apps.bi_connector.models import StoredHostMetric

        flushed = _flush(
            pending,
            StoredHostMetric,
            unique_fields=["hostname"],
            update_fields=[
                "host_id",
                "first_automation",
                "last_automation",
                "automated_counter",
                "deleted_counter",
                "last_deleted",
                "deleted",
                "ansible_product_serial",
                "ansible_machine_id",
                "ansible_host_variable",
                "ansible_connection_variable",
                "collection_batch_id",
                "modified",
            ],
        )
        total_flushed += flushed
        if batch is not None:
            batch.cursor = {"flushed_rows": total_flushed}
            batch.records_imported = total_flushed
            batch.save(update_fields=["cursor", "records_imported", "modified"])

    return total_flushed


def _collect_host_metric_daily(conn, since, until, batch) -> int:
    """
    Collect daily host-metric aggregates and store as StoredHostMetric rows.
    """
    from metrics_utility.library.collectors.controller import main_host_daily

    from apps.bi_connector.models import StoredHostMetric

    df: pd.DataFrame = main_host_daily(db=conn, since=since, until=until)
    if df is None or df.empty:
        return 0

    pending = [_df_row_to_host_metric(row, batch) for _, row in df.iterrows()]
    total_flushed = 0
    while pending:
        chunk, pending = pending[:FLUSH_EVERY], pending[FLUSH_EVERY:]
        total_flushed += _flush(
            chunk,
            StoredHostMetric,
            unique_fields=["hostname"],
            update_fields=[
                "host_id",
                "first_automation",
                "last_automation",
                "automated_counter",
                "deleted_counter",
                "last_deleted",
                "deleted",
                "ansible_product_serial",
                "ansible_machine_id",
                "ansible_host_variable",
                "ansible_connection_variable",
                "collection_batch_id",
                "modified",
            ],
        )
        if batch is not None:
            batch.records_imported = total_flushed
            batch.save(update_fields=["records_imported", "modified"])

    return total_flushed


def _collect_job_host_summary(conn, since, until, batch) -> int:
    """
    Collect job host summary rows and store as StoredJobHostSummary.
    """
    from metrics_utility.library.collectors.controller import job_host_summary

    from apps.bi_connector.models import StoredJobHostSummary

    df: pd.DataFrame = job_host_summary(db=conn, since=since, until=until)
    if df is None or df.empty:
        return 0

    pending = []
    for _, row in df.iterrows():
        pending.append(
            StoredJobHostSummary(
                summary_id=row.get("id"),
                host_id=row.get("host_id"),
                job_id=row.get("job_id"),
                host_name=row.get("host_name") or row.get("hostname") or "",
                organization_id=row.get("organization_id"),
                inventory_id=row.get("inventory_id"),
                modified=_safe_dt(row.get("modified")),
                collection_batch=batch,
            )
        )

    total_flushed = 0
    while pending:
        chunk, pending = pending[:FLUSH_EVERY], pending[FLUSH_EVERY:]
        total_flushed += _flush(
            chunk,
            StoredJobHostSummary,
            unique_fields=["summary_id"],
            update_fields=[
                "host_id",
                "job_id",
                "host_name",
                "organization_id",
                "inventory_id",
                "modified",
                "collection_batch_id",
            ],
        )
        if batch is not None:
            batch.records_imported = total_flushed
            batch.save(update_fields=["records_imported", "modified"])

    return total_flushed


def _collect_indirect_audit(conn, since, until, batch) -> int:
    """
    Collect indirect managed-node audit rows and store as StoredIndirectAudit.
    """
    from metrics_utility.library.collectors.controller import main_indirectmanagednodeaudit

    from apps.bi_connector.models import StoredIndirectAudit

    df: pd.DataFrame = main_indirectmanagednodeaudit(db=conn, since=since, until=until)
    if df is None or df.empty:
        return 0

    pending = []
    for _, row in df.iterrows():
        pending.append(
            StoredIndirectAudit(
                audit_id=row.get("id"),
                host_id=row.get("host_id"),
                job_id=row.get("job_id"),
                organization_id=row.get("organization_id"),
                created=_safe_dt(row.get("created")),
                collection_batch=batch,
            )
        )

    total_flushed = 0
    while pending:
        chunk, pending = pending[:FLUSH_EVERY], pending[FLUSH_EVERY:]
        total_flushed += _flush(
            chunk,
            StoredIndirectAudit,
            unique_fields=["audit_id"],
            update_fields=[
                "host_id",
                "job_id",
                "organization_id",
                "created",
                "collection_batch_id",
            ],
        )
        if batch is not None:
            batch.records_imported = total_flushed
            batch.save(update_fields=["records_imported", "modified"])

    return total_flushed


# ---------------------------------------------------------------------------
# Collector registry
# ---------------------------------------------------------------------------

_COLLECTOR_REGISTRY: dict[str, callable] = {
    "main_host": _collect_host_metric_snapshot,
    "main_host_daily": _collect_host_metric_daily,
    "job_host_summary": _collect_job_host_summary,
    "main_indirectmanagednodeaudit": _collect_indirect_audit,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def collect_bi_billing_data(task_data: dict | None = None, **kwargs) -> dict:
    """
    Collect billing data for a single collector type and store in the DB.

    task_data keys:
        collector_type (str)  — one of: main_host, main_host_daily,
                                job_host_summary, main_indirectmanagednodeaudit
        since          (str)  — ISO 8601 start datetime (used by time-series collectors)
        until          (str)  — ISO 8601 end datetime
        batch_id       (int)  — optional CollectionBatch PK
    """
    task_data = task_data or {}

    collector_type: str | None = task_data.get("collector_type")
    since_str: str | None = task_data.get("since")
    until_str: str | None = task_data.get("until")
    batch_id: int | None = task_data.get("batch_id")

    if not collector_type:
        raise ValueError("collector_type is required in task_data")

    if collector_type not in _COLLECTOR_REGISTRY:
        valid = ", ".join(sorted(_COLLECTOR_REGISTRY))
        raise ValueError(f"Unknown collector_type: {collector_type!r}. Valid types: {valid}")

    since = parse_datetime_string(since_str) if since_str else None
    until = parse_datetime_string(until_str) if until_str else None

    # Load and initialise CollectionBatch if provided
    batch = None
    if batch_id is not None:
        from apps.bi_connector.models import CollectionBatch

        batch = CollectionBatch.objects.get(pk=batch_id)
        batch.status = "running"
        batch.started_at = now()
        batch.save(update_fields=["status", "started_at", "modified"])

    conn = get_db_connection()
    handler = _COLLECTOR_REGISTRY[collector_type]

    try:
        total_records = handler(conn, since, until, batch)
    except Exception as exc:
        if batch is not None:
            batch.status = "failed"
            batch.error_message = str(exc)
            batch.save(update_fields=["status", "error_message", "modified"])
        raise

    if batch is not None:
        batch.status = "completed"
        batch.completed_at = now()
        batch.records_imported = total_records
        batch.save(update_fields=["status", "completed_at", "records_imported", "modified"])

    logger.info(
        "collect_bi_billing_data: collector_type=%s total_records=%d",
        collector_type,
        total_records,
    )

    return {
        "status": "success",
        "collector_type": collector_type,
        "records_imported": total_records,
    }
