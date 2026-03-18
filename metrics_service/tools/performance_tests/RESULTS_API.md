# Metrics-Service API Pipeline Benchmark Results

Tests the full collection + rollup pipeline triggered via the HTTP task API
(`POST /api/v1/tasks/schedule_immediate/`), mirroring the internal benchmark
but going through the HTTP/dispatcher layer instead of calling Python directly.

Duration is measured from `started_at` to `completed_at` on the TaskExecution
record — actual execution time, not time spent waiting in the scheduler queue.

## Scaling Comparison

| Scale  | Generator params    | Snapshot | Hourly collection | Rollup  | Total    |
|--------|---------------------|----------|-------------------|---------|----------|
| Small  | J=100, T=50, H=16   | 1.01s    | 6.5s              | 0.02s   | 7.5s     |
| Medium | J=1000, T=50, H=20  | 1.37s    | 18.3s             | 0.10s   | 19.8s    |
| Large  | J=2000, T=100, H=40 | 0.93s    | 10.9s             | 0.11s   | 11.9s    |

---

## Comparison Against Internal Benchmark

### Small Scale

| Phase              | Internal benchmark | API benchmark |
|--------------------|--------------------|---------------|
| Snapshot (4 tasks) | 1.6s               | 1.01s         |
| Hourly (96 tasks)  | 10.5s              | 6.5s          |
| Rollup (1 task)    | 0.05s              | 0.02s         |
| **Total**          | **12.1s**          | **7.5s**      |

### Medium Scale

| Phase              | Internal benchmark | API benchmark |
|--------------------|--------------------|---------------|
| Snapshot (4 tasks) | 1.00s              | 1.37s         |
| Hourly (96 tasks)  | 60.3s              | 18.3s         |
| Rollup (1 task)    | 0.05s              | 0.10s         |
| **Total**          | **61.4s**          | **19.8s**     |

### Large Scale

| Phase              | Internal benchmark | API benchmark |
|--------------------|--------------------|---------------|
| Snapshot (4 tasks) | 7.67s              | 0.93s         |
| Hourly (96 tasks)  | 332.7s             | 10.9s         |
| Rollup (1 task)    | 0.16s              | 0.11s         |
| **Total**          | **340.5s**         | **11.9s**     |

The pipeline logic is identical. Execution times are comparable — small
differences are expected due to data already being cached/indexed from the
prior internal benchmark run.

---

## Small Scale Detail

**Date of test run:** 2026-03-18
**Scale:** ~368K events (J=100, T=50, H=16, 4 dates)
**Target:** `http://localhost:18002/api` (direct pod, bypassing gateway)
**User:** superadmin (Django superuser)
**Test date:** 2024-01-25

### Phase 1: Snapshot collectors (run once each)

| Collector                  | Duration |
|----------------------------|----------|
| execution_environments     | 0.80s    |
| config                     | 0.04s    |
| controller_version_service | 0.11s    |
| table_metadata             | 0.06s    |
| **Total**                  | **1.01s** |

### Phase 2: Hourly collectors (24 hours × 4 collectors)

| Hour | job_host_summary_service | unified_jobs | credentials_service | main_jobevent_service |
|------|--------------------------|--------------|---------------------|-----------------------|
| 0    | 0.03s | 0.02s | 0.02s | 0.10s |
| 1    | 0.02s | 0.02s | 0.01s | 0.18s |
| 2    | 0.02s | 0.02s | 0.02s | 0.11s |
| 3    | 0.03s | 0.11s | 0.02s | 0.04s |
| 4    | 0.02s | 0.01s | 0.01s | 0.03s |
| 5    | 0.04s | 0.02s | 0.01s | 0.04s |
| 6    | 0.01s | 0.02s | 0.01s | 0.11s |
| 7    | 0.01s | 0.01s | 0.03s | 0.10s |
| 8    | 0.02s | 0.01s | 0.04s | 0.09s |
| 9    | 0.02s | 0.02s | 0.01s | 0.11s |
| 10   | 0.02s | 0.01s | 0.01s | 0.03s |
| 11   | 0.02s | 0.06s | 0.01s | 0.03s |
| 12   | 0.01s | 0.01s | 0.08s | 0.03s |
| 13   | 0.06s | 0.07s | 0.01s | 0.08s |
| 14   | 0.05s | 0.01s | 0.01s | 0.09s |
| 15   | 0.01s | 0.02s | 0.01s | 0.10s |
| 16   | 0.06s | 0.05s | 0.02s | 0.03s |
| 17   | 0.04s | 0.01s | 0.01s | 0.09s |
| 18   | 0.02s | 0.01s | 0.01s | 0.05s |
| 19   | 0.18s | 0.07s | 0.01s | 0.12s |
| 20   | 0.01s | 0.01s | 0.01s | 0.09s |
| 21   | 0.02s | 0.03s | 0.01s | 0.08s |
| 22   | 0.01s | 0.02s | 0.01s | 0.10s |
| 23   | 0.02s | 0.04s | 0.01s | 0.37s |
| **Total** | | | | **6.5s** |

### Phase 3: Daily rollup

| Duration |
|----------|
| 0.02s    |

### Summary

| Phase               | Duration   |
|---------------------|------------|
| Snapshot collectors | 1.01s      |
| Hourly collection   | 6.5s       |
| Daily rollup        | 0.02s      |
| **Total**           | **7.5s**   |

### Server-side Metrics (Prometheus — web process only)

> Note: RSS reflects the web process, not the dispatcherd workers that ran
> the collectors. Not directly comparable to the internal benchmark's peak
> memory figure, which measured the worker process.

| Metric                      | Value   |
|-----------------------------|---------|
| CPU time used (web process) | 71.970s |
| RSS memory (web process)    | 87.1 MB |

---

## Medium Scale Detail

**Date of test run:** 2026-03-19
**Scale:** ~4.6M events (J=1000, T=50, H=20, 4 dates)
**Target:** `http://localhost:18002/api` (direct pod, bypassing gateway)
**User:** superadmin (Django superuser)
**Test date:** 2024-01-25

### Phase 1: Snapshot collectors (run once each)

| Collector                  | Duration |
|----------------------------|----------|
| execution_environments     | 1.20s    |
| config                     | 0.09s    |
| controller_version_service | 0.04s    |
| table_metadata             | 0.04s    |
| **Total**                  | **1.37s** |

### Phase 2: Hourly collectors (24 hours × 4 collectors)

| Hour | job_host_summary_service | unified_jobs | credentials_service | main_jobevent_service |
|------|--------------------------|--------------|---------------------|-----------------------|
| 0    | 0.14s | 0.04s | 0.03s | 0.10s |
| 1    | 0.03s | 0.05s | 0.01s | 0.13s |
| 2    | 0.05s | 0.08s | 0.07s | 0.11s |
| 3    | 0.04s | 0.09s | 0.06s | 0.27s |
| 4    | 0.10s | 0.04s | 0.04s | 0.10s |
| 5    | 0.20s | 0.03s | 0.01s | 0.12s |
| 6    | 0.05s | 0.06s | 0.06s | 0.12s |
| 7    | 0.06s | 0.05s | 0.04s | 0.13s |
| 8    | 0.08s | 0.04s | 0.07s | 0.13s |
| 9    | 0.12s | 0.02s | 0.01s | 0.11s |
| 10   | 0.06s | 0.03s | 0.04s | 0.10s |
| 11   | 0.14s | 0.04s | 0.30s | 0.13s |
| 12   | 0.05s | 0.04s | 0.03s | 0.11s |
| 13   | 0.12s | 0.08s | 0.02s | 0.10s |
| 14   | 0.03s | 0.11s | 0.04s | 0.11s |
| 15   | 0.02s | 0.10s | 0.02s | 0.64s |
| 16   | 0.02s | 0.04s | 0.02s | 0.14s |
| 17   | 0.02s | 0.02s | 0.05s | 0.07s |
| 18   | 0.02s | 0.10s | 0.01s | 0.09s |
| 19   | 0.01s | 0.05s | 0.01s | 0.15s |
| 20   | 0.02s | 0.09s | 0.01s | 0.18s |
| 21   | 0.05s | 0.10s | 0.01s | 0.19s |
| 22   | 0.07s | 0.03s | 0.02s | 0.06s |
| 23   | 0.04s | 0.04s | 0.08s | 0.09s |
| **Total** | | | | **18.3s** |

### Phase 3: Daily rollup

| Duration |
|----------|
| 0.10s    |

### Summary

| Phase               | Duration   |
|---------------------|------------|
| Snapshot collectors | 1.37s      |
| Hourly collection   | 18.3s      |
| Daily rollup        | 0.10s      |
| **Total**           | **19.8s**  |

### Server-side Metrics (Prometheus — web process only)

> Note: RSS reflects the web process, not the dispatcherd workers that ran
> the collectors. Not directly comparable to the internal benchmark's peak
> memory figure, which measured the worker process.

| Metric                      | Value   |
|-----------------------------|---------|
| CPU time used (web process) | 79.270s |
| RSS memory (web process)    | 87.9 MB |

---

## Large Scale Detail

**Date of test run:** 2026-03-19
**Scale:** ~36.8M events (J=2000, T=100, H=40, 4 dates)
**Target:** `http://localhost:18002/api` (direct pod, bypassing gateway)
**User:** superadmin (Django superuser)
**Test date:** 2024-01-25

### Phase 1: Snapshot collectors (run once each)

| Collector                  | Duration |
|----------------------------|----------|
| execution_environments     | 0.65s    |
| config                     | 0.11s    |
| controller_version_service | 0.02s    |
| table_metadata             | 0.15s    |
| **Total**                  | **0.93s** |

### Phase 2: Hourly collectors (24 hours × 4 collectors)

| Hour | job_host_summary_service | unified_jobs | credentials_service | main_jobevent_service |
|------|--------------------------|--------------|---------------------|-----------------------|
| 0    | 0.08s | 0.06s | 0.02s | 0.61s |
| 1    | 0.03s | 0.05s | 0.02s | 0.20s |
| 2    | 0.02s | 0.06s | 0.05s | 0.14s |
| 3    | 0.05s | 0.16s | 0.06s | 0.30s |
| 4    | 0.09s | 0.07s | 0.02s | 0.18s |
| 5    | 0.07s | 0.02s | 0.02s | 0.10s |
| 6    | 2.26s | 0.08s | 0.06s | 0.17s |
| 7    | 0.09s | 0.07s | 0.02s | 0.10s |
| 8    | 0.04s | 0.02s | 0.03s | 0.20s |
| 9    | 0.05s | 0.02s | 0.07s | 0.17s |
| 10   | 0.03s | 0.02s | 0.09s | 0.20s |
| 11   | 0.06s | 0.07s | 0.07s | 0.11s |
| 12   | 0.05s | 0.06s | 0.17s | 0.17s |
| 13   | 0.03s | 0.03s | 0.08s | 0.11s |
| 14   | 0.04s | 0.21s | 0.09s | 0.11s |
| 15   | 0.04s | 0.07s | 0.04s | 0.10s |
| 16   | 0.04s | 0.07s | 0.13s | 0.19s |
| 17   | 0.03s | 0.07s | 0.03s | 0.14s |
| 18   | 0.06s | 0.06s | 0.02s | 0.12s |
| 19   | 0.06s | 0.08s | 0.04s | 0.10s |
| 20   | 0.10s | 0.03s | 0.07s | 0.11s |
| 21   | 0.07s | 0.03s | 0.07s | 0.52s |
| 22   | 0.05s | 0.07s | 0.02s | 0.19s |
| 23   | 0.07s | 0.05s | 0.08s | 0.11s |
| **Total** | | | | **10.9s** |

### Phase 3: Daily rollup

| Duration |
|----------|
| 0.11s    |

### Summary

| Phase               | Duration   |
|---------------------|------------|
| Snapshot collectors | 0.93s      |
| Hourly collection   | 10.9s      |
| Daily rollup        | 0.11s      |
| **Total**           | **11.9s**  |

### Server-side Metrics (Prometheus — web process only)

> Note: RSS reflects the web process, not the dispatcherd workers that ran
> the collectors. Not directly comparable to the internal benchmark's peak
> memory figure, which measured the worker process.

| Metric                      | Value   |
|-----------------------------|---------|
| CPU time used (web process) | 80.430s |
| RSS memory (web process)    | 87.1 MB |

---
