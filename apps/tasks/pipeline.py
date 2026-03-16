"""
End-to-end test pipeline for metrics collection, anonymization, and Segment transmission.

Runs the full daily pipeline for a given date in sequence:
  1. Hourly collections  – all collector types, for each requested hour
  2. Snapshot collections – all collector types (point-in-time state)
  3. Daily metrics rollup – merges hourly/snapshot data into a DailyMetricsSummary
  4. Anonymize & prepare  – anonymizes the summary and creates an AnonymizedMetricsPayload
  5. Send to Segment      – transmits the payload (event name gets '_Test' suffix when
                           SEGMENT_TEST_MODE is enabled)

Intended for end-to-end testing only. Always enable SEGMENT_TEST_MODE before running
so that test events are clearly separated from real customer data in Segment.
"""

import logging
from datetime import date, timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Ordered list of hourly collector types (matches production schedule)
HOURLY_COLLECTOR_TYPES: list[str] = [
    "job_host_summary_service",
    "unified_jobs",
    "credentials_service",
    "main_jobevent_service",
]

# Ordered list of snapshot collector types (matches production schedule)
SNAPSHOT_COLLECTOR_TYPES: list[str] = [
    "execution_environments",
    "config",
    "controller_version_service",
    "table_metadata",
]


def _is_test_mode_active() -> bool:
    """Return True when SEGMENT_TEST_MODE is enabled in Django settings."""
    return bool(getattr(settings, "SEGMENT_TEST_MODE", False))


def run_test_pipeline(
    summary_date: date | None = None,
    *,
    skip_hourly: bool = False,
    skip_snapshot: bool = False,
    hours: list[int] | None = None,
) -> dict[str, Any]:
    """
    Run the full metrics pipeline end-to-end for a single day.

    Steps executed in order:
      1. Hourly collections  (skippable via skip_hourly)
      2. Snapshot collections (skippable via skip_snapshot)
      3. Daily metrics rollup
      4. Anonymize & prepare
      5. Send to Segment

    If any of steps 3–5 return an error the pipeline aborts immediately and
    returns a result dict with ``status="error"`` and ``step`` indicating which
    step failed.

    Args:
        summary_date: Date to run the pipeline for (defaults to yesterday).
        skip_hourly: Skip all hourly collector calls (useful when data already
            exists in the database or to speed up local testing).
        skip_snapshot: Skip all snapshot collector calls.
        hours: Specific hours (0–23) to collect for. Defaults to all 24 hours.
            Ignored when skip_hourly=True.

    Returns:
        dict with ``status`` ("success" or "error"), ``summary_date``, and
        per-step ``results``.
    """
    from apps.tasks.collectors import (
        collect_hourly_metrics,
        collect_snapshot_metrics,
        daily_anonymize_and_prepare,
        daily_metrics_rollup,
        send_anonymized_to_segment,
    )

    if summary_date is None:
        summary_date = timezone.now().date() - timedelta(days=1)

    date_str = summary_date.isoformat()
    hours_to_collect = hours if hours is not None else list(range(24))

    pipeline_results: dict[str, Any] = {
        "summary_date": date_str,
        "test_mode_active": _is_test_mode_active(),
    }

    # ------------------------------------------------------------------
    # Step 1: Hourly collections
    # ------------------------------------------------------------------
    if not skip_hourly:
        logger.info(
            "Pipeline step 1/5: hourly collections (%d types × %d hours)",
            len(HOURLY_COLLECTOR_TYPES),
            len(hours_to_collect),
        )
        hourly_results: list[dict[str, Any]] = []
        for collector_type in HOURLY_COLLECTOR_TYPES:
            for hour in hours_to_collect:
                hour_ts = f"{date_str}T{hour:02d}:00:00+00:00"
                result = collect_hourly_metrics(collector_type=collector_type, hour_timestamp=hour_ts)
                hourly_results.append({"collector_type": collector_type, "hour": hour, "result": result})
        pipeline_results["hourly"] = hourly_results
    else:
        logger.info("Pipeline step 1/5: hourly collections – skipped")
        pipeline_results["hourly"] = "skipped"

    # ------------------------------------------------------------------
    # Step 2: Snapshot collections
    # ------------------------------------------------------------------
    if not skip_snapshot:
        logger.info("Pipeline step 2/5: snapshot collections (%d types)", len(SNAPSHOT_COLLECTOR_TYPES))
        snapshot_results: list[dict[str, Any]] = []
        for collector_type in SNAPSHOT_COLLECTOR_TYPES:
            result = collect_snapshot_metrics(collector_type=collector_type)
            snapshot_results.append({"collector_type": collector_type, "result": result})
        pipeline_results["snapshot"] = snapshot_results
    else:
        logger.info("Pipeline step 2/5: snapshot collections – skipped")
        pipeline_results["snapshot"] = "skipped"

    # ------------------------------------------------------------------
    # Step 3: Daily rollup
    # ------------------------------------------------------------------
    logger.info("Pipeline step 3/5: daily metrics rollup for %s", date_str)
    rollup_result = daily_metrics_rollup(summary_date=date_str)
    pipeline_results["rollup"] = rollup_result
    if rollup_result.get("status") == "error":
        logger.error("Pipeline aborted at step 3 (rollup): %s", rollup_result.get("error"))
        return {"status": "error", "step": "rollup", "error": rollup_result.get("error"), **pipeline_results}

    # ------------------------------------------------------------------
    # Step 4: Anonymize & prepare
    # ------------------------------------------------------------------
    logger.info("Pipeline step 4/5: anonymize and prepare for %s", date_str)
    anonymize_result = daily_anonymize_and_prepare(summary_date=date_str)
    pipeline_results["anonymize"] = anonymize_result
    if anonymize_result.get("status") == "error":
        logger.error("Pipeline aborted at step 4 (anonymize): %s", anonymize_result.get("error"))
        return {"status": "error", "step": "anonymize", "error": anonymize_result.get("error"), **pipeline_results}

    # ------------------------------------------------------------------
    # Step 5: Send to Segment
    # ------------------------------------------------------------------
    logger.info("Pipeline step 5/5: send to Segment (test_mode=%s)", _is_test_mode_active())
    send_result = send_anonymized_to_segment()
    pipeline_results["send"] = send_result
    if send_result.get("status") == "error":
        logger.error("Pipeline aborted at step 5 (send): %s", send_result.get("error"))
        return {"status": "error", "step": "send", "error": send_result.get("error"), **pipeline_results}

    logger.info("Pipeline completed successfully for %s", date_str)
    return {"status": "success", **pipeline_results}
