# Metrics-Service Jenkins Pipeline Benchmark Results (Scaled Up)

Tests the full collection + rollup pipeline on a containerized AIO Jenkins
deployment, using `benchmark_manage.py` via `podman exec` (direct Python calls
inside the container). Duration is wall-clock time measured by `time.perf_counter()`.
Memory is peak RSS sampled every 50ms by a background thread.

Each scale uses a fresh Jenkins instance.

## Scaling Summary

| Scale   | Jobs    | Hosts | Snapshot | Hourly | Daily rollup | Total | Baseline MB | Peak MB | Delta MB |
| ------- | ------- | ----- | -------- | ------ | ------------ | ----- | ----------- | ------- | -------- |
| Scale 1 | 2,500   | 5     | 0.55s    | 13.4s  | 2.78s        | 16.8s | 129.5 MB    | 315.8 MB | 186.3 MB |
| Scale 2 | 25,000  | 5     | 0.55s    | 30.8s  | 3.88s        | 35.2s | 129.3 MB    | 456.8 MB | 327.5 MB |
| Scale 3 | 250,000 | 5     |          |        |              |       |             |         |          |
| Scale 4 | 25,000  | 50    |          |        |              |       |             |         |          |

---

## Scale 1 Detail

**Date of test run:** 2026-04-17
**Scale:** J=2,500, H=5 (no events)
**Environment:** AIO containerized Jenkins deployment
**Test date:** 2024-01-25

### Summary

| Phase               | Duration  | Peak MB  |
| ------------------- | --------- | -------- |
| Snapshot collectors | 0.55s     | 135.3 MB |
| Hourly collection   | 13.4s     | 155.7 MB |
| Daily rollup        | 2.78s     | 315.8 MB |
| **Total**           | **16.8s** |          |

| Baseline MB | Peak MB  | Delta MB |
| ----------- | -------- | -------- |
| 129.5 MB    | 315.8 MB | 186.3 MB |

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
| job_host_summary_service  | 2.89s          | 12,900 (main_jobhostsummary rows)           |
| unified_jobs              | 9.34s          | 2,580 (main_unifiedjob rows)                |
| credentials_service       | 1.20s          | 10,320 (main_unifiedjob_credentials rows)   |

---

## Scale 2 Detail

**Date of test run:** 2026-04-16
**Scale:** J=25,000, H=5 (no events)
**Environment:** AIO containerized Jenkins deployment
**Test date:** 2024-01-25

### Summary

| Phase               | Duration | Peak MB  |
| ------------------- | -------- | -------- |
| Snapshot collectors | 0.55s    | 135.0 MB |
| Hourly collection   | 30.8s    | 171.3 MB |
| Daily rollup        | 3.88s    | 456.8 MB |
| **Total**           | **35.2s** |         |

| Baseline MB | Peak MB  | Delta MB |
| ----------- | -------- | -------- |
| 129.3 MB    | 456.8 MB | 327.5 MB |

### Output Table Sizes

| Table                   | Rows | Size (MB) |
| ----------------------- | ---- | --------- |
| HourlyMetricsCollection | 76   | 73.10     |
| DailyMetricsSummary     | 1    | 3.39      |

### Source Table Counts (AWX DB)

| Table                       | Total (all time) | Test date total      |
| --------------------------- | ---------------- | -------------------- |
| main_unifiedjob             | 100,035          | 25,832               |
| main_jobhostsummary         | 500,310          | 129,160 (5 per job)  |
| main_unifiedjob_credentials | 400,001          | 103,328 (4 per job)  |
| main_host                   | 34               |                      |
| main_job                    | 100,023          |                      |
| main_unifiedjobtemplate     | 76               |                      |
| main_inventory              | 16               |                      |
| main_organization           | 27               |                      |
| main_credential             | 35               |                      |
| main_credentialtype         | 32               |                      |
| main_executionenvironment   | 408              |                      |

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
| job_host_summary_service  |                | 129,160 (main_jobhostsummary rows)          |
| unified_jobs              |                | 25,832 (main_unifiedjob rows)               |
| credentials_service       |                | 103,328 (main_unifiedjob_credentials rows)  |

---

## Scale 3 Detail

**Date of test run:** TBD
**Scale:** J=250,000, H=5 (no events)
**Environment:** AIO containerized Jenkins deployment
**Test date:** 2024-01-25

### Summary

| Phase               | Duration | Peak MB |
| ------------------- | -------- | ------- |
| Snapshot collectors |          |         |
| Hourly collection   |          |         |
| Daily rollup        |          |         |
| **Total**           |          |         |

| Baseline MB | Peak MB | Delta MB |
| ----------- | ------- | -------- |
|             |         |          |

### Output Table Sizes

| Table                    | Rows | Size (MB) |
| ------------------------ | ---- | --------- |
| HourlyMetricsCollection  |      |           |
| DailyMetricsSummary      |      |           |

### Source Table Counts (AWX DB)

| Table                        | Total (all time) | Test date total        |
| ---------------------------- | ---------------- | ---------------------- |
| main_unifiedjob              |                  |                        |
| main_jobhostsummary          |                  | (N per job)            |
| main_unifiedjob_credentials  |                  | (N per job)            |
| main_host                    |                  |                        |
| main_job                     |                  |                        |
| main_unifiedjobtemplate      |                  |                        |
| main_inventory               |                  |                        |
| main_organization            |                  |                        |
| main_credential              |                  |                        |
| main_credentialtype          |                  |                        |
| main_executionenvironment    |                  |                        |

### Jobs Finished Per Hour (2024-01-25)

| Hour | Jobs |
| ---- | ---- |
| 0    |      |
| 1    |      |
| 2    |      |
| 3    |      |
| 4    |      |
| 5    |      |
| 6    |      |
| 7    |      |
| 8    |      |
| 9    |      |
| 10   |      |
| 11   |      |
| 12   |      |
| 13   |      |
| 14   |      |
| 15   |      |
| 16   |      |
| 17   |      |
| 18   |      |
| 19   |      |
| 20   |      |
| 21   |      |
| 22   |      |
| 23   |      |

### Per-Collector Summary (24 hours total)

| Collector                 | Total duration | Rows processed                              |
| ------------------------- | -------------- | ------------------------------------------- |
| job_host_summary_service  |                | (main_jobhostsummary rows)                  |
| unified_jobs              |                | (main_unifiedjob rows)                      |
| credentials_service       |                | (main_unifiedjob_credentials rows)          |

---

## Scale 4 Detail

**Date of test run:** TBD
**Scale:** J=25,000, H=50 (no events)
**Environment:** AIO containerized Jenkins deployment
**Test date:** 2024-01-25

### Summary

| Phase               | Duration | Peak MB |
| ------------------- | -------- | ------- |
| Snapshot collectors |          |         |
| Hourly collection   |          |         |
| Daily rollup        |          |         |
| **Total**           |          |         |

| Baseline MB | Peak MB | Delta MB |
| ----------- | ------- | -------- |
|             |         |          |

### Output Table Sizes

| Table                    | Rows | Size (MB) |
| ------------------------ | ---- | --------- |
| HourlyMetricsCollection  |      |           |
| DailyMetricsSummary      |      |           |

### Source Table Counts (AWX DB)

| Table                        | Total (all time) | Test date total        |
| ---------------------------- | ---------------- | ---------------------- |
| main_unifiedjob              |                  |                        |
| main_jobhostsummary          |                  | (N per job)            |
| main_unifiedjob_credentials  |                  | (N per job)            |
| main_host                    |                  |                        |
| main_job                     |                  |                        |
| main_unifiedjobtemplate      |                  |                        |
| main_inventory               |                  |                        |
| main_organization            |                  |                        |
| main_credential              |                  |                        |
| main_credentialtype          |                  |                        |
| main_executionenvironment    |                  |                        |

### Jobs Finished Per Hour (2024-01-25)

| Hour | Jobs |
| ---- | ---- |
| 0    |      |
| 1    |      |
| 2    |      |
| 3    |      |
| 4    |      |
| 5    |      |
| 6    |      |
| 7    |      |
| 8    |      |
| 9    |      |
| 10   |      |
| 11   |      |
| 12   |      |
| 13   |      |
| 14   |      |
| 15   |      |
| 16   |      |
| 17   |      |
| 18   |      |
| 19   |      |
| 20   |      |
| 21   |      |
| 22   |      |
| 23   |      |

### Per-Collector Summary (24 hours total)

| Collector                 | Total duration | Rows processed                              |
| ------------------------- | -------------- | ------------------------------------------- |
| job_host_summary_service  |                | (main_jobhostsummary rows)                  |
| unified_jobs              |                | (main_unifiedjob rows)                      |
| credentials_service       |                | (main_unifiedjob_credentials rows)          |

---
