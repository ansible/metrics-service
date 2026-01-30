# Simple Performance Test

This is a basic performance test to measure collection and rollup time.

## What It Does

1. Checks what raw data exists in AWX database
2. Picks a test date (middle of the data range)
3. Runs collection for one day (24 hours)
4. Measures how long collection takes
5. Runs rollup on that day's data
6. Measures how long rollup takes
7. Reports the results

## Prerequisites

**Raw AWX data must exist** - Use metrics-utility generators:

```bash
# In metrics-utility repository:
python tools/anonymized_db_perf_data/fill_perf_db_data.py \
    --job-count=200 \
    --host-count=869 \
    --task-count=50
```

This creates ~11M events in the AWX database.

## How to Run

```bash
# Set database connection
export METRICS_SERVICE_DATABASES__default__ENGINE=django.db.backends.postgresql
export METRICS_SERVICE_DATABASES__default__HOST=localhost
export METRICS_SERVICE_DATABASES__default__PORT=5432
export METRICS_SERVICE_DATABASES__default__USER=metrics_service
export METRICS_SERVICE_DATABASES__default__PASSWORD=metrics_service
export METRICS_SERVICE_DATABASES__default__NAME=metrics_service

# Run the test
.venv/bin/python tools/performance_tests/collection_rollup_benchmark.py
```

## Reporting

```
Step 1: Check Raw AWX Data
  - How many events exist
  - Date range of events
  - How many hosts, job summaries

Step 2: Pick Test Date
  - Which date it's testing
  - How many events on that date

Step 3: Clean Existing Collections
  - Removes old test data

Step 4: Run Collection on 24 hours
  - Progress updates every 6 hours
  - Show collections created
  - Show total data size
  - Show duration

Step 5: Verify Collections
  - Show what was actually collected
  - Warns if collectors returned empty data

Step 6: Run Rollup
  - Shows rollup duration
  - Shows summaries created

Final Results:
  - Collection: X minutes
  - Rollup: X seconds
  - Total: X minutes
```

## Example Output

```
================================================================================
  Final Results
================================================================================

Test date: 2024-01-15

Collection:
  Collections created: 72
  Total size: 43.15 MB
  Duration: 156.3 seconds (2.6 minutes)

Rollup:
  Duration: 2.45 seconds

Total pipeline:
  Duration: 158.8 seconds (2.6 minutes)
```

## Interpreting Results

**Collection Time:**

- This is the main bottleneck
- Measures how long it takes to query raw AWX tables and create HourlyMetricsCollection records
- For 11M events, expect 2-5 minutes

**Rollup Time:**

- Fast (usually < 3 seconds)
- Processes the HourlyMetricsCollection records into daily summaries

**Total Time:**

- Collection + Rollup
- Collection is the bottleneck (>95% of total time)

## Troubleshooting

- Check that docker-compose is running: `docker-compose ps`
- Check password matches docker-compose.yml
- Default password is "metrics_service"
