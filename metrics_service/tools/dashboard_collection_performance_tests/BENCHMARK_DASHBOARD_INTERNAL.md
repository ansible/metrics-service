# Dashboard Collection — Internal Performance Benchmark

Benchmarks the automation dashboard data collection pipeline by calling
`_collect_data()` directly in Python (no HTTP/dispatcher layer).

Two phases are measured:

- **Phase 1 — Initial backfill:** full 90-day historical collection
- **Phase 2 — Incremental sync:** re-syncs the last day in 4 × 6h windows

---

## Run the benchmarks at each scale

Repeat for **scale 1**, **scale 2**, **scale 3**, and **scale 4**.
Each time: fill data → run benchmark → save results.

> See [FILL_DATA.md](FILL_DATA.md) for the full scale reference table
> (`main_unifiedjob`, `main_jobhostsummary`, `main_unifiedjob_credentials` row counts).

Set connection variables once for the whole session:

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

# fill_data.py AWX connection (same DB, different env var prefix)
export METRICS_UTILITY_DB_HOST=localhost
export METRICS_UTILITY_DB_PORT=<port>
export METRICS_UTILITY_DB_NAME=<awx-db-name>
export METRICS_UTILITY_DB_USER=<awx-db-user>
export METRICS_UTILITY_DB_PASSWORD=<awx-db-password>

export METRICS_SERVICE_LOG_LEVEL=WARNING
export METRICS_SERVICE_FEATURE_ENABLED__DASHBOARD_COLLECTION=true
```

---

### Scale 1 — 100 jobs/day, 5 hosts (~9 K jobs over 90 days)

**Fill data:**

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 1
```

**Run benchmark:**

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/benchmark_dashboard_collection.py \
  | tee /tmp/results_scale1_internal.txt
```

---

### Scale 2 — 500 jobs/day, 5 hosts (~45 K jobs over 90 days)

**Fill data:**

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 2
```

**Run benchmark:**

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/benchmark_dashboard_collection.py \
  | tee /tmp/results_scale2_internal.txt
```

---

### Scale 3 — 1100 jobs/day, 5 hosts (~100 K jobs over 90 days)

**Fill data:**

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 3
```

**Run benchmark:**

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/benchmark_dashboard_collection.py \
  | tee /tmp/results_scale3_internal.txt
```

---

### Scale 4 — 500 jobs/day, 50 hosts (~45 K jobs, ~2.3 M host summaries over 90 days)

**Fill data:**

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 4
```

**Run benchmark:**

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/benchmark_dashboard_collection.py \
  | tee /tmp/results_scale4_internal.txt
```

---

## Troubleshooting

- Check that postgres is running: `docker-compose ps`
- If the `JobData` table does not exist, run migrations: `python manage.py migrate`
- If `_collect_data` reports a feature flag error, verify `METRICS_SERVICE_FEATURE_ENABLED__DASHBOARD_COLLECTION=true`
  is exported
- If `fill_data.py` reports `scripts directory not found`, set `METRICS_UTILITY_PATH` to your `metrics-utility` checkout
- For verbose output set `METRICS_SERVICE_LOG_LEVEL=INFO`


