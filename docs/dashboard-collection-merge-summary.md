# Dashboard Collection Merge — Summary of Changes

Branch: `Dashboard-Collector-Merge-Anonymized-Collector`
Companion branch (metrics-utility): `Updated-Dashboard-Collection`

## What changed and why

The standalone 6-hourly dashboard collection task (`dashboard_jobs`) has been replaced by a lightweight hook on the existing `hourly_unified_jobs` collection. Dashboard job records are now derived from data already collected each hour for the anonymised rollup pipeline — no extra Controller DB queries.

**Before:** 4 Controller DB calls per hour (2 rollup + 2 dashboard)
**After:** 2 Controller DB calls per hour (rollup only; dashboard reuses the same data)

---

## Files changed

### metrics-utility repo

| File | Change |
|------|--------|
| `metrics_utility/library/collectors/controller/unified_jobs_dashboard.py` | **New file.** Extended `unified_jobs` query with `modified`, `project_id`, `project_name`, `launched_by_id`, `launched_by_username`, `label_ids`, `num_hosts`. `unified_jobs` is untouched (CLI backward compat). |
| `metrics_utility/library/collectors/controller/__init__.py` | Exported `unified_jobs_dashboard`. |
| `metrics_utility/library/collectors/dashboard/queries.py` | Added `get_min_max_job_id_query`, `get_jobs_batch_query`, `get_job_labels_for_ids_query`, `get_job_host_summaries_for_ids_query` for cursor-paginated backfill. |
| `metrics_utility/library/collectors/dashboard/collectors.py` | `dashboard_jobs` accepts optional `after_id` and `batch_size`; uses batch queries when set, full-window queries otherwise (backward compat). |
| `metrics_utility/library/collectors/dashboard/__init__.py` | Exported `get_min_max_job_id_query`. |

### metrics-service repo

| File | Change |
|------|--------|
| `apps/tasks/utils.py` | Added optional `post_collect_hook(raw_data)` parameter to `generic_collect_metrics`. Called after `gather()`, before rollup processing. Hook failures are caught and logged as warnings. |
| `apps/tasks/collectors/collect_hourly_metrics.py` | Added `_build_dashboard_sync_hook(hour_timestamp)`. For `unified_jobs` collections when `DASHBOARD_COLLECTION` is enabled, the hook filters the raw DataFrame to terminal states, serialises to task_data, and creates a `sync_dashboard_job_records` Task. |
| `apps/dashboard_reports/tasks.py` | Added `sync_dashboard_job_records`. Batched backfill with cursor resume on retry. Made backfill window and batch size configurable. Removed follow-up task creation from `collect_dashboard_reports_initial_data`. Cleaned up now-unused imports. |
| `apps/dashboard_reports/models.py` | Guarded `_sync_host_summaries` — skips sync when `host_summaries is None` (preserves records from initial backfill). |
| `apps/tasks/tasks.py` | Registered `sync_dashboard_job_records` in `TASK_FUNCTIONS`. |
| `apps/tasks/task_groups.py` | Removed `daily_dashboard_collection` from `DASHBOARD_COLLECTION_GROUP`. Updated `initial_dashboard_collection` description to reference `INITIAL_BACKFILL_DAYS`. |

---

## New task: `sync_dashboard_job_records`

| Property | Value |
|---|---|
| Triggered by | `hourly_unified_jobs` hook (not a cron) |
| Frequency | Once per hour, created via `get_or_create` (safe on retries) |
| Input | `task_data.raw_jobs` — pre-filtered serialised job rows |
| Output | `JobData` + `JobLabel` records updated in metrics-service DB |
| `JobHostSummary` | Not touched — existing records from initial backfill are preserved |
| Feature flag | `DASHBOARD_COLLECTION` (checked in hook before Task creation) |

---

## Configuration

`settings.DASHBOARD_COLLECTION` dict keys relevant to this change:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `False` | Enables the feature flag. Hook only fires and initial backfill only runs when `True`. |
| `INITIAL_BACKFILL_DAYS` | `90` | How many days of historical data `collect_dashboard_reports_initial_data` collects on first run. |
| `BACKFILL_BATCH_SIZE` | `10000` | Number of job records fetched and committed per batch during backfill. |

Example settings override:

```python
DASHBOARD_COLLECTION = {
    "enabled": True,
    "INITIAL_BACKFILL_DAYS": 30,
    "BACKFILL_BATCH_SIZE": 5000,
}
```

---

## Collection lifecycle

```
DASHBOARD_COLLECTION enabled
        │
        ▼
initial_dashboard_collection (one-off)
  └── dashboard_jobs collector — cursor-paginated batches of BACKFILL_BATCH_SIZE
        ├── Batch 1: fetch min_id → min_id+N, commit → advance cursor
        ├── Batch 2: fetch next N, commit → advance cursor  (retry resumes here)
        └── ... until cursor >= max_id
  └── Populates JobData + JobLabel + JobHostSummary
        │
        ▼
Every hour at :10 — hourly_unified_jobs
  ├── unified_jobs_dashboard collector → HourlyMetricsCollection (rollup)
  └── post_collect_hook fires
        └── sync_dashboard_job_records Task created (get_or_create, safe on retry)
              └── JobData + JobLabel updated (JobHostSummary records preserved)
```

---

## What was not changed

- The anonymised rollup pipeline (`JobsAnonymizedRollup`, `HourlyMetricsCollection`, `DailyMetricsSummary`, Segment shipping)
- `cleanup_dashboard_reports_old_data` retention task
- `collect_dashboard_reports_data` — remains registered for manual/ad-hoc use
- `dashboard_jobs` collector in metrics-utility — kept for the initial backfill path
- All snapshot and other hourly collectors
