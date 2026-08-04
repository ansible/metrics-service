# Metrics Data Pipeline — Collection to Segment

The metrics-service runs a daily pipeline that collects AWX job and configuration data from the Controller PostgreSQL database, rolls it up, anonymizes it, and ships it to Segment for telemetry analysis. The pipeline is gated by two feature flags — `METRICS_COLLECTION` (stages 1–2) and `ANONYMIZED_DATA_COLLECTION` (stages 3–4) — and is orchestrated entirely by APScheduler jobs scheduled within the Django application.

Each stage produces a database record that serves as the input to the next stage, giving the pipeline durability and the ability to resume after failures without data loss.

```mermaid
flowchart TB
    subgraph awx2["AWX / Controller PostgreSQL DB — source"]
        direction LR
        H1["unified_jobs :05\njob_host_summary :10\ncredentials :15\njob_events :20"]
        H2["execution_environments 01:00\nconfig 01:30 · controller_version 01:35\ntable_metadata 01:40 · feature_flags 01:45\ntask_executions 01:50"]
        H3["indirect_managed_nodes 01:55\n(INDIRECT_NODE_COLLECTION)"]
    end

    subgraph stage1["Stage 1 — Hourly Collection\nfeature: METRICS_COLLECTION"]
        COL["metrics_utility collector.gather()\npandas DataFrame\nAnonymizedRollup.prepare() → JSON"]
        HMC["HourlyMetricsCollection\ncollector_type + collection_timestamp\n(unique_together)\nraw_data JSON · status: collected"]
    end

    subgraph stage2["Stage 2 — Daily Rollup — 02:00 AM"]
        ROLL["daily_metrics_rollup()\nrollup_processor.merge()\n24 hourly blobs per collector_type"]
        DMS["DailyMetricsSummary\nsummary_date (unique)\naggregated_metrics JSON\nstatus: aggregated"]
    end

    subgraph stage3["Stage 3 — Anonymize — 03:00 AM\nfeature: ANONYMIZED_DATA_COLLECTION"]
        ANON["daily_anonymize_and_prepare()\nanonymize_rollups()\nstrip PII · hash IDs (daily-rotated salt)\nadd summary_metadata + dashboard_telemetry"]
        AMP["AnonymizedMetricsPayload\nsummary_date\nanonymized_data JSON\nstatus: pending → sending → sent"]
    end

    subgraph stage4["Stage 4 — Ship to Segment\n1-240 min random jitter"]
        SHIP["send_anonymized_to_segment()\nStorageSegment.put()\nmax SEGMENT_MAX_ATTEMPTS=7\nexponential backoff"]
        SEG["Segment.com\nEvent: Controller Metrics Daily Rollup\nSEGMENT_TEST_MODE appends _Test"]
    end

    CLEAN["cleanup_metrics_data()\n04:00 AM\npurge old HourlyMetricsCollection\nand DailyMetricsSummary rows"]

    H1 --> COL
    H2 --> COL
    H3 -.->|"if enabled"| COL
    COL --> HMC
    HMC --> ROLL
    ROLL --> DMS
    DMS --> ANON
    ANON --> AMP
    AMP --> SHIP
    SHIP --> SEG
    HMC -.->|"04:00 cleanup"| CLEAN
    DMS -.->|"04:00 cleanup"| CLEAN
```
