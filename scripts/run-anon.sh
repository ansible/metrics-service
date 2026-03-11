#!/bin/sh
set -e
set -x

uv run scripts/run_task.py collect_hourly_metrics '{"collector_type": "credentials_service", "hour_timestamp": "20250613T10:00:00Z"}'
uv run scripts/run_task.py collect_hourly_metrics '{"collector_type": "job_host_summary_service", "hour_timestamp": "20250613T10:00:00Z"}'
# disabled for now: uv run scripts/run_task.py collect_hourly_metrics '{"collector_type": "main_jobevent_service", "hour_timestamp": "20250613T10:00:00Z"}'
uv run scripts/run_task.py collect_hourly_metrics '{"collector_type": "unified_jobs", "hour_timestamp": "20250613T10:00:00Z"}'

# TODO dates from here on (20250613)
# these just once per day, same table (misnomer but works)
uv run scripts/run_task.py collect_snapshot_metrics '{"collector_type": "config"}'
uv run scripts/run_task.py collect_snapshot_metrics '{"collector_type": "controller_version_service"}'
uv run scripts/run_task.py collect_snapshot_metrics '{"collector_type": "execution_environments"}'
uv run scripts/run_task.py collect_snapshot_metrics '{"collector_type": "table_metadata"}'

# dump to hourly_dumps/
uv run scripts/dump_hourly.py

# this reads from tasks_hourlymetricscollection and writes to tasks_dailymetricssummary
uv run scripts/run_task.py daily_metrics_rollup

# this reads from tasks_dailymetricssummary and writes to tasks_anonymizedmetricspayload
uv run scripts/run_task.py daily_anonymize_and_prepare

# dump to daily_dumps/
uv run scripts/dump_daily_anonymized.py

# this reads from tasks_anonymizedmetricspayload and sends to segment
uv run scripts/run_task.py send_anonymized_to_segment

echo SUCCESS
