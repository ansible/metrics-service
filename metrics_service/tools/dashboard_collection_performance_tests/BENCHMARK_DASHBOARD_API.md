# Dashboard Collection — API Performance Benchmark

Benchmarks the automation dashboard data collection pipeline through the full
HTTP/dispatcherd stack — tasks are triggered via `POST /api/v1/tasks/schedule_immediate/`
and polled until completion.

Three phases are measured, each on a clean `JobData` table:

|         Phase | Window                                |
|--------------:|---------------------------------------|
| 1 — one month | `TEST_SINCE` → `TEST_SINCE + 30 days` |
|  2 — one week | `TEST_UNTIL - 7 days` → `TEST_UNTIL`  |
|   3 — one day | `TEST_UNTIL - 1 day`  → `TEST_UNTIL`  |

Duration is measured from `started_at` to `completed_at` on the `TaskExecution`
record — actual execution time, directly comparable to the internal benchmark.
Wall time (printed separately) includes the dispatcherd queue wait.

---

## Prerequisites

**postgres, metrics-service web server, and dispatcherd must all be running.**

### 1 — Start postgres

```bash
cd metrics-service
docker-compose up -d postgres
```

### 2 — Start the web server (if not already running)

```bash
cd metrics-service
.venv/bin/python manage.py runserver
```

### 3 — Start dispatcherd (in a separate terminal)

```bash
cd metrics-service
.venv/bin/python manage.py run_dispatcherd --workers 4
```

### 4 — Run migrations and create a superuser (first time only)

```bash
cd metrics-service
.venv/bin/python manage.py migrate
.venv/bin/python manage.py metrics_service init-service-id
.venv/bin/python manage.py metrics_service init-system-tasks

DJANGO_SUPERUSER_PASSWORD=<password> \
  .venv/bin/python manage.py createsuperuser \
  --username <username> --email <email> --noinput
```

---

## Step 1 — Populate the AWX database

Use `fill_data.py` to generate test data. See [FILL_DATA.md](FILL_DATA.md) for
full documentation and scale reference table.

Set AWX database connection variables first:

```bash
export METRICS_UTILITY_DB_HOST=localhost
export METRICS_UTILITY_DB_PORT=<port>
export METRICS_UTILITY_DB_NAME=<awx-db-name>
export METRICS_UTILITY_DB_USER=<awx-db-user>
export METRICS_UTILITY_DB_PASSWORD=<awx-db-password>
```

Then fill with a scale preset:

```bash
cd metrics-service

# Scale 1 — 100 jobs/day, 5 hosts
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 1
```

---

## Step 2 — Run the benchmark

Set the required environment variables:

```bash
# metrics-service DB
export METRICS_SERVICE_DATABASES__default__ENGINE=django.db.backends.postgresql
export METRICS_SERVICE_DATABASES__default__HOST=localhost
export METRICS_SERVICE_DATABASES__default__PORT=<port>
export METRICS_SERVICE_DATABASES__default__USER=<metrics-service-db-user>
export METRICS_SERVICE_DATABASES__default__PASSWORD=<metrics-service-db-password>
export METRICS_SERVICE_DATABASES__default__NAME=<metrics-service-db-name>

# AWX DB
export METRICS_SERVICE_DATABASES__awx__HOST=localhost
export METRICS_SERVICE_DATABASES__awx__PORT=<port>
export METRICS_SERVICE_DATABASES__awx__USER=<awx-db-user>
export METRICS_SERVICE_DATABASES__awx__PASSWORD=<awx-db-password>
export METRICS_SERVICE_DATABASES__awx__NAME=<awx-db-name>

# General
export METRICS_SERVICE_LOG_LEVEL=WARNING
export METRICS_SERVICE_FEATURE_ENABLED__DASHBOARD_COLLECTION=true
```

Then run for each scale:

> **Output files** are written to `/tmp/` to avoid committing large artifacts.
> Change the `tee` path if you want to keep results elsewhere.

### Scale 1

```bash
cd metrics-service
BASE_URL=http://localhost:8000/api \
BENCHMARK_USER=<username> \
PASSWORD=<password> \
  .venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/benchmark_dashboard_api.py \
  | tee /tmp/results_scale1_api.txt
```

### Scale 2

```bash
# Fill data first:
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 2

# Run benchmark:
BASE_URL=http://localhost:8000/api \
BENCHMARK_USER=<username> \
PASSWORD=<password> \
  .venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/benchmark_dashboard_api.py \
  | tee /tmp/results_scale2_api.txt
```

### Scale 3

```bash
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 3

BASE_URL=http://localhost:8000/api \
BENCHMARK_USER=<username> \
PASSWORD=<password> \
  .venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/benchmark_dashboard_api.py \
  | tee /tmp/results_scale3_api.txt
```

### Scale 4

```bash
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 4

BASE_URL=http://localhost:8000/api \
BENCHMARK_USER=<username> \
PASSWORD=<password> \
  .venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/benchmark_dashboard_api.py \
  | tee /tmp/results_scale4_api.txt
```

---

## Test parameters (optional overrides)

| Variable      | Default      | Description                                                 |
|---------------|--------------|-------------------------------------------------------------|
| `TEST_SINCE`  | `2024-01-01` | Start of the test period                                    |
| `TEST_UNTIL`  | `2024-03-31` | End of the test period                                      |
| `DB_NAME`     | `awx`        | AWX database alias                                          |
| `METRICS_URL` | —            | Prometheus `/metrics` URL (optional, for server-side stats) |

---

## Expected output

```
================================================================================
  Automation Dashboard Collection API Benchmark
  Test period:  2024-01-01 → 2024-03-31
  Phase 1 (month):  2024-01-01 → 2024-01-31
  Phase 2 (week):   2024-03-24 → 2024-03-31
  Phase 3 (day):    2024-03-30 → 2024-03-31
  Target:    http://localhost:8000/api
  User:      <username>
  Prometheus: (not configured)
================================================================================

Verifying connectivity...
  OK

Phase 1: One month collection
  Range: 2024-01-01 → 2024-01-31
  Duration (task):     X.XXs
  Duration (wall):     XX.XXs  (includes queue wait)
  JobData rows in DB:  X,XXX

Phase 2: One week collection
  Range: 2024-03-24 → 2024-03-31
  Duration (task):     X.XXs
  Duration (wall):     XX.XXs  (includes queue wait)
  JobData rows in DB:  XXX

Phase 3: One day collection
  Range: 2024-03-30 → 2024-03-31
  Duration (task):     X.XXs
  Duration (wall):     XX.XXs  (includes queue wait)
  JobData rows in DB:  XXX

================================================================================
  Final Results
================================================================================

  Phase                          Window                    Task time
  ------------------------------ ------------------------ ----------
  Phase 1 — one month            2024-01-01 → 2024-01-31     X.XXs
  Phase 2 — one week             2024-03-24 → 2024-03-31     X.XXs
  Phase 3 — one day              2024-03-30 → 2024-03-31     X.XXs

  Total wall time:  XX.Xs (X.X min)  (includes queue waits)
```

---

## Troubleshooting

- **`NOT RUNNING` or connection refused** — verify `runserver` and `run_dispatcherd` are both active
- **Task stays pending** — dispatcherd is not running or `DASHBOARD_COLLECTION` feature flag is not enabled; verify
  `METRICS_SERVICE_FEATURE_ENABLED__DASHBOARD_COLLECTION=true`
- **401 Unauthorized** — wrong `BENCHMARK_USER` / `PASSWORD`; verify the user is a superuser
- **`JobData` table does not exist** — run `python manage.py migrate`
- **`fill_data.py` scripts directory not found** — set `METRICS_UTILITY_PATH` to your `metrics-utility` checkout
- **Wall time >> task time** — normal; wall time includes the dispatcherd queue wait (~20s per task on a local setup)
- For verbose output set `METRICS_SERVICE_LOG_LEVEL=INFO`

