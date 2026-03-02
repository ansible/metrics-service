# Metrics-Service Performance Test Results

## Scaling Comparison

Generator parameters (`fill_perf_db_data.py`): `--job-count=J --task-count=T --host-count=H`, run 4× (background + Jan 24/25/26).

| Scale  | Generator params    | Events (total) | Events (2024-01-25) | Collection time  | Peak memory | Total time |
|--------|---------------------|----------------|---------------------|------------------|-------------|------------|
| Small  | J=100, T=50, H=16   | 368,104        | 97,572              | 10.3s (0.2 min)  | 211.5 MB    | 10.7s      |
| Medium | J=1000, T=50, H=20  | 4,598,136      | 1,181,781           | 51.0s (0.9 min)  | 442.3 MB    | 51.6s      |
| Large  | J=2000, T=500, H=8  | 36,791,820     | 9,464,708           | 338.4s (5.6 min) | 2,451.7 MB  | 338.9s     |

---

## Small Run Detail

**Date of test run:** 2026-02-27

### Source Data (AWX DB)

| Table               | Total rows | On test date (2024-01-25) |
|---------------------|------------|---------------------------|
| main_jobevent       | 368,104    | 97,572                    |
| main_jobhostsummary | 6,400      | —                         |
| main_host           | 64         | —                         |
| main_job            | 400        | —                         |

### Timing Results

| Phase | Duration | Notes |
|-------|----------|-------|
| Snapshot collectors | 0.37s | Run once (execution_environments, config, controller_version_service, table_metadata) |
| Hourly collection | 10.3s (0.2 min) | 24 hours × 4 collectors |
| — job_host_summary_service | 1.3s total | peak 210.5 MB |
| — unified_jobs | 1.3s total | |
| — credentials_service | 1.3s total | peak 210.5 MB |
| — main_jobevent_service | 6.3s total | peak 211.5 MB |
| Rollup | 0.05s | |
| **Total** | **10.7s (0.2 min)** | |

### Memory

| Metric | Value |
|--------|-------|
| Baseline | 170.9 MB |
| Peak | 211.5 MB |
| Delta | 40.6 MB |

> **Note:** Peak memory is RSS sampled every 50ms during task execution.

### Output Table Sizes

| Table                   | Rows | Data Size |
|-------------------------|------|-----------|
| HourlyMetricsCollection | 100  | 2.01 MB   |
| DailyMetricsSummary     | 1    | 0.01 MB   |

---

## Medium Run Detail

**Date of test run:** 2026-02-27

### Source Data (AWX DB)

| Table               | Total rows | On test date (2024-01-25) |
|---------------------|------------|---------------------------|
| main_jobevent       | 4,598,136  | 1,181,781                 |
| main_jobhostsummary | 80,000     | —                         |
| main_host           | 80         | —                         |
| main_job            | 4,000      | —                         |

### Timing Results

| Phase | Duration | Notes |
|-------|----------|-------|
| Snapshot collectors | 0.53s | Run once (execution_environments, config, controller_version_service, table_metadata) |
| Hourly collection | 51.0s (0.9 min) | 24 hours × 4 collectors |
| — job_host_summary_service | 1.4s total | peak 386.8 MB |
| — unified_jobs | 1.3s total | |
| — credentials_service | 1.3s total | peak 386.8 MB |
| — main_jobevent_service | 47.0s total | peak 442.3 MB |
| Rollup | 0.05s | |
| **Total** | **51.6s (0.9 min)** | |

### Memory

| Metric | Value |
|--------|-------|
| Baseline | 139.3 MB |
| Peak | 442.3 MB |
| Delta | 303.0 MB |

> **Note:** Peak memory is RSS sampled every 50ms during task execution.

### Output Table Sizes

| Table                   | Rows | Data Size |
|-------------------------|------|-----------|
| HourlyMetricsCollection | 100  | 2.57 MB   |
| DailyMetricsSummary     | 1    | 0.03 MB   |

## Large Run Detail

**Date of test run:** 2026-02-27

### Source Data (AWX DB)

| Table               | Total rows | On test date (2024-01-25) |
|---------------------|------------|---------------------------|
| main_jobevent       | 36,791,820 | 9,464,708                 |
| main_jobhostsummary | 64,000     | —                         |
| main_host           | 32         | —                         |
| main_job            | 8,000      | —                         |

### Timing Results

| Phase | Duration | Notes |
|-------|----------|-------|
| Snapshot collectors | 0.43s | Run once (execution_environments, config, controller_version_service, table_metadata) |
| Hourly collection | 338.4s (5.6 min) | 24 hours × 4 collectors |
| — job_host_summary_service | 1.6s total | peak 1,625.1 MB |
| — unified_jobs | 1.3s total | |
| — credentials_service | 1.3s total | peak 1,625.1 MB |
| — main_jobevent_service | 334.2s total | peak 2,451.7 MB |
| Rollup | 0.11s | |
| **Total** | **338.9s (5.6 min)** | |

### Memory

| Metric | Value |
|--------|-------|
| Baseline | 138.6 MB |
| Peak | 2,451.7 MB |
| Delta | 2,313.1 MB |

> **Note:** Peak memory is RSS sampled every 50ms during task execution.

### Output Table Sizes

| Table                   | Rows | Data Size |
|-------------------------|------|-----------|
| HourlyMetricsCollection | 100  | 2.36 MB   |
| DailyMetricsSummary     | 1    | 0.04 MB   |

---
