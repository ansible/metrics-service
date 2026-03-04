# Metrics-Service Performance Test Results

## Scaling Comparison

Generator parameters (`fill_perf_db_data.py`): `--job-count=J --task-count=T --host-count=H`, run 4× (background + Jan 24/25/26).

| Scale  | Generator params    | Events (total) | Events (2024-01-25) | Collection time  | Peak memory | Total time |
|--------|---------------------|----------------|---------------------|------------------|-------------|------------|
| Small  | J=100, T=50, H=16   | 368,104        | 97,572              | 10.1s (0.2 min)  | 186.2 MB    | 10.6s      |
| Medium | J=1000, T=50, H=20  | 4,598,136      | 1,181,781           | 55.7s (0.9 min)  | 460.2 MB    | 56.3s      |
| Large  | J=2000, T=100, H=40 | 36,793,472     | 9,465,180           | 348.3s (5.8 min) | 2,465.8 MB  | 349.0s     |

---

## Small Run Detail

**Date of test run:** 2026-03-04

### Source Data (AWX DB)

| Table                       | Total rows | On test date (2024-01-25) |
|-----------------------------|------------|---------------------------|
| main_jobevent               | 368,104    | 97,572                    |
| main_jobhostsummary         | 6,400      | —                         |
| main_host                   | 64         | —                         |
| main_unifiedjob             | 400        | —                         |
| main_job                    | 400        | —                         |
| main_unifiedjobtemplate     | 44         | —                         |
| main_inventory              | 4          | —                         |
| main_organization           | 4          | —                         |
| main_credential             | 0          | —                         |
| main_credentialtype         | 5          | —                         |
| main_unifiedjob_credentials | 0          | —                         |
| main_executionenvironment   | 0          | —                         |

### Timing Results

| Phase | Duration | Notes |
|-------|----------|-------|
| Snapshot collectors | 0.43s | Run once (execution_environments, config, controller_version_service, table_metadata) |
| Hourly collection | 10.1s (0.2 min) | 24 hours × 4 collectors |
| — job_host_summary_service | 1.3s total | peak 185.3 MB |
| — unified_jobs | 1.3s total | peak 185.3 MB |
| — credentials_service | 1.3s total | peak 184.9 MB |
| — main_jobevent_service | 6.2s total | peak 186.2 MB |
| Rollup | 0.05s | |
| **Total** | **10.6s (0.2 min)** | |

### Memory

| Metric | Value |
|--------|-------|
| Baseline | 140.3 MB |
| Peak | 186.2 MB |
| Delta | 46.0 MB |

> **Note:** Peak memory is RSS sampled every 50ms during task execution.

### Output Table Sizes

| Table                   | Rows | Data Size |
|-------------------------|------|-----------|
| HourlyMetricsCollection | 100  | 2.08 MB   |
| DailyMetricsSummary     | 1    | 0.00 MB   |

---

## Medium Run Detail

**Date of test run:** 2026-03-04

### Source Data (AWX DB)

| Table                       | Total rows | On test date (2024-01-25) |
|-----------------------------|------------|---------------------------|
| main_jobevent               | 4,598,136  | 1,181,781                 |
| main_jobhostsummary         | 80,000     | —                         |
| main_host                   | 80         | —                         |
| main_unifiedjob             | 4,000      | —                         |
| main_job                    | 4,000      | —                         |
| main_unifiedjobtemplate     | 44         | —                         |
| main_inventory              | 4          | —                         |
| main_organization           | 4          | —                         |
| main_credential             | 0          | —                         |
| main_credentialtype         | 5          | —                         |
| main_unifiedjob_credentials | 0          | —                         |
| main_executionenvironment   | 0          | —                         |

### Timing Results

| Phase | Duration | Notes |
|-------|----------|-------|
| Snapshot collectors | 0.58s | Run once (execution_environments, config, controller_version_service, table_metadata) |
| Hourly collection | 55.7s (0.9 min) | 24 hours × 4 collectors |
| — job_host_summary_service | 1.4s total | peak 420.2 MB |
| — unified_jobs | 1.3s total | peak 420.2 MB |
| — credentials_service | 1.3s total | peak 420.2 MB |
| — main_jobevent_service | 51.7s total | peak 460.2 MB |
| Rollup | 0.05s | |
| **Total** | **56.3s (0.9 min)** | |

### Memory

| Metric | Value |
|--------|-------|
| Baseline | 139.1 MB |
| Peak | 460.2 MB |
| Delta | 321.1 MB |

> **Note:** Peak memory is RSS sampled every 50ms during task execution.

### Output Table Sizes

| Table                   | Rows | Data Size |
|-------------------------|------|-----------|
| HourlyMetricsCollection | 100  | 2.66 MB   |
| DailyMetricsSummary     | 1    | 0.00 MB   |

## Large Run Detail

**Date of test run:** 2026-03-04

### Source Data (AWX DB)

| Table                       | Total rows | On test date (2024-01-25) |
|-----------------------------|------------|---------------------------|
| main_jobevent               | 36,793,472 | 9,465,180                 |
| main_jobhostsummary         | 320,000    | —                         |
| main_host                   | 160        | —                         |
| main_unifiedjob             | 8,000      | —                         |
| main_job                    | 8,000      | —                         |
| main_unifiedjobtemplate     | 44         | —                         |
| main_inventory              | 4          | —                         |
| main_organization           | 4          | —                         |
| main_credential             | 0          | —                         |
| main_credentialtype         | 5          | —                         |
| main_unifiedjob_credentials | 0          | —                         |
| main_executionenvironment   | 0          | —                         |

### Timing Results

| Phase | Duration | Notes |
|-------|----------|-------|
| Snapshot collectors | 0.64s | Run once (execution_environments, config, controller_version_service, table_metadata) |
| Hourly collection | 348.3s (5.8 min) | 24 hours × 4 collectors |
| — job_host_summary_service | 2.6s total | peak 1,715.1 MB |
| — unified_jobs | 1.3s total | peak 1,714.1 MB |
| — credentials_service | 1.3s total | peak 1,714.5 MB |
| — main_jobevent_service | 343.0s total | peak 2,465.8 MB |
| Rollup | 0.11s | |
| **Total** | **349.0s (5.8 min)** | |

### Memory

| Metric | Value |
|--------|-------|
| Baseline | 140.4 MB |
| Peak | 2,465.8 MB |
| Delta | 2,325.4 MB |

> **Note:** Peak memory is RSS sampled every 50ms during task execution.

### Output Table Sizes

| Table                   | Rows | Data Size |
|-------------------------|------|-----------|
| HourlyMetricsCollection | 100  | 3.50 MB   |
| DailyMetricsSummary     | 1    | 0.00 MB   |

---
