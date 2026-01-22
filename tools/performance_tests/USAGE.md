# Performance Testing Usage Guide

Performance testing for metrics-service collection and rollup tasks.

## Quick Start

```bash
# Run complete test suite across all dataset sizes (small, medium, large)
python tools/performance_tests/run_all_dataset_sizes.py

# View results
cat tools/performance_tests/output/full_suite_*/SUMMARY.md
```

## Individual Operations

### 1. Generate Test Data

```bash
# Small (~100K events), Medium (~1M events), Large (~10M events)
python tools/performance_tests/generate_test_data.py --size small
python tools/performance_tests/generate_test_data.py --size medium
python tools/performance_tests/generate_test_data.py --size large
```

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

- Requires database setup: `python manage.py migrate`
- Large dataset tests may need 4GB+ memory
- Enable features: `export METRICS_SERVICE_METRICS_COLLECTION=true`
