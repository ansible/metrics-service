# Simple Performance Test

Takes time measurement in seconds to:

1. Collect metrics for 24 hours. 3 collectors * 24 hrs = 72 collections total

- collect_job_host_summary_hourly
- collect_host_metrics_hourly
- collect_main_host_hourly

1. Roll up those collections into daily summaries

## Prerequisites

**Start the db**

```bash
cd metrics-service
docker-compose up -d postgres
```

**Clean up the AWX db**

```bash

cd metrics-utility
.venv/bin/python tools/anonymized_db_perf_data/clean_all_data.py --force

```

**Use metrics-utility generators to populate db. The example below creates (1000 hosts * 20 jobs * 50 tasks) * 4 = ~4M events.**

```bash

cd metrics-utility

# Add background data across the month
.venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
    --job-count=20 \
    --host-count=1000 \
    --task-count=50

# Add data around specific test data (Jan 24 2026)
  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
      --date=2024-01-24 \
      --job-count=20 \
      --host-count=1000 \
      --task-count=50

  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
      --date=2024-01-25 \
      --job-count=20 \
      --host-count=1000 \
      --task-count=50

  .venv/bin/python tools/anonymized_db_perf_data/fill_perf_db_data.py \
      --date=2024-01-26 \
      --job-count=20 \
      --host-count=1000 \
      --task-count=50
```

**This should generate 4,599,376 events - close to the 4M target. The generator script intentionally includes failures, accounting for the the extra tasks > 4M. Check the db for events to confirm the number:**

```bash
docker exec metrics-service-postgres psql -U myuser -d awx -c "SELECT COUNT(*) as total_events FROM main_jobevent;"

```

## Check event number on Jan 25, 2025. Estimation 1,264,938

```bash
docker exec metrics-service-postgres psql -U myuser -d awx -c "SELECT COUNT(*) as events_on_jan25 FROM main_jobevent WHERE job_created >= '2024-01-25 00:00:00' AND job_created < '2024-01-26 00:00:00';"

```

## Check event number by hour on Jan 25, 2025. Approximately 16 out of 24 hours should have data

```bash
docker exec metrics-service-postgres psql -U myuser -d awx -c "SELECT DATE_TRUNC('hour', job_created) AS hour, COUNT(*) AS event_count FROM main_jobevent WHERE job_created >= '2024-01-25 00:00:00' AND job_created < '2024-01-26 00:00:00'
GROUP BY hour ORDER BY hour;"

```

## Run the perf test

```bash
cd metrics-service
# Set database connection
export METRICS_SERVICE_DATABASES__default__ENGINE=django.db.backends.postgresql
export METRICS_SERVICE_DATABASES__default__HOST=localhost
export METRICS_SERVICE_DATABASES__default__PORT=5432
export METRICS_SERVICE_DATABASES__default__USER=metrics_service
export METRICS_SERVICE_DATABASES__default__PASSWORD=metrics_service
export METRICS_SERVICE_DATABASES__default__NAME=metrics_service

# AWX database
export METRICS_SERVICE_DATABASES__awx__HOST=localhost
export METRICS_SERVICE_DATABASES__awx__USER=metrics_service
export METRICS_SERVICE_DATABASES__awx__PASSWORD=metrics_service

# Run tests with warning level, not debug level
export METRICS_SERVICE_LOG_LEVEL=WARNING

# Set the date (Defaults to 2024-01-16)
export TEST_DATE=2024-01-25 # (1,264,938 events on that day)


# Run the test
.venv/bin/python tools/performance_tests/collection_rollup_benchmark_hourly.py
```

## Reporting

```
Final Results:
  - Collection: X minutes
  - Rollup: X seconds
  - Total: X minutes
```

## Troubleshooting

- Check that docker-compose is running: `docker-compose ps`
- Check password matches docker-compose.yml
- Default password is "metrics_service"
