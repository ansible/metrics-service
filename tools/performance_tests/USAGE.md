# Performance Testing Usage Guide

Performance testing for metrics-service collection and rollup tasks.

## Prerequisites

**Important:** Performance tests require raw data in AWX/Controller database tables. Use [metrics-utility data generators](https://github.com/ansible/metrics-utility/tree/devel/tools/anonymized_db_perf_data) to populate test data.

### Setup Raw Test Data

```bash
# Clone metrics-utility repository
git clone https://github.com/ansible/metrics-utility.git
cd metrics-utility

# Install and generate test data
pip install -e .

# Small dataset (~100K events): 20 jobs × 100 hosts × 50 tasks
python tools/anonymized_db_perf_data/fill_perf_db_data.py --job-count=20 --host-count=100 --task-count=50

# Medium dataset (~1M events): 20 jobs × 1000 hosts × 50 tasks
python tools/anonymized_db_perf_data/fill_perf_db_data.py --job-count=20 --host-count=1000 --task-count=50

# Large dataset (~10M events): 200 jobs × 869 hosts × 50 tasks
python tools/anonymized_db_perf_data/fill_perf_db_data.py --job-count=200 --host-count=869 --task-count=50
```

This populates AWX database tables (`main_jobevent`, `main_host`, `main_jobhostsummary`) that the collection tasks read from.

## Quick Start

```bash
# Run complete test suite across all dataset sizes (small, medium, large)
python tools/performance_tests/run_all_dataset_sizes.py

# View results
cat tools/performance_tests/output/full_suite_*/SUMMARY.md
```

## Individual Operations

### 1. Run Collection Tasks

**Note:** Collection tasks require raw data (see Prerequisites). They query AWX database tables and create `HourlyMetricsCollection` records.

```bash
# Run hourly collection tasks for 24 hours
python tools/performance_tests/generate_test_data.py --size small
python tools/performance_tests/generate_test_data.py --size medium
python tools/performance_tests/generate_test_data.py --size large
```

This executes the actual production collection tasks:

- `collect_job_host_summary_hourly` - Uses metrics-utility `job_host_summary` collector
- `collect_host_metrics_hourly` - Uses metrics-utility `main_host` collector
- `collect_main_host_hourly` - Uses metrics-utility `main_jobevent` collector

Collections are stored in `HourlyMetricsCollection` model for rollup processing.

### 1.5 Verify Test Data Distribution

```bash
# Validate that generated data is correctly distributed
python tools/performance_tests/verify_hourly_distribution.py --size small
python tools/performance_tests/verify_hourly_distribution.py --size medium
python tools/performance_tests/verify_hourly_distribution.py --size large

# Auto-detect and verify current dataset
python tools/performance_tests/verify_hourly_distribution.py
```

The verification script validates:

- Correct number of collections (72 = 24 hours × 3 collectors)
- Even distribution across hours (3 collections per hour)
- Event counts match target dataset size
- No gaps in hourly time sequence

### 2. Test Individual Tasks

```bash
# Test all tasks separately
python tools/performance_tests/task_performance_test.py --task all

# Test specific task groups
python tools/performance_tests/task_performance_test.py --task hourly    # 3 hourly collectors
python tools/performance_tests/task_performance_test.py --task daily     # 5-step rollup pipeline
```

### 3. Test All Tasks Together

```bash
# Run all tasks in parallel (max load) and sequential (normal order)
python tools/performance_tests/run_all_tasks.py --mode both
```

## What Gets Measured

Each test measures:

- **Duration** (milliseconds)
- **Memory usage** (before, after, delta, peak in MB)
- **Status** (success/failed)

## Output

Results saved to `tools/performance_tests/output/` with:

- **Markdown reports** - Human-readable summaries
- **JSON reports** - Structured data for analysis
- **Timing logs** - Detailed execution logs with ISO 8601 timestamps

## Tasks Tested

**Hourly Collections:**

- `collect_job_host_summary_hourly`
- `collect_host_metrics_hourly`
- `collect_main_host_hourly`

**Daily Rollup Pipeline:**

- `daily_metrics_rollup`
- `daily_anonymize_and_prepare`
- `send_anonymized_to_segment`
- `cleanup_metrics_data`

**Anonymized Collection:**

- `full_process_anonymize` (12-hour task)

## Notes

- **Requires database setup:** `python manage.py migrate`
- **Requires raw AWX data:** Use metrics-utility generators (see Prerequisites)
- **Tests production pipeline:** Collection tasks → HourlyMetricsCollection → Rollup
- **Large dataset tests:** May need 4GB+ memory
- **Enable features:** `export METRICS_SERVICE_METRICS_COLLECTION=true`

## Testing Approach

This performance testing follows the full production pipeline:

1. **Raw Data Setup** (using metrics-utility)
   - Populate AWX tables: `main_jobevent`, `main_host`, `main_jobhostsummary`
   - Use `fill_perf_db_data.py` from metrics-utility repository

2. **Collection Phase** (tested by `generate_test_data.py`)
   - Run actual collection tasks (`collect_*_hourly`)
   - Tasks use metrics-utility collectors to query raw tables
   - Creates `HourlyMetricsCollection` records

3. **Rollup Phase** (tested by performance test scripts)
   - Aggregate hourly collections into daily summaries
   - Test individual, parallel, and sequential execution

This approach ensures realistic performance measurements that match production behavior.
