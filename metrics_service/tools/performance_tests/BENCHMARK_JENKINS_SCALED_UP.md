# Running Scaled-Up Performance Benchmarks Against Jenkins Pipeline

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
    automation-metrics-tasks:/tmp/benchmark_manage.py
```

## Step 3 — Run the benchmarks at each scale

Use a fresh Jenkins instance for each scale. Generate data for all four dates, then run the benchmark.

---

### Scale 1 (2,500 jobs, 5 hosts)

**Generate data:**

```bash
cd <path-to-metrics-utility>

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --job-count=2500 --host-count=5 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-24 --job-count=2500 --host-count=5 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-25 --job-count=2500 --host-count=5 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-26 --job-count=2500 --host-count=5 --no-events
```

**Run benchmark (on the metrics-service host):**

```bash
podman exec automation-metrics-tasks \
  python3.12 manage.py shell -c "exec(open('/tmp/benchmark_manage.py').read())" \
  | tee /home/ansible/results_scale1_jenkins.txt
```

---

### Scale 2 (25,000 jobs, 5 hosts)

**Generate data:**

```bash
cd <path-to-metrics-utility>

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --job-count=25000 --host-count=5 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-24 --job-count=25000 --host-count=5 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-25 --job-count=25000 --host-count=5 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-26 --job-count=25000 --host-count=5 --no-events
```

**Run benchmark (on the metrics-service host):**

```bash
podman exec automation-metrics-service \
  python3.12 manage.py shell -c "exec(open('/tmp/benchmark_manage.py').read())" \
  | tee /home/ansible/results_scale2_jenkins.txt
```

---

### Scale 3 (250,000 jobs, 5 hosts)

**Generate data:**

```bash
cd <path-to-metrics-utility>

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --job-count=250000 --host-count=5 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-24 --job-count=250000 --host-count=5 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-25 --job-count=250000 --host-count=5 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-26 --job-count=250000 --host-count=5 --no-events
```

**Run benchmark (on the metrics-service host):**

```bash
podman exec automation-metrics-service \
  python3.12 manage.py shell -c "exec(open('/tmp/benchmark_manage.py').read())" \
  | tee /home/ansible/results_scale3_jenkins.txt
```

---

### Scale 4 (25,000 jobs, 50 hosts)

**Generate data:**

```bash
cd <path-to-metrics-utility>

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --job-count=25000 --host-count=50 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-24 --job-count=25000 --host-count=50 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-25 --job-count=25000 --host-count=50 --no-events

METRICS_UTILITY_DB_HOST=<controller-ip> \
METRICS_UTILITY_DB_USER=<controller-db-user> \
METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-26 --job-count=25000 --host-count=50 --no-events
```

**Run benchmark (on the metrics-service host):**

```bash
podman exec automation-metrics-service \
  python3.12 manage.py shell -c "exec(open('/tmp/benchmark_manage.py').read())" \
  | tee /home/ansible/results_scale4_jenkins.txt
```

---

## Results

Timing and memory from the benchmark Summary section. Full output (per-collector durations,
per-hour memory peaks, source table counts, per-hour job breakdown) is in the individual
`results_scale*_jenkins.txt` files.

| Scale | Jobs | Hosts | Snapshot | Hourly | Daily rollup | Total | Baseline MB | Peak MB | Delta MB |
| ----- | ---- | ----- | -------- | ------ | ------------ | ----- | ----------- | ------- | -------- |
| Scale 1 | 2,500 | 5 | | | | | | | |
| Scale 2 | 25,000 | 5 | | | | | | | |
| Scale 3 | 250,000 | 5 | | | | | | | |
| Scale 4 | 25,000 | 50 | | | | | | | |
