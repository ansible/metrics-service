"""
Anonymize daily summary and prepare payload for Segment.

This task fetches the daily metrics summary, applies anonymization using
metrics-utility, and creates an anonymized payload ready for transmission.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.utils import timezone

from ..utils import (
    create_task_result,
    generate_salt,
    log_task_execution,
    task,
    task_execution_wrapper,
)
from .helpers import (
    METRICS_UTILITY_AVAILABLE,
    MSG_METRICS_UTILITY_NOT_AVAILABLE,
    anonymize_rollup_data,
)

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("daily_anonymize_and_prepare")
def daily_anonymize_and_prepare(**kwargs) -> dict[str, Any]:
    """
    Anonymize daily summary and prepare payload for Segment.

    This task:
    1. Fetches DailyMetricsSummary (with aggregated, non-anonymized data)
    2. Applies anonymization using anonymize_rollup_data() from metrics-utility
    3. Creates AnonymizedMetricsPayload record
    4. Does NOT send (separate task handles sending)

    Args:
        **kwargs: Task data containing:
            - summary_date (str): Date to anonymize (YYYY-MM-DD, defaults to yesterday)
            - salt (str): Anonymization salt (auto-generated if not provided)

    Returns:
        dict: Task result with payload ID
    """
    from django.db import transaction

    from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

    if not METRICS_UTILITY_AVAILABLE or anonymize_rollup_data is None:
        return create_task_result("error", error=MSG_METRICS_UTILITY_NOT_AVAILABLE)

    # Determine summary date
    summary_date_str = kwargs.get("summary_date")
    if summary_date_str:
        summary_date = date.fromisoformat(summary_date_str)
    else:
        summary_date = timezone.now().date() - timedelta(days=1)

    log_task_execution("daily_anonymize_and_prepare", "processing", f"Anonymizing daily summary for: {summary_date}")

    try:
        # Get daily summary (aggregated but not anonymized)
        daily_summary = DailyMetricsSummary.objects.get(summary_date=summary_date, status="aggregated")

        # Generate or use provided salt
        salt = kwargs.get("salt", generate_salt())

        # Prepare data structure for anonymization
        # anonymize_rollup_data expects a flattened structure with specific keys
        # Extract records from aggregated_metrics (each collector type has {"records": [...], ...})
        def extract_records(data: dict | list, default=None) -> list | dict:
            """Extract records from aggregated collector data structure."""
            if default is None:
                default = []
            if isinstance(data, dict):
                # New structure: {"records": [...], "total_records": N, "hourly_snapshots": [...]}
                return data.get("records", default)
            elif isinstance(data, list):
                # Legacy structure: direct list of records
                return data
            return default

        data_to_anonymize = {
            "job_host_summary": extract_records(daily_summary.aggregated_metrics.get("job_host_summary", {}), []),
            "jobs_by_template": extract_records(daily_summary.aggregated_metrics.get("jobs_by_template", {}), []),
            "module_stats": extract_records(daily_summary.aggregated_metrics.get("module_stats", {}), []),
            "collection_name_stats": extract_records(
                daily_summary.aggregated_metrics.get("collection_name_stats", {}), []
            ),
            "modules_used_per_playbook": extract_records(
                daily_summary.aggregated_metrics.get("modules_used_per_playbook", {}), []
            ),
            "main_jobevent": extract_records(daily_summary.aggregated_metrics.get("main_jobevent", {}), {}),
            "main_host": extract_records(daily_summary.aggregated_metrics.get("main_host", {}), {}),
        }

        # Apply anonymization using metrics-utility (modifies in-place)
        anonymize_rollup_data(data_to_anonymize, salt)

        # Add config and metadata
        anonymized_data = data_to_anonymize.copy()
        anonymized_data["config"] = daily_summary.config_data

        aggregation_timestamp = (
            daily_summary.aggregation_completed_at.isoformat() if daily_summary.aggregation_completed_at else None
        )
        anonymized_data["summary_metadata"] = {
            "summary_date": str(summary_date),
            "hourly_collections_count": daily_summary.hourly_collections_count,
            "missing_hours": daily_summary.missing_hours,
            "aggregation_timestamp": aggregation_timestamp,
        }

        # Use atomic transaction to prevent duplicate payloads
        with transaction.atomic():
            # Create AnonymizedMetricsPayload
            todays_date = datetime.now(UTC).date().isoformat()
            event_name = f"Controller Metrics Anonymized Daily {todays_date}"
            payload = AnonymizedMetricsPayload.objects.create(
                summary_date=summary_date,
                anonymized_data=anonymized_data,
                status="pending",
                daily_summary=daily_summary,
                anonymization_task_execution_id=kwargs.get("execution_id"),
                segment_event_name=kwargs.get("event_name", event_name),
                segment_user_id=kwargs.get("user_id", generate_salt()),
            )

            # Update daily summary status
            daily_summary.status = "anonymized"
            daily_summary.save()

        log_task_execution("daily_anonymize_and_prepare", "completed", f"Created anonymized payload ID: {payload.id}")

        return create_task_result(
            "success",
            {
                "task_type": "daily_anonymize_and_prepare",
                "payload_id": payload.id,
                "summary_date": str(summary_date),
                "payload_size_bytes": payload.payload_size_bytes,
            },
        )

    except DailyMetricsSummary.DoesNotExist:
        error_msg = f"No daily summary found for {summary_date} with status=aggregated"
        logger.error(error_msg)
        return create_task_result("error", error=error_msg)

    except Exception as e:
        logger.error(f"Error in daily_anonymize_and_prepare: {str(e)}")
        return create_task_result("error", error=f"Anonymization failed: {str(e)}")
