# APScheduler — Task Groups & Scheduled Jobs

The metrics-service scheduler process runs APScheduler and organises all scheduled work into five named task groups defined in `task_groups.py`. Each group maps to a queue and may be gated by a feature flag; the `UnifiedTaskScheduler` polls the database every 60 seconds, inserts `Task` model rows for any due jobs, and dispatches them to dispatcherd via `pg_notify`.

Groups and their tasks are registered at startup; one-shot tasks use a `DateTrigger` and fire only once, while recurring tasks use `IntervalTrigger` or `CronTrigger` schedules. All task state (due time, last run, status) is stored as rows in the PostgreSQL `Task` table.

```mermaid
flowchart LR
    subgraph maint["MAINTENANCE_GROUP\n(no feature flag)"]
        direction TB
        M1["daily_task_cleanup\ncleanup_old_tasks\ndaily 05:00"]
        M2["hourly_health_check\nhello_world\nevery hour :00"]
        M3["initial_resource_sync\nsync_resources_from_gateway\none-shot on init"]
    end

    subgraph metrics["METRICS_GROUP\nfeature: METRICS_COLLECTION"]
        direction TB
        ME1["hourly_unified_jobs :05\nhourly_job_host_summary :10\nhourly_credentials :15\nhourly_job_events :20"]
        ME2["daily EEs 01:00 · config 01:30\ncontroller_version 01:35\ntable_metadata 01:40\nfeature_flags 01:45"]
        ME3["daily_task_executions 01:50\ndaily_metrics_rollup 02:00\ncleanup_metrics_data 04:00"]
    end

    subgraph anon["ANONYMIZED_GROUP\nfeature: ANONYMIZED_DATA_COLLECTION"]
        direction TB
        A1["daily_anonymize_and_prepare\ndaily 03:00"]
        A2["send_anonymized_to_segment\n1-240 min jitter after 03:00"]
    end

    subgraph dash["DASHBOARD_GROUP\nfeature: DASHBOARD_COLLECTION"]
        direction TB
        D1["initial_dashboard_collection\none-shot on enable"]
        D2["cleanup_dashboard_reports_old_data\ndaily 05:30"]
        D3["cleanup_dashboard_telemetry\ndaily 05:45"]
    end

    subgraph indirect["INDIRECT_GROUP\nfeature: INDIRECT_NODE_COLLECTION\n(default: disabled)"]
        I1["daily_collect_indirect_nodes\ncollect_daily_metrics indirect_managed_nodes\ndaily 01:55"]
    end

    UTS["UnifiedTaskScheduler\nAPScheduler\npoll DB every 60s\ninsert Task rows for due jobs\ndispatch via pg_notify"]

    maint --> UTS
    metrics --> UTS
    anon --> UTS
    dash --> UTS
    indirect --> UTS
    UTS --> DB["PostgreSQL\nTask queue\n(Task model rows)"]
```
