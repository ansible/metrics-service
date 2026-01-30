# Metrics-Service Performance Test Results

**Date:** 2026-01-29
**Goal:** Simple baseline performance test for metrics-service collection and rollup

## Test Setup

**Test Data:**

- Total events in database: 11,373,397 events (~11.4M)
- Data range: January 1-31, 2024
- Generated using metrics-utility: `fill_perf_db_data.py`

**Test Date Selected:**

- January 16, 2024 (automatically picked by test - middle of data range)
- Events on this date: 199,776 (~200K)

**What Was Tested:**

- Collection: 24 hours of hourly collections (3 collectors × 24 hours = 72 collections)
- Rollup: Daily rollup of those 72 collections

## Results

### Collection Phase

- **Time:** 437.5 seconds (7.3 minutes)
- **Collections created:** 72
- **Data collected:**
  - main_jobevent: 113.02 MB (24 collections)
  - main_host: 43.12 MB (24 collections)
  - job_host_summary: 2.50 MB (24 collections)
  - **Total:** 158.64 MB

### Rollup Phase

- **Time:** 0.06 seconds
- **Daily summaries created:** 0 (rollup completed but no summaries saved - possible issue to investigate)

### Total Pipeline

- **Total time:** 437.5 seconds (7.3 minutes)
- **Throughput:** ~456 events/second (199,776 events ÷ 437.5s)
- **Bottleneck:** Collection phase (99.9% of time)

**Metrics-Service Results:**

- Small-scale test: ~200K events in 7.3 minutes (437 seconds)
- Throughput: ~456 events/second
- Collection: 437 seconds (99.9% of time)
- Rollup: 0.06 seconds (<0.1% of time)

## How to Run This Test

```bash
# Set database connection (both metrics_service and awx databases)
export METRICS_SERVICE_DATABASES__default__ENGINE=django.db.backends.postgresql
export METRICS_SERVICE_DATABASES__default__HOST=localhost
export METRICS_SERVICE_DATABASES__default__PORT=5432
export METRICS_SERVICE_DATABASES__default__USER=metrics_service
export METRICS_SERVICE_DATABASES__default__PASSWORD=metrics_service
export METRICS_SERVICE_DATABASES__default__NAME=metrics_service
export METRICS_SERVICE_DATABASES__awx__HOST=localhost
export METRICS_SERVICE_DATABASES__awx__USER=metrics_service
export METRICS_SERVICE_DATABASES__awx__PASSWORD=metrics_service
export METRICS_SERVICE_LOG_LEVEL=WARNING

# Run the test
.venv/bin/python tools/performance_tests/simple_test.py
```

## Test Data Generation

Test data was generated using metrics-utility:

```bash
# In metrics-utility repository:
python tools/anonymized_db_perf_data/fill_perf_db_data.py \
    --job-count=200 \
    --host-count=869 \
    --task-count=50
```

This creates ~11M events distributed across January 2024.
