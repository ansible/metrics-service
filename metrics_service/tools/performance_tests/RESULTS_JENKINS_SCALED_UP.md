# Metrics-Service Jenkins Pipeline Benchmark Results (Scaled Up)

Tests the full collection + rollup pipeline on a containerized AIO Jenkins
deployment, using `benchmark_manage.py` via `podman exec` (direct Python calls
inside the container). Duration is wall-clock time measured by `time.perf_counter()`.
Memory is peak RSS sampled every 50ms by a background thread.

Each scale uses a fresh Jenkins instance.

## Scaling Summary

| Scale   | Jobs    | Hosts | Snapshot | Hourly | Daily rollup | Total | Baseline MB | Peak MB | Delta MB |
| ------- | ------- | ----- | -------- | ------ | ------------ | ----- | ----------- | ------- | -------- |
| Scale 1 | 2,500   | 5     | 0.55s    | 13.7s  | 3.13s        | 17.4s | 129.3 MB    | 299.4 MB | 170.1 MB |
| Scale 2 | 25,000  | 5     | 0.45s    | 29.5s  | 3.31s        | 33.3s | 129.2 MB    | 447.8 MB | 318.6 MB |
| Scale 3 | 250,000 | 5     | 0.50s    | 152.1s | 3.78s        | 156.4s | 129.4 MB   | 501.0 MB | 371.5 MB |
| Scale 4 | 25,000  | 50    | 0.56s    | 59.2s  | 4.12s        | 63.9s | 129.8 MB    | 425.3 MB | 295.5 MB |

---

## Scale 1 Detail

**Date of test run:** 2026-04-17
**Scale:** J=2,500, H=5 (no events)
**Environment:** AIO containerized Jenkins deployment
**Test date:** 2024-01-25

### Summary

| Phase               | Duration  | Peak MB  |
| ------------------- | --------- | -------- |
| Snapshot collectors | 0.55s     | 135.2 MB |
| Hourly collection   | 13.7s     | 156.0 MB |
| Daily rollup        | 3.13s     | 299.4 MB |
| **Total**           | **17.4s** |          |

| Baseline MB | Peak MB  | Delta MB |
| ----------- | -------- | -------- |
| 129.3 MB    | 299.4 MB | 170.1 MB |

### Output Table Sizes

| Table                   | Rows | Size (MB) |
| ----------------------- | ---- | --------- |
| HourlyMetricsCollection | 76   | 45.69     |
| DailyMetricsSummary     | 1    | 3.13      |

### Source Table Counts (AWX DB)

| Table                       | Total (all time) | Test date total     |
| --------------------------- | ---------------- | ------------------- |
| main_unifiedjob             | 10,000           | 2,580               |
| main_jobhostsummary         | 50,000           | 12,900 (5 per job)  |
| main_unifiedjob_credentials | 40,000           | 10,320 (4 per job)  |
| main_host                   | 21               |                     |
| main_job                    | 10,000           |                     |
| main_unifiedjobtemplate     | 49               |                     |
| main_inventory              | 5                |                     |
| main_organization           | 5                |                     |
| main_credential             | 18               |                     |
| main_credentialtype         | 32               |                     |
| main_executionenvironment   | 405              |                     |

### Jobs Finished Per Hour (2024-01-25)

| Hour | Jobs |
| ---- | ---- |
| 0    | 24   |
| 1    | 80   |
| 2    | 129  |
| 3    | 140  |
| 4    | 128  |
| 5    | 107  |
| 6    | 118  |
| 7    | 118  |
| 8    | 116  |
| 9    | 90   |
| 10   | 113  |
| 11   | 112  |
| 12   | 130  |
| 13   | 110  |
| 14   | 127  |
| 15   | 119  |
| 16   | 96   |
| 17   | 125  |
| 18   | 124  |
| 19   | 131  |
| 20   | 122  |
| 21   | 112  |
| 22   | 91   |
| 23   | 18   |

### Per-Collector Summary (24 hours total)

| Collector                 | Total duration | Rows processed                              |
| ------------------------- | -------------- | ------------------------------------------- |
| job_host_summary_service  | 2.87s          | 12,900 (main_jobhostsummary rows)           |
| unified_jobs              | 9.59s          | 2,580 (main_unifiedjob rows)                |
| credentials_service       | 1.22s          | 10,320 (main_unifiedjob_credentials rows)   |

---

## Scale 2 Detail

**Date of test run:** 2026-04-17
**Scale:** J=25,000, H=5 (no events)
**Environment:** AIO containerized Jenkins deployment
**Test date:** 2024-01-25

### Summary

| Phase               | Duration  | Peak MB  |
| ------------------- | --------- | -------- |
| Snapshot collectors | 0.45s     | 135.4 MB |
| Hourly collection   | 29.5s     | 171.1 MB |
| Daily rollup        | 3.31s     | 447.8 MB |
| **Total**           | **33.3s** |          |

| Baseline MB | Peak MB  | Delta MB |
| ----------- | -------- | -------- |
| 129.2 MB    | 447.8 MB | 318.6 MB |

### Output Table Sizes

| Table                   | Rows | Size (MB) |
| ----------------------- | ---- | --------- |
| HourlyMetricsCollection | 76   | 72.24     |
| DailyMetricsSummary     | 1    | 3.31      |

### Source Table Counts (AWX DB)

| Table                       | Total (all time) | Test date total      |
| --------------------------- | ---------------- | -------------------- |
| main_unifiedjob             | 100,000          | 25,832               |
| main_jobhostsummary         | 500,000          | 129,160 (5 per job)  |
| main_unifiedjob_credentials | 400,000          | 103,328 (4 per job)  |
| main_host                   | 21               |                      |
| main_job                    | 100,000          |                      |
| main_unifiedjobtemplate     | 49               |                      |
| main_inventory              | 5                |                      |
| main_organization           | 5                |                      |
| main_credential             | 18               |                      |
| main_credentialtype         | 32               |                      |
| main_executionenvironment   | 405              |                      |

### Jobs Finished Per Hour (2024-01-25)

| Hour | Jobs  |
| ---- | ----- |
| 0    | 227   |
| 1    | 963   |
| 2    | 1,201 |
| 3    | 1,189 |
| 4    | 1,172 |
| 5    | 1,201 |
| 6    | 1,131 |
| 7    | 1,160 |
| 8    | 1,177 |
| 9    | 1,166 |
| 10   | 1,198 |
| 11   | 1,087 |
| 12   | 1,173 |
| 13   | 1,173 |
| 14   | 1,164 |
| 15   | 1,189 |
| 16   | 1,162 |
| 17   | 1,228 |
| 18   | 1,143 |
| 19   | 1,210 |
| 20   | 1,135 |
| 21   | 1,150 |
| 22   | 1,004 |
| 23   | 229   |

### Per-Collector Summary (24 hours total)

| Collector                 | Total duration | Rows processed                              |
| ------------------------- | -------------- | ------------------------------------------- |
| job_host_summary_service  | 11.16s         | 129,160 (main_jobhostsummary rows)          |
| unified_jobs              | 17.12s         | 25,832 (main_unifiedjob rows)               |
| credentials_service       | 1.21s          | 103,328 (main_unifiedjob_credentials rows)  |

---

## Scale 3 Detail

**Date of test run:** 2026-04-19
**Scale:** J=250,000, H=5 (no events)
**Environment:** AIO containerized Jenkins deployment
**Test date:** 2024-01-25

### Summary

| Phase               | Duration   | Peak MB  |
| ------------------- | ---------- | -------- |
| Snapshot collectors | 0.50s      | 135.4 MB |
| Hourly collection   | 152.1s     | 282.1 MB |
| Daily rollup        | 3.78s      | 501.0 MB |
| **Total**           | **156.4s** |          |

| Baseline MB | Peak MB  | Delta MB |
| ----------- | -------- | -------- |
| 129.4 MB    | 501.0 MB | 371.5 MB |

### Output Table Sizes

| Table                   | Rows | Size (MB) |
| ----------------------- | ---- | --------- |
| HourlyMetricsCollection | 72   | 76.34     |
| DailyMetricsSummary     | 1    | 3.43      |

### Source Table Counts (AWX DB)

| Table                       | Total (all time) | Test date total            |
| --------------------------- | ---------------- | -------------------------- |
| main_unifiedjob             | 848,034          | 253,311                    |
| main_jobhostsummary         | 4,240,160        | 1,266,555 (5 per job)      |
| main_unifiedjob_credentials | 3,392,128        | 1,013,244 (4 per job)      |
| main_host                   | 21               |                            |
| main_job                    | 848,032          |                            |
| main_unifiedjobtemplate     | 49               |                            |
| main_inventory              | 5                |                            |
| main_organization           | 5                |                            |
| main_credential             | 18               |                            |
| main_credentialtype         | 32               |                            |
| main_executionenvironment   | 405              |                            |

### Jobs Finished Per Hour (2024-01-25)

| Hour | Jobs   |
| ---- | ------ |
| 0    | 1,975  |
| 1    | 9,596  |
| 2    | 11,513 |
| 3    | 11,678 |
| 4    | 11,510 |
| 5    | 11,377 |
| 6    | 11,433 |
| 7    | 11,477 |
| 8    | 11,471 |
| 9    | 11,432 |
| 10   | 11,711 |
| 11   | 11,526 |
| 12   | 11,520 |
| 13   | 11,394 |
| 14   | 11,429 |
| 15   | 11,560 |
| 16   | 11,259 |
| 17   | 11,471 |
| 18   | 11,684 |
| 19   | 11,656 |
| 20   | 11,400 |
| 21   | 11,499 |
| 22   | 9,640  |
| 23   | 2,100  |

### Per-Collector Summary (24 hours total)

| Collector                | Total duration | Rows processed                             |
| ------------------------ | -------------- | ------------------------------------------ |
| job_host_summary_service | 94.52s         | 1,266,555 (main_jobhostsummary rows)       |
| unified_jobs             | 56.37s         | 253,311 (main_unifiedjob rows)             |
| credentials_service      | 1.22s          | 1,013,244 (main_unifiedjob_credentials rows) |

---

## Scale 4 Detail

**Date of test run:** 2026-04-17
**Scale:** J=25,000, H=50 (no events)
**Environment:** AIO containerized Jenkins deployment
**Test date:** 2024-01-25

### Summary

| Phase               | Duration  | Peak MB  |
| ------------------- | --------- | -------- |
| Snapshot collectors | 0.56s     | 135.4 MB |
| Hourly collection   | 59.2s     | 288.4 MB |
| Daily rollup        | 4.12s     | 425.3 MB |
| **Total**           | **63.9s** |          |

| Baseline MB | Peak MB  | Delta MB |
| ----------- | -------- | -------- |
| 129.8 MB    | 425.3 MB | 295.5 MB |

### Output Table Sizes

| Table                   | Rows | Size (MB) |
| ----------------------- | ---- | --------- |
| HourlyMetricsCollection | 76   | 72.21     |
| DailyMetricsSummary     | 1    | 3.30      |

### Source Table Counts (AWX DB)

| Table                       | Total (all time) | Test date total           |
| --------------------------- | ---------------- | ------------------------- |
| main_unifiedjob             | 100,000          | 25,832                    |
| main_jobhostsummary         | 5,000,000        | 1,291,600 (50 per job)    |
| main_unifiedjob_credentials | 400,000          | 103,328 (4 per job)       |
| main_host                   | 201              |                           |
| main_job                    | 100,000          |                           |
| main_unifiedjobtemplate     | 49               |                           |
| main_inventory              | 5                |                           |
| main_organization           | 5                |                           |
| main_credential             | 18               |                           |
| main_credentialtype         | 32               |                           |
| main_executionenvironment   | 405              |                           |

### Jobs Finished Per Hour (2024-01-25)

| Hour | Jobs  |
| ---- | ----- |
| 0    | 227   |
| 1    | 963   |
| 2    | 1,201 |
| 3    | 1,189 |
| 4    | 1,172 |
| 5    | 1,201 |
| 6    | 1,131 |
| 7    | 1,160 |
| 8    | 1,177 |
| 9    | 1,166 |
| 10   | 1,198 |
| 11   | 1,087 |
| 12   | 1,173 |
| 13   | 1,173 |
| 14   | 1,164 |
| 15   | 1,189 |
| 16   | 1,162 |
| 17   | 1,228 |
| 18   | 1,143 |
| 19   | 1,210 |
| 20   | 1,135 |
| 21   | 1,150 |
| 22   | 1,004 |
| 23   | 229   |

### Per-Collector Summary (24 hours total)

| Collector                 | Total duration | Rows processed                                |
| ------------------------- | -------------- | --------------------------------------------- |
| job_host_summary_service  | 39.42s         | 1,291,600 (main_jobhostsummary rows)          |
| unified_jobs              | 18.60s         | 25,832 (main_unifiedjob rows)                 |
| credentials_service       | 1.22s          | 103,328 (main_unifiedjob_credentials rows)    |

---
