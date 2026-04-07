# Running Performance Benchmarks Against Jenkins Pipeline

**Jenkins pipeline:** AAPQA/AAPQA Provisioner/AAPQA-ATF-Test-Suite-Yolo

## Prerequisites

- Jenkins pipeline has completed and the TSD file is available
- `metrics-utility` is checked out locally
- `metrics-service` is checked out locally

## Step 1 — Get IPs and credentials from the TSD file

The TSD file provides:

- `<controller-ip>` — Controller host (source DB for `fill_perf_db_data.py`)
- `<metrics-service-ip>` — metrics-service host (where the container runs)
- `<controller-db-user>` and `<controller-db-password>` — AWX DB credentials

> **Note:** `benchmark_api.py` does not work against Jenkins deployments.
> Production metrics-service sets `ALLOWED_HOSTS=[]`, which causes Django to reject
> all HTTP requests with 400. Use `benchmark_manage.py` instead, which runs the
> collectors directly via `manage.py shell` inside the container.

## Step 2 — Copy the benchmark script into the container

```bash
# From your local machine — copy to the host
scp metrics_service/tools/performance_tests/benchmark_manage.py \
    ansible@<metrics-service-ip>:/tmp/benchmark_manage.py

# On the metrics-service host — copy into the container
podman cp /tmp/benchmark_manage.py \
    automation-metrics-service:/tmp/benchmark_manage.py
```

## Step 3 — Run the benchmarks at each scale

Repeat the following block for **small**, **medium**, and **large**.
Each time: generate data (cumulative — do not clean between scales) → run benchmark.

> **Note:** Cleaning the AWX DB between scales is not reliable on Jenkins deployments
> due to FK constraints on internal AWX jobs. Data is accumulated across scales instead.

---

### Small (100 jobs, 50 tasks, 16 hosts)

**Generate data:**

```bash
cd <path-to-metrics-utility>

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --job-count=100 --task-count=50 --host-count=16 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-24 --job-count=100 --task-count=50 --host-count=16 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-25 --job-count=100 --task-count=50 --host-count=16 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-26 --job-count=100 --task-count=50 --host-count=16 --no-events
```

**Run benchmark (on the metrics-service host):**

```bash
podman exec automation-metrics-service \
  python3.12 manage.py shell -c "exec(open('/tmp/benchmark_manage.py').read())" \
  | tee /home/ansible/results_small_jenkins.txt
```

---

### Medium (1000 jobs, 50 tasks, 20 hosts)

**Generate data:**

```bash
cd <path-to-metrics-utility>

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --job-count=1000 --task-count=50 --host-count=20 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-24 --job-count=1000 --task-count=50 --host-count=20 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-25 --job-count=1000 --task-count=50 --host-count=20 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-26 --job-count=1000 --task-count=50 --host-count=20 --no-events
```

**Run benchmark (on the metrics-service host):**

```bash
podman exec automation-metrics-service \
  python3.12 manage.py shell -c "exec(open('/tmp/benchmark_manage.py').read())" \
  | tee /home/ansible/results_medium_jenkins.txt
```

---

### Large (2000 jobs, 100 tasks, 40 hosts)

**Generate data:**

```bash
cd <path-to-metrics-utility>

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --job-count=2000 --task-count=100 --host-count=40 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-24 --job-count=2000 --task-count=100 --host-count=40 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-25 --job-count=2000 --task-count=100 --host-count=40 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-26 --job-count=2000 --task-count=100 --host-count=40 --no-events
```

**Run benchmark (on the metrics-service host):**

```bash
podman exec automation-metrics-service \
  python3.12 manage.py shell -c "exec(open('/tmp/benchmark_manage.py').read())" \
  | tee /home/ansible/results_large_jenkins.txt
```

---

## Results

Collected 2026-04-07 on a Jenkins pipeline AIO (containerized) deployment.
Data is cumulative — each scale builds on top of the previous (no clean between scales).

| Scale | Snapshot | Hourly | Daily rollup | Total |
|-------|----------|--------|--------------|-------|
| Small (100 jobs, 50 tasks, 16 hosts) | 2.51s | 3.2s | 0.07s | 5.8s |
| Medium (1000 jobs, 50 tasks, 20 hosts) | 1.64s | 8.3s | 2.32s | 12.2s |
| Large (2000 jobs, 100 tasks, 40 hosts) | 1.49s | 15.7s | 3.32s | 20.5s |
