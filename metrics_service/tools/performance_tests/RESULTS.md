# Metrics-Service Performance Test Results

## Scaling Comparison

Generator parameters (`fill_perf_db_data.py`): `--job-count=J --task-count=T --host-count=H`, run 4× (background + Jan 24/25/26).

| Scale  | Generator params    | Events (total) | Events (2024-01-25) | Collection time  | Peak memory | Total time |
|--------|---------------------|----------------|---------------------|------------------|-------------|------------|
| Small  | J=100, T=50, H=16   | 368,104        | 97,572              | 10.7s (0.2 min)  | 193.8 MB    | 11.3s      |
| Medium | J=1000, T=50, H=20  | 4,598,136      | 1,181,781           | 52.2s (0.9 min)  | 444.7 MB    | 52.7s      |
| Large  | J=2000, T=100, H=40 | 36,793,472     | 9,465,180           | 333.4s (5.6 min) | 2,456.8 MB  | 334.0s     |

---

## Small Run Detail

**Date of test run:** 2026-03-02

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
| Snapshot collectors | 0.55s | Run once (execution_environments, config, controller_version_service, table_metadata) |
| Hourly collection | 10.7s (0.2 min) | 24 hours × 4 collectors |
| — job_host_summary_service | 1.3s total | peak 192.9 MB |
| — unified_jobs | 1.3s total | |
| — credentials_service | 1.3s total | peak 192.9 MB |
| — main_jobevent_service | 6.8s total | peak 193.8 MB |
| Rollup | 0.06s | |
| **Total** | **11.3s (0.2 min)** | |

### Memory

| Metric | Value |
|--------|-------|
| Baseline | 140.8 MB |
| Peak | 193.8 MB |
| Delta | 53.0 MB |

> **Note:** Peak memory is RSS sampled every 50ms during task execution.

### Output Table Sizes

| Table                   | Rows | Data Size |
|-------------------------|------|-----------|
| HourlyMetricsCollection | 100  | 2.01 MB   |
| DailyMetricsSummary     | 1    | 0.01 MB   |

---

## Medium Run Detail

**Date of test run:** 2026-03-02

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
| Snapshot collectors | 0.48s | Run once (execution_environments, config, controller_version_service, table_metadata) |
| Hourly collection | 52.2s (0.9 min) | 24 hours × 4 collectors |
| — job_host_summary_service | 1.3s total | peak 396.9 MB |
| — unified_jobs | 1.3s total | |
| — credentials_service | 1.3s total | peak 396.0 MB |
| — main_jobevent_service | 48.2s total | peak 444.7 MB |
| Rollup | 0.05s | |
| **Total** | **52.7s (0.9 min)** | |

### Memory

| Metric | Value |
|--------|-------|
| Baseline | 138.6 MB |
| Peak | 444.7 MB |
| Delta | 306.1 MB |

> **Note:** Peak memory is RSS sampled every 50ms during task execution.

### Output Table Sizes

| Table                   | Rows | Data Size |
|-------------------------|------|-----------|
| HourlyMetricsCollection | 100  | 2.57 MB   |
| DailyMetricsSummary     | 1    | 0.03 MB   |

## Large Run Detail

**Date of test run:** 2026-03-02

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
| Snapshot collectors | 0.48s | Run once (execution_environments, config, controller_version_service, table_metadata) |
| Hourly collection | 333.4s (5.6 min) | 24 hours × 4 collectors |
| — job_host_summary_service | 2.6s total | peak 1,709.8 MB |
| — unified_jobs | 1.3s total | |
| — credentials_service | 1.3s total | peak 1,710.5 MB |
| — main_jobevent_service | 328.2s total | peak 2,456.8 MB |
| Rollup | 0.10s | |
| **Total** | **334.0s (5.6 min)** | |

### Memory

| Metric | Value |
|--------|-------|
| Baseline | 140.1 MB |
| Peak | 2,456.8 MB |
| Delta | 2,316.7 MB |

> **Note:** Peak memory is RSS sampled every 50ms during task execution.

### Output Table Sizes

| Table                   | Rows | Data Size |
|-------------------------|------|-----------|
| HourlyMetricsCollection | 100  | 3.32 MB   |
| DailyMetricsSummary     | 1    | 0.05 MB   |

---
