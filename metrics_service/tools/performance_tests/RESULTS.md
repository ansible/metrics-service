# Metrics-Service Performance Test Results

**Date of test run:** 2026-02-23

## Source Data (AWX DB)

| Table               | Total rows | On test date (2024-01-25) |
|---------------------|------------|---------------------------|
| main_jobevent       | 4,599,376  | 1,264,938                 |
| main_jobhostsummary | 80,000     | —                         |
| main_host           | 4,000      | —                         |
| main_job            | 80         | —                         |

## Timing Results

| Phase | Duration | Notes |
|-------|----------|-------|
| Snapshot collectors | 0.42s | Run once (execution_environments, config, controller_version_service, table_metadata) |
| Hourly collection | 57.6s (1.0 min) | 24 hours × 4 collectors |
| — job_host_summary_service | 1.7s total | peak 753.6 MB |
| — unified_jobs | 1.3s total | failing: int64 serialization bug in metrics-utility |
| — credentials_service | 1.3s total | |
| — main_jobevent_service | 53.3s total | peak 953.1 MB |
| Rollup | 0.22s | |
| **Total** | **58.3s (1.0 min)** | |

## Memory

| Metric | Value |
|--------|-------|
| Baseline | 156.9 MB |
| Peak | 953.1 MB |
| Delta | 796.2 MB |

> **Note:** Peak memory is RSS sampled every 50ms during task execution.

## Output Table Sizes

| Table                   | Rows | Data Size |
|-------------------------|------|-----------|
| HourlyMetricsCollection | 100  | 7.92 MB   |
| DailyMetricsSummary     | 1    | 0.19 MB   |

## Known Issues

- **unified_jobs**: fails every hour with `Object of type int64 is not JSON serializable` — `sanitize_json` not applied in `jobs_anonymized_rollup.py` in metrics-utility
- **Snapshot collectors**: stored with today's timestamp, not the test date — rollup warnings about missing snapshot collections are expected for historical benchmarks
