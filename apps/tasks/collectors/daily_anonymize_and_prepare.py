"""
Anonymize daily rollup and prepare payload for Segment.

This task fetches the daily rollup summary (containing all 6 collectors),
combines the rollup JSONs using anonymize_rollups(), applies salt-based hashing,
and creates an anonymized payload ready for transmission.

The output is a flattened structure with statistics and arrays ready for Segment.
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

logger = logging.getLogger(__name__)


@task(queue="metrics_collectors", decorate=False)
@task_execution_wrapper("daily_anonymize_and_prepare")
def daily_anonymize_and_prepare(**kwargs) -> dict[str, Any]:
    """
    Anonymize daily metrics summary and prepare payload for Segment

    - Fetches DailyMetricsSummary non-anyonymized daily rollup
    - anonymizes using anonymize_rollups() from metrics-utility
    - Creates AnonymizedMetricsPayload record

    Args:
        **kwargs: Task data containing:
            - summary_date (str): Date to anonymize (YYYY-MM-DD, defaults to yesterday)
            - salt (str): Anonymization salt (auto-generated if not provided)

    Returns:
        dict: Task result with payload ID
    """
    from django.db import transaction

    # Import from metrics-utility (will fail if not available)
    from metrics_utility.anonymized_rollups import anonymize_rollups

    from apps.tasks.models import AnonymizedMetricsPayload, DailyMetricsSummary

    # Determine summary date
    summary_date_str = kwargs.get("summary_date")
    if summary_date_str:
        summary_date = date.fromisoformat(summary_date_str)
    else:
        summary_date = timezone.now().date() - timedelta(days=1)

    log_task_execution("daily_anonymize_and_prepare", "processing", f"Anonymizing daily rollup for: {summary_date}")

    try:
        # Get daily summary (merged rollup but not anonymized)
        daily_summary = DailyMetricsSummary.objects.get(summary_date=summary_date, status="aggregated")
        metrics = daily_summary.aggregated_metrics

        anonymized_data = anonymize_rollups(
            events_modules_rollup=metrics.get("main_jobevent_service", {}),
            execution_environments_rollup=metrics.get("execution_environments", {}),
            jobs_rollup=metrics.get("unified_jobs", {}),
            job_host_summary_rollup=metrics.get("job_host_summary_service", {}),
            credentials_rollup=metrics.get("credentials_service", {}),
            table_metadata_rollup=metrics.get("table_metadata", {}),
            controller_version_rollup=metrics.get("controller_version_service", {}),
            salt=kwargs.get("salt", generate_salt()),
        )

        # Add metadata
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
            event_name = f"Controller Metrics Daily Rollup {todays_date}"
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
