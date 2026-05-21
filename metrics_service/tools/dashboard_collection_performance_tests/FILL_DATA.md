# Fill AWX Database — Dashboard Collection Benchmark

Populates the AWX database with performance test data for the dashboard collection benchmark.
The script calls `fill_perf_db_data.py` (from `metrics-utility`) once for every day in the
given period and cleans up existing data first.

---

## Prerequisites

**Start the database**

```bash
cd metrics-service
docker-compose up -d postgres
```

---

## Scale presets

| Scale | Jobs/day | Hosts | `main_unifiedjob` | `main_jobhostsummary` | `main_unifiedjob_credentials` |
|------:|---------:|------:|------------------:|----------------------:|------------------------------:|
|     1 |      100 |     5 |             9,100 |                45,500 |                        36,400 |
|     2 |      500 |     5 |            45,500 |               227,500 |                       182,000 |
|     3 |    1,100 |     5 |           100,100 |               500,500 |                       400,400 |
|     4 |      500 |    50 |            45,500 |             2,275,000 |                       182,000 |

> Row counts are measured over the default 90-day period (`2024-01-01 → 2024-03-31`).

---

## Run

Set AWX database connection variables before running any of the examples below:

```bash
export METRICS_UTILITY_DB_HOST=localhost
export METRICS_UTILITY_DB_PORT=<port>
export METRICS_UTILITY_DB_NAME=<awx-db-name>
export METRICS_UTILITY_DB_USER=<awx-db-user>
export METRICS_UTILITY_DB_PASSWORD=<awx-db-password>
```

If `metrics-utility` is not checked out as a sibling of `metrics-service`, also set:

```bash
export METRICS_UTILITY_PATH=<path-to-metrics-utility>
```

---

### Scale 1 — 100 jobs/day, 5 hosts (~9 K jobs over 90 days)

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 1
```

### Scale 2 — 500 jobs/day, 5 hosts (~45 K jobs over 90 days)

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 2
```

### Scale 3 — 1100 jobs/day, 5 hosts (~100 K jobs over 90 days)

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 3
```

### Scale 4 — 500 jobs/day, 50 hosts (~45 K jobs, ~2.3 M host summaries over 90 days)

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 4
```

### Custom period

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --scale 2 \
  --period-start 2024-01-01 \
  --period-end   2024-06-30
```

### Custom counts (no scale preset)

```bash
cd metrics-service
.venv/bin/python \
  metrics_service/tools/dashboard_collection_performance_tests/fill_data.py \
  --period-start 2024-01-01 \
  --period-end   2024-03-31 \
  --job-count    750 \
  --host-count   10 \
  --task-count   30
```

### All arguments

| Argument         | Default      | Description                                                          |
|------------------|--------------|----------------------------------------------------------------------|
| `--scale`        | —            | Preset 1–4 (overrides `--job-count`, `--host-count`, `--task-count`) |
| `--period-start` | `2024-01-01` | First day to fill                                                    |
| `--period-end`   | `2024-03-31` | Last day to fill                                                     |
| `--job-count`    | `500`        | Jobs per day (ignored when `--scale` is set)                         |
| `--host-count`   | `5`          | Hosts (ignored when `--scale` is set)                                |
| `--task-count`   | `50`         | Tasks per job (ignored when `--scale` is set)                        |

### Environment variables

| Variable                      | Description                                                                                                                                                                                                        |
|-------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `METRICS_UTILITY_PATH`        | Path to the `metrics-utility` checkout. If not set, `fill_data.py` looks for a sibling directory named `metrics-utility` next to the `metrics-service` repo (i.e. `../metrics-utility` relative to the repo root). |
| `METRICS_UTILITY_DB_HOST`     | AWX DB host                                                                                                                                                                                                        |
| `METRICS_UTILITY_DB_PORT`     | AWX DB port                                                                                                                                                                                                        |
| `METRICS_UTILITY_DB_NAME`     | AWX DB name                                                                                                                                                                                                        |
| `METRICS_UTILITY_DB_USER`     | AWX DB user                                                                                                                                                                                                        |
| `METRICS_UTILITY_DB_PASSWORD` | AWX DB password                                                                                                                                                                                                    |

---

## Expected output

```
============================================================
  Dashboard Benchmark — Data Fill
============================================================
  Scale:      scale 2
  Period:     2024-01-01 → 2024-03-31  (91 day(s))
  Job-count:  500 per day
  Host-count: 5
  Task-count: 50
  AWX DB:     <user>@localhost:5432/<db>
  mu path:    /path/to/metrics-utility

Step 1: Cleaning existing AWX data...
$ python clean_all_data.py --force
  → done in X.Xs

Step 2: Filling 91 day(s)...
  2024-01-01
$ python fill_perf_db_data.py --date=2024-01-01 --job-count=500 --host-count=5 --task-count=50 --no-events
  → done in X.Xs
  ...
  2024-03-31
  → done in X.Xs

============================================================
  Done — 91 day(s) filled.
============================================================
```

---

## Verify row counts

```bash
docker exec <postgres-container> psql -U <user> -d <db> \
  -c "SELECT COUNT(*) FROM main_unifiedjob;"

docker exec <postgres-container> psql -U <user> -d <db> \
  -c "SELECT COUNT(*) FROM main_jobhostsummary;"
```

---

## Troubleshooting

- Check that postgres is running: `docker-compose ps`
- If `scripts directory not found` error appears, set `METRICS_UTILITY_PATH` to your `metrics-utility` checkout
- If `clean_all_data.py` or `fill_perf_db_data.py` are missing, verify the `metrics-utility` checkout is complete
- The script fills jobs **without events** (`--no-events`) for speed — the dashboard collector does not require event
  data

