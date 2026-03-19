# Running Performance Benchmarks Against AAP-Dev

## Prerequisites

- aap-dev is running (`./hack/run-local.sh` completed successfully)
- `psql` is installed locally
- Both `metrics-service` and `metrics-utility` are checked out

## Step 1 — Port-forward postgres

In a dedicated terminal (leave it running):

```bash
cd <path-to-aap-dev>

KUBECONFIG=.tmp/26-next.kubeconfig \
  bin/kubectl port-forward \
  -n aap26-next svc/myaap-postgres-15 15432:5432
```

## Step 2 — Port-forward metrics-service pod (for Prometheus metrics)

In another dedicated terminal (leave it running):

```bash
cd <path-to-aap-dev>

POD=$(KUBECONFIG=.tmp/26-next.kubeconfig \
  bin/kubectl get pods -n aap26-next \
  -l app.kubernetes.io/name=myaap-metrics-service \
  --no-headers -o custom-columns=":metadata.name")

KUBECONFIG=.tmp/26-next.kubeconfig \
  bin/kubectl port-forward -n aap26-next "$POD" 18002:8000
```

## Step 3 — Create the `awx` database in aap-dev postgres

Run once. The postgres admin password is from [make admin-password].

```bash
PGPASSWORD=<your_postgres_password> psql \
  -h localhost -p 15432 -U postgres \
  -c "CREATE USER myuser WITH PASSWORD 'mypassword';" 2>/dev/null || true

PGPASSWORD=<your_postgres_password> psql \
  -h localhost -p 15432 -U postgres \
  -c "CREATE DATABASE awx WITH OWNER myuser;" 2>/dev/null || true

PGPASSWORD=<your_postgres_password> psql \
  -h localhost -p 15432 -U postgres -d awx \
  -c "GRANT ALL ON SCHEMA public TO myuser;"
```

## Step 4 — Create a Django superuser for the metrics-service

Run once. This creates a superuser that can access all benchmarked endpoints
(the default `admin` AAP user will get 403s on most endpoints due to gateway
permission issues).

```bash
cd <path-to-metrics-service>

# Choose any password — it only needs to live for this benchmark session.
export BENCHMARK_PW=<your-password-here>

export METRICS_SERVICE_DATABASES__default__ENGINE=django.db.backends.postgresql
export METRICS_SERVICE_DATABASES__default__HOST=localhost
export METRICS_SERVICE_DATABASES__default__PORT=15432
export METRICS_SERVICE_DATABASES__default__NAME=metrics_service
export METRICS_SERVICE_DATABASES__default__USER=metrics_service
export METRICS_SERVICE_DATABASES__default__PASSWORD=metrics_service_dev_password
export DJANGO_SUPERUSER_PASSWORD=$BENCHMARK_PW
.venv/bin/python manage.py createsuperuser --username superadmin --email superadmin@example.com --noinput
```

Then use `BENCHMARK_USER=superadmin PASSWORD=$BENCHMARK_PW` when running the benchmarks below.

> **Note:** `USERNAME` is a reserved read-only variable in zsh and cannot be overridden inline.
> Use `BENCHMARK_USER` instead.

## Step 5 — Run the benchmarks at each scale

Repeat the following block for **small**, **medium**, and **large**.
Each time: clean → generate data → run internal benchmark → run API benchmark.

> **Important:** The internal benchmark must run before the API benchmark. It populates
> the `HourlyMetricsCollection` and `DailyMetricsSummary` tables that the API reads from.
> Running the API benchmark without the internal benchmark first will produce results
> against empty summary tables.

---

### Small (~368K events)

**Generate data:**

```bash
cd <path-to-metrics-utility>

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/clean_all_data.py --force

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --job-count=100 --task-count=50 --host-count=16

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-24 --job-count=100 --task-count=50 --host-count=16

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-25 --job-count=100 --task-count=50 --host-count=16

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-26 --job-count=100 --task-count=50 --host-count=16
```

**Run internal collection/rollup benchmark:**

```bash
cd <path-to-metrics-service>

METRICS_SERVICE_DATABASES__default__HOST=localhost \
METRICS_SERVICE_DATABASES__default__PORT=15432 \
METRICS_SERVICE_DATABASES__default__NAME=metrics_service \
METRICS_SERVICE_DATABASES__default__USER=metrics_service \
METRICS_SERVICE_DATABASES__default__PASSWORD=metrics_service_dev_password \
METRICS_SERVICE_DATABASES__awx__HOST=localhost \
METRICS_SERVICE_DATABASES__awx__PORT=15432 \
METRICS_SERVICE_DATABASES__awx__NAME=awx \
METRICS_SERVICE_DATABASES__awx__USER=myuser \
METRICS_SERVICE_DATABASES__awx__PASSWORD=mypassword \
METRICS_SERVICE_LOG_LEVEL=WARNING \
TEST_DATE=2024-01-25 \
.venv/bin/python metrics_service/tools/performance_tests/collection_rollup_benchmark_hourly.py \
  | tee metrics_service/tools/performance_tests/results_small_internal.txt
```

**Run API benchmark:**

```bash
cd <path-to-metrics-service>

BASE_URL=http://localhost:18002/api \
BENCHMARK_USER=superadmin \
PASSWORD=$BENCHMARK_PW \
METRICS_URL=http://localhost:18002/metrics \
TEST_DATE=2024-01-25 \
  .venv/bin/python metrics_service/tools/performance_tests/benchmark_api.py \
  | tee metrics_service/tools/performance_tests/results_small_api.txt
```

---

### Medium (~4.6M events)

**Generate data:**

```bash
cd <path-to-metrics-utility>

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/clean_all_data.py --force

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --job-count=1000 --task-count=50 --host-count=20

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-24 --job-count=1000 --task-count=50 --host-count=20

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-25 --job-count=1000 --task-count=50 --host-count=20

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-26 --job-count=1000 --task-count=50 --host-count=20
```

**Run internal collection/rollup benchmark:**

```bash
cd <path-to-metrics-service>

METRICS_SERVICE_DATABASES__default__HOST=localhost \
METRICS_SERVICE_DATABASES__default__PORT=15432 \
METRICS_SERVICE_DATABASES__default__NAME=metrics_service \
METRICS_SERVICE_DATABASES__default__USER=metrics_service \
METRICS_SERVICE_DATABASES__default__PASSWORD=metrics_service_dev_password \
METRICS_SERVICE_DATABASES__awx__HOST=localhost \
METRICS_SERVICE_DATABASES__awx__PORT=15432 \
METRICS_SERVICE_DATABASES__awx__NAME=awx \
METRICS_SERVICE_DATABASES__awx__USER=myuser \
METRICS_SERVICE_DATABASES__awx__PASSWORD=mypassword \
METRICS_SERVICE_LOG_LEVEL=WARNING \
TEST_DATE=2024-01-25 \
.venv/bin/python metrics_service/tools/performance_tests/collection_rollup_benchmark_hourly.py \
  | tee metrics_service/tools/performance_tests/results_medium_internal.txt
```

**Run API benchmark:**

```bash
cd <path-to-metrics-service>

BASE_URL=http://localhost:18002/api \
BENCHMARK_USER=superadmin \
PASSWORD=$BENCHMARK_PW \
METRICS_URL=http://localhost:18002/metrics \
TEST_DATE=2024-01-25 \
  .venv/bin/python metrics_service/tools/performance_tests/benchmark_api.py \
  | tee metrics_service/tools/performance_tests/results_medium_api.txt
```

---

### Large (~36.8M events)

> ⚠️ Data generation will take a while. The benchmark itself runs ~6 minutes.

**Generate data:**

```bash
cd <path-to-metrics-utility>

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/clean_all_data.py --force

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --job-count=2000 --task-count=100 --host-count=40

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-24 --job-count=2000 --task-count=100 --host-count=40

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-25 --job-count=2000 --task-count=100 --host-count=40

METRICS_UTILITY_DB_HOST=localhost \
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
  --date=2024-01-26 --job-count=2000 --task-count=100 --host-count=40
```

**Run internal collection/rollup benchmark:**

```bash
cd <path-to-metrics-service>

METRICS_SERVICE_DATABASES__default__HOST=localhost \
METRICS_SERVICE_DATABASES__default__PORT=15432 \
METRICS_SERVICE_DATABASES__default__NAME=metrics_service \
METRICS_SERVICE_DATABASES__default__USER=metrics_service \
METRICS_SERVICE_DATABASES__default__PASSWORD=metrics_service_dev_password \
METRICS_SERVICE_DATABASES__awx__HOST=localhost \
METRICS_SERVICE_DATABASES__awx__PORT=15432 \
METRICS_SERVICE_DATABASES__awx__NAME=awx \
METRICS_SERVICE_DATABASES__awx__USER=myuser \
METRICS_SERVICE_DATABASES__awx__PASSWORD=mypassword \
METRICS_SERVICE_LOG_LEVEL=WARNING \
TEST_DATE=2024-01-25 \
.venv/bin/python metrics_service/tools/performance_tests/collection_rollup_benchmark_hourly.py \
  | tee metrics_service/tools/performance_tests/results_large_internal.txt
```

**Run API benchmark:**

```bash
cd <path-to-metrics-service>

BASE_URL=http://localhost:18002/api \
BENCHMARK_USER=superadmin \
PASSWORD=$BENCHMARK_PW \
METRICS_URL=http://localhost:18002/metrics \
TEST_DATE=2024-01-25 \
  .venv/bin/python metrics_service/tools/performance_tests/benchmark_api.py \
  | tee metrics_service/tools/performance_tests/results_large_api.txt
```

---

## Results

Output files will be saved alongside this document:

| File | Contents |
|------|----------|
| `results_small_internal.txt` | Small scale — collection/rollup timing and memory |
| `results_small_api.txt` | Small scale — API pipeline timing and Prometheus delta |
| `results_medium_internal.txt` | Medium scale — collection/rollup timing and memory |
| `results_medium_api.txt` | Medium scale — API pipeline timing and Prometheus delta |
| `results_large_internal.txt` | Large scale — collection/rollup timing and memory |
| `results_large_api.txt` | Large scale — API pipeline timing and Prometheus delta |
