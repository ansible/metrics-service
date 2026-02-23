# Metrics-Service Performance Test Results

**Date of test run:** 2026-02-23

## Source Data

- **Test date selected:** January 25, 2024
- Total events in db: 4,599,376 events
- Events on test date: 1,264,938

## Timing Results

| Phase | Duration | Notes |
|-------|----------|-------|
| Snapshot (main_host) | 1.02s | Run once |
| Hourly collection | 16.9s (0.3 min) | 24 hours |
| — job_host_summary | 0.3s total | peak 1229.0 MB |
| — main_jobevent | 16.5s total | peak 1229.0 MB |
| Rollup | 1.07s | 1286.5 MB after |
| **Total** | **19.0s (0.3 min)** | |

## Memory

| Metric | Value |
|--------|-------|
| Baseline | 1192.6 MB |
| Peak | 1286.5 MB |
| Delta | 93.9 MB |

> **Note:** Peak memory is RSS sampled every 50ms during task execution.

## Output Table Sizes

| Table                   | Rows | Data Size |
|-------------------------|------|-----------|
| HourlyMetricsCollection | 49   | 3.51 MB   |
| DailyMetricsSummary     | 1    | 3.50 MB   |
