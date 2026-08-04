# Task System

The metrics-service task system is a three-layer pipeline: a PostgreSQL-backed `Task` model defines what runs and when, `UnifiedTaskScheduler` (backed by APScheduler) polls for due tasks and dispatches them via `pg_notify`, and `dispatcherd` workers listen on named channels to atomically claim and execute tasks. Advisory locks (`pg_advisory_lock`) prevent concurrent execution of heavyweight operations such as metrics collection and anonymization. Task lifecycle state is tracked in `TaskExecution`, with a background watchdog marking any task that exceeds `TASK_TIMEOUT=3600s` as failed.

```mermaid
flowchart TB
    subgraph db["PostgreSQL"]
        TM["Task\nfunction_name · schedule · is_enabled\ncan_modify · queue · extra_vars\nlast_run · next_run"]
        TE["TaskExecution\nstatus: pending → running\n→ successful / failed / retry / cancelled\nstarted_at · finished_at · output"]
    end

    subgraph sched["scheduler — UnifiedTaskScheduler (APScheduler)"]
        POLL["Poll DB every 60s\nfor due Tasks"]
        TRIG["CronTrigger /\nDateTrigger"]
        INJECT["Inject pinned\nhour_timestamp"]
        SUBMIT["submit_task_to_dispatcher()\npg_notify on queue channel"]
        STUCK["_fail_stuck_tasks()\nevery 30s — mark running tasks\nolder than TASK_TIMEOUT=3600s as failed\nkill stale advisory lock PG sessions"]
    end

    subgraph disp["dispatcherd — pg_notify workers"]
        LISTEN["LISTEN on channels:\nmaintenance / metrics / dashboard"]
        CLAIM["_claim_task()\nSELECT FOR UPDATE SKIP LOCKED\natomic DB claim"]
        EXEC["execute_db_task()\nTASK_FUNCTIONS[function_name]()"]
        LOCK["pg_advisory_lock\n(metrics_utility.library.lock)\nwraps: collect_hourly_metrics\ncollect_snapshot_metrics\ndaily_metrics_rollup\ndaily_anonymize_and_prepare\nsend_anonymized_to_segment\ndashboard sync tasks"]
    end

    TM -->|"scheduled by"| POLL
    POLL --> TRIG
    TRIG --> INJECT
    INJECT --> SUBMIT
    SUBMIT -->|pg_notify| LISTEN
    LISTEN --> CLAIM
    CLAIM --> EXEC
    EXEC -->|"acquires"| LOCK
    EXEC --> TE
    POLL -->|every 30s check| STUCK
    STUCK -->|"mark failed"| TE
    TM -->|"system tasks\ncan_modify=false\nblocked on PATCH"| EXEC
```
