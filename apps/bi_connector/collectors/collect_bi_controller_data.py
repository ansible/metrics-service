"""
On-demand BI controller data collection task.

Invoked by ControllerTimeSeriesView when a BI tool requests live AWX data.
Runs inside dispatcherd so the HTTP request returns immediately (202) while
the potentially long-running AWX query executes in the background.

Result stored in Task.result_data by the tasks_system machinery and readable
via GET /api/v1/bi/tasks/<task_id>/ once status == "completed".
"""

import json
import logging

from apps.tasks.utils import get_db_connection, parse_datetime_string

logger = logging.getLogger(__name__)


def collect_bi_controller_data(
    collector_key: str | None = None,
    since: str | None = None,
    until: str | None = None,
    **kwargs,
) -> dict:
    """
    Collect live AWX data for a single collector type over an explicit date range.

    Called by tasks_system with unpacked task_data kwargs:
        collector_key (str)  — matches a key in get_hourly_collectors() registry
        since         (str)  — ISO 8601 datetime string
        until         (str)  — ISO 8601 datetime string

    Returns a dict compatible with the tasks_system success/error convention:
        {"status": "success", "collector_type": ..., "since": ..., "until": ..., "data": [...]}
    """
    since_str = since
    until_str = until

    if not all([collector_key, since_str, until_str]):
        return {"status": "error", "error": "task_data must contain collector_key, since, and until"}

    since = parse_datetime_string(since_str)
    until = parse_datetime_string(until_str)

    if since is None or until is None:
        return {"status": "error", "error": f"Invalid datetime values: since={since_str!r}, until={until_str!r}"}

    try:
        conn = get_db_connection()
    except Exception:
        logger.exception("AWX DB unavailable for bi_collect %s", collector_key)
        return {"status": "error", "error": "AWX database unavailable"}

    try:
        from apps.tasks.collectors.collect_hourly_metrics import get_hourly_collectors

        collectors = get_hourly_collectors()

        if collector_key not in collectors:
            return {"status": "error", "error": f"Unknown collector_key: {collector_key!r}"}

        collector = collectors[collector_key]["collector_func"](db=conn, since=since, until=until)
        raw = collector.gather()
        # Collectors return a pandas DataFrame which may contain Timestamp/Decimal
        # objects that are not JSON-serialisable. Use pandas' own JSON serialiser
        # (round-trips through a string) to normalise all types to plain Python.
        if hasattr(raw, "to_json"):
            data = json.loads(raw.to_json(orient="records", date_format="iso"))
        elif isinstance(raw, list):
            data = raw
        else:
            data = [raw] if raw is not None else []
    except Exception:
        logger.exception("Collection failed for bi_collect %s", collector_key)
        return {"status": "error", "error": "Collection failed"}

    logger.info("bi_collect %s completed: %d records", collector_key, len(data))
    return {
        "status": "success",
        "collector_type": collector_key,
        "since": since_str,
        "until": until_str,
        "data": data,
    }
