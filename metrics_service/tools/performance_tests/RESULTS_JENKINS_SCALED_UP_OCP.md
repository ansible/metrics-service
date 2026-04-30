# Metrics-Service Jenkins Pipeline Benchmark Results (Scaled Up, OCP)

Tests the full collection + rollup pipeline on an OCP Jenkins deployment,
using `benchmark_manage.py` via `oc exec` (direct Python calls inside the
container). Duration is wall-clock time measured by `time.perf_counter()`.
Memory is peak RSS sampled every 50ms by a background thread.

Each scale uses a fresh Jenkins instance.

## Scaling Summary

| Scale   | Jobs    | Hosts | Snapshot | Hourly | Daily rollup | Total | Baseline MB | Peak MB | Delta MB |
| ------- | ------- | ----- | -------- | ------ | ------------ | ----- | ----------- | ------- | -------- |
| Scale 1 | 2,500   | 5     | 0.71s    | 20.1s  | 4.88s        | 25.7s | 134.4 MB    | 326.3 MB | 191.8 MB |
| Scale 2 | 25,000  | 5     | 0.81s    | 56.9s  | 6.70s        | 64.4s | 129.8 MB    | 456.2 MB | 326.3 MB |
| Scale 3 | 250,000 | 5     | 0.86s    | 302.5s | 7.12s        | 310.4s | 132.3 MB   | 468.6 MB | 336.3 MB |
| Scale 4 | 25,000  | 50    | 0.31s    | 92.6s  | 5.76s        | 98.7s | 132.4 MB    | 450.4 MB | 318.1 MB |

---

## Scale 1 Detail

**Date of test run:** 2026-04-28
**Scale:** J=2,500, H=5 (no events)
**Environment:** OCP Jenkins deployment

### Summary

| Phase               | Duration  | Peak MB  |
| ------------------- | --------- | -------- |
| Snapshot collectors | 0.71s     | 134.4 MB |
| Hourly collection   | 20.1s     | 326.3 MB |
| Daily rollup        | 4.88s     | 326.3 MB |
| **Total**           | **25.7s** |          |

| Baseline MB | Peak MB  | Delta MB |
| ----------- | -------- | -------- |
| 134.4 MB    | 326.3 MB | 191.8 MB |

### Output Table Sizes

| Table                   | Rows | Size (MB) |
| ----------------------- | ---- | --------- |
| HourlyMetricsCollection | 76   | 45.76     |
| DailyMetricsSummary     | 1    | 3.14      |

### Source Table Counts (AWX DB)

| Table                       | Total (all time) | Test date total     |
| --------------------------- | ---------------- | ------------------- |
| main_unifiedjob             | 10,516           | 2,580               |
| main_jobhostsummary         | 52,561           | 12,900 (5 per job)  |
| main_unifiedjob_credentials | 41,972           | 10,320 (4 per job)  |
| main_host                   | 26               |                     |
| main_job                    | 10,515           |                     |
| main_unifiedjobtemplate     | 61               |                     |
| main_inventory              | 6                |                     |
| main_organization           | 6                |                     |
| main_credential             | 22               |                     |
| main_credentialtype         | 32               |                     |
| main_executionenvironment   | 503              |                     |

### Jobs Finished Per Hour

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

| Collector                 | Total duration | Rows processed                            |
| ------------------------- | -------------- | ----------------------------------------- |
| job_host_summary_service  | 4.13s          | 12,900 (main_jobhostsummary rows)         |
| unified_jobs              | 14.74s         | 2,580 (main_unifiedjob rows)              |
| credentials_service       | 1.23s          | 10,320 (main_unifiedjob_credentials rows) |

---

## Scale 2 Detail

**Date of test run:** 2026-04-29
**Scale:** J=25,000, H=5 (no events)
**Environment:** OCP Jenkins deployment

### Summary

| Phase               | Duration  | Peak MB  |
| ------------------- | --------- | -------- |
| Snapshot collectors | 0.81s     | 133.6 MB |
| Hourly collection   | 56.9s     | 456.2 MB |
| Daily rollup        | 6.70s     | 456.2 MB |
| **Total**           | **64.4s** |          |

| Baseline MB | Peak MB  | Delta MB |
| ----------- | -------- | -------- |
| 129.8 MB    | 456.2 MB | 326.3 MB |

### Output Table Sizes

| Table                   | Rows | Size (MB) |
| ----------------------- | ---- | --------- |
| HourlyMetricsCollection | 76   | 72.65     |
| DailyMetricsSummary     | 1    | 3.49      |

### Source Table Counts (AWX DB)

| Table                       | Total (all time) | Test date total          |
| --------------------------- | ---------------- | ------------------------ |
| main_unifiedjob             | 134,207          | 26,664                   |
| main_jobhostsummary         | 671,031          | 133,320 (5 per job)      |
| main_unifiedjob_credentials | 536,820          | 106,656 (4 per job)      |
| main_host                   | 37               |                          |
| main_job                    | 134,207          |                          |
| main_unifiedjobtemplate     | 94               |                          |
| main_inventory              | 9                |                          |
| main_organization           | 9                |                          |
| main_credential             | 34               |                          |
| main_credentialtype         | 32               |                          |
| main_executionenvironment   | 803              |                          |

### Jobs Finished Per Hour

| Hour | Jobs  |
| ---- | ----- |
| 0    | 273   |
| 1    | 999   |
| 2    | 1,232 |
| 3    | 1,223 |
| 4    | 1,215 |
| 5    | 1,238 |
| 6    | 1,160 |
| 7    | 1,187 |
| 8    | 1,203 |
| 9    | 1,205 |
| 10   | 1,238 |
| 11   | 1,120 |
| 12   | 1,210 |
| 13   | 1,214 |
| 14   | 1,194 |
| 15   | 1,222 |
| 16   | 1,193 |
| 17   | 1,265 |
| 18   | 1,177 |
| 19   | 1,250 |
| 20   | 1,161 |
| 21   | 1,182 |
| 22   | 1,047 |
| 23   | 256   |

### Per-Collector Summary (24 hours total)

| Collector                 | Total duration | Rows processed                              |
| ------------------------- | -------------- | ------------------------------------------- |
| job_host_summary_service  | 23.10s         | 133,320 (main_jobhostsummary rows)          |
| unified_jobs              | 32.53s         | 26,664 (main_unifiedjob rows)               |
| credentials_service       | 1.23s          | 106,656 (main_unifiedjob_credentials rows)  |

---

## Scale 3 Detail

**Date of test run:** 2026-04-29
**Scale:** J=250,000, H=5 (no events)
**Environment:** OCP Jenkins deployment

### Summary

| Phase               | Duration   | Peak MB  |
| ------------------- | ---------- | -------- |
| Snapshot collectors | 0.86s      | 136.0 MB |
| Hourly collection   | 302.5s     | 468.6 MB |
| Daily rollup        | 7.12s      | 468.6 MB |
| **Total**           | **310.4s** |          |

| Baseline MB | Peak MB  | Delta MB |
| ----------- | -------- | -------- |
| 132.3 MB    | 468.6 MB | 336.3 MB |

### Output Table Sizes

| Table                   | Rows | Size (MB) |
| ----------------------- | ---- | --------- |
| HourlyMetricsCollection | 77   | 76.34     |
| DailyMetricsSummary     | 1    | 3.67      |

### Source Table Counts (AWX DB)

| Table                       | Total (all time) | Test date total              |
| --------------------------- | ---------------- | ---------------------------- |
| main_unifiedjob             | 1,079,608        | 252,680                      |
| main_jobhostsummary         | 5,398,035        | 1,263,400 (5 per job)        |
| main_unifiedjob_credentials | 4,318,420        | 1,010,720 (4 per job)        |
| main_host                   | 41               |                              |
| main_job                    | 1,079,607        |                              |
| main_unifiedjobtemplate     | 94               |                              |
| main_inventory              | 9                |                              |
| main_organization           | 9                |                              |
| main_credential             | 34               |                              |
| main_credentialtype         | 32               |                              |
| main_executionenvironment   | 803              |                              |

### Jobs Finished Per Hour

| Hour | Jobs   |
| ---- | ------ |
| 0    | 1,972  |
| 1    | 9,588  |
| 2    | 11,475 |
| 3    | 11,648 |
| 4    | 11,500 |
| 5    | 11,352 |
| 6    | 11,369 |
| 7    | 11,445 |
| 8    | 11,435 |
| 9    | 11,401 |
| 10   | 11,708 |
| 11   | 11,499 |
| 12   | 11,512 |
| 13   | 11,384 |
| 14   | 11,403 |
| 15   | 11,541 |
| 16   | 11,210 |
| 17   | 11,456 |
| 18   | 11,651 |
| 19   | 11,642 |
| 20   | 11,354 |
| 21   | 11,451 |
| 22   | 9,630  |
| 23   | 2,054  |

### Per-Collector Summary (24 hours total)

| Collector                | Total duration | Rows processed                                |
| ------------------------ | -------------- | --------------------------------------------- |
| job_host_summary_service | 185.54s        | 1,263,400 (main_jobhostsummary rows)          |
| unified_jobs             | 114.57s        | 252,680 (main_unifiedjob rows)                |
| credentials_service      | 2.34s          | 1,010,720 (main_unifiedjob_credentials rows)  |

---

## Scale 4 Detail

**Date of test run:** 2026-04-30
**Scale:** J=25,000, H=50 (no events)
**Environment:** OCP Jenkins deployment

### Summary

| Phase               | Duration  | Peak MB  |
| ------------------- | --------- | -------- |
| Snapshot collectors | 0.31s     | 134.9 MB |
| Hourly collection   | 92.6s     | 291.4 MB |
| Daily rollup        | 5.76s     | 450.4 MB |
| **Total**           | **98.7s** |          |

| Baseline MB | Peak MB  | Delta MB |
| ----------- | -------- | -------- |
| 132.4 MB    | 450.4 MB | 318.1 MB |

### Output Table Sizes

| Table                   | Rows | Size (MB) |
| ----------------------- | ---- | --------- |
| HourlyMetricsCollection | 72   | —         |
| DailyMetricsSummary     | 1    | 3.19      |

### Source Table Counts (AWX DB)

| Table                       | Total (all time) | Test date total              |
| --------------------------- | ---------------- | ---------------------------- |
| main_unifiedjob             | 75,289           | 25,000                       |
| main_jobhostsummary         | 3,750,049        | 1,250,000 (50 per job)       |
| main_unifiedjob_credentials | 300,000          | 100,000 (4 per job)          |
| main_host                   | 202              |                              |
| main_job                    | 75,195           |                              |
| main_unifiedjobtemplate     | 52               |                              |
| main_inventory              | 9                |                              |
| main_organization           | 6                |                              |
| main_credential             | 18               |                              |
| main_credentialtype         | 32               |                              |
| main_executionenvironment   | 403              |                              |

### Jobs Finished Per Hour

| Hour | Jobs  |
| ---- | ----- |
| 0    | 181   |
| 1    | 927   |
| 2    | 1,170 |
| 3    | 1,155 |
| 4    | 1,129 |
| 5    | 1,164 |
| 6    | 1,102 |
| 7    | 1,133 |
| 8    | 1,151 |
| 9    | 1,127 |
| 10   | 1,158 |
| 11   | 1,054 |
| 12   | 1,136 |
| 13   | 1,132 |
| 14   | 1,134 |
| 15   | 1,156 |
| 16   | 1,131 |
| 17   | 1,191 |
| 18   | 1,109 |
| 19   | 1,170 |
| 20   | 1,109 |
| 21   | 1,118 |
| 22   | 961   |
| 23   | 202   |

### Per-Collector Summary (24 hours total)

| Collector                 | Total duration | Rows processed                              |
| ------------------------- | -------------- | ------------------------------------------- |
| job_host_summary_service  | 62.07s         | 1,250,000 (main_jobhostsummary rows)        |
| unified_jobs              | 29.29s         | 25,000 (main_unifiedjob rows)               |
| credentials_service       | 1.22s          | 100,000 (main_unifiedjob_credentials rows)  |

---
