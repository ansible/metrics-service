# Metrics-Service Jenkins Pipeline Benchmark Results

Tests the full collection + rollup pipeline on a containerized AIO Jenkins
deployment, using `benchmark_manage.py` via `podman exec` (direct Python calls
inside the container). Duration is wall-clock time measured by `time.perf_counter()`.

> **Note:** `benchmark_api.py` cannot be used against Jenkins deployments —
> production metrics-service sets `ALLOWED_HOSTS=[]`, which causes Django to
> reject all HTTP requests with 400.
>
> **Note:** Data is cumulative across scales (no clean between runs due to FK
> constraints on internal AWX jobs). Each scale's AWX DB contains data from all
> prior scales as well.

## Scaling Summary

| Scale  | Generator params    | Snapshot | Hourly | Daily rollup | Total  |
|--------|---------------------|----------|--------|--------------|--------|
| Small  | J=100, T=50, H=16   | 1.29s    | 3.5s   | 1.09s        | 5.9s   |
| Medium | J=1000, T=50, H=20  | 0.89s    | 8.3s   | 2.83s        | 12.1s  |
| Large  | J=2000, T=100, H=40 | 0.87s    | 15.8s  | 3.33s        | 20.0s  |

---

## Small Scale Detail

**Date of test run:** 2026-04-07
**Scale:** J=100, T=50, H=16 (no events)
**Environment:** AIO containerized Jenkins deployment
**Test date:** 2024-01-25

### AWX DB counts at time of benchmark (total rows in DB, not per hour)

| Table               | Total rows |
|---------------------|------------|
| main_host           | 78         |
| main_job            | 423        |
| main_jobhostsummary | 6,710      |
| main_jobevent       | 729        |

### Summary

| Phase               | Duration  |
|---------------------|-----------|
| Snapshot collectors | 1.29s     |
| Hourly collection   | 3.5s      |
| Daily rollup        | 1.09s     |
| **Total**           | **5.9s**  |

---

## Medium Scale Detail

**Date of test run:** 2026-04-07
**Scale:** J=1000, T=50, H=20 (cumulative on top of small; no events)
**Environment:** AIO containerized Jenkins deployment
**Test date:** 2024-01-25

### AWX DB counts at time of benchmark (total rows in DB, not per hour)

| Table               | Total rows |
|---------------------|------------|
| main_host           | 158        |
| main_job            | 4,423      |
| main_jobhostsummary | 86,710     |
| main_jobevent       | 729        |

### Summary

| Phase               | Duration   |
|---------------------|------------|
| Snapshot collectors | 0.89s      |
| Hourly collection   | 8.3s       |
| Daily rollup        | 2.83s      |
| **Total**           | **12.1s**  |

---

## Large Scale Detail

**Date of test run:** 2026-04-07
**Scale:** J=2000, T=100, H=40 (cumulative on top of medium; no events)
**Environment:** AIO containerized Jenkins deployment
**Test date:** 2024-01-25

### AWX DB counts at time of benchmark (total rows in DB, not per hour)

| Table               | Total rows |
|---------------------|------------|
| main_host           | 338        |
| main_job            | 13,423     |
| main_jobhostsummary | 426,710    |
| main_jobevent       | 729        |

### Summary

| Phase               | Duration   |
|---------------------|------------|
| Snapshot collectors | 0.87s      |
| Hourly collection   | 15.8s      |
| Daily rollup        | 3.33s      |
| **Total**           | **20.0s**  |

---
