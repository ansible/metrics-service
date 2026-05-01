# Dashboard Collection Merge — Implementation Plan

## Problem

Two separate collection paths hit the Controller DB every hour:

| Path | Schedule | Collector | Destination |
|------|----------|-----------|-------------|
| Anonymised rollup | :05 — `job_host_summary_service` | Controller DB | `HourlyMetricsCollection` → `DailyMetricsSummary` → Segment |
| Anonymised rollup | :10 — `unified_jobs` | Controller DB | `HourlyMetricsCollection` → `DailyMetricsSummary` → Segment |
| Dashboard sync | Every 6 hours — `dashboard_jobs` | Controller DB | `JobData` → automation-reports |

The 6-hourly `dashboard_jobs` collector duplicates most of the data already collected by `unified_jobs`, adding 2 unnecessary Controller DB queries and an inconsistent collection cadence.

## Goal

- Eliminate the 6-hourly collection entirely
- Reuse the data the `unified_jobs` hourly collection already gathers
- Keep total Controller DB calls at 2 per hour (no increase)
- Keep the one-time historical backfill intact and configurable

---

## Key Architectural Constraint

`HourlyMetricsCollection.raw_data` stores only the **anonymised rollup JSON** produced by `rollup_processor.prepare()` — individual job records are discarded after that step. Dashboard data therefore cannot be derived from `HourlyMetricsCollection`; the raw DataFrame must be tapped before rollup processing.

---

## Design

### Hook pattern in `generic_collect_metrics`

A `post_collect_hook(raw_data)` optional parameter is added to `generic_collect_metrics` in `apps/tasks/utils.py`. The hook is called immediately after `collector.gather()` returns the raw DataFrame, before the rollup processor runs. Hook failures are caught and logged as warnings so they never abort the main collection.

### Hook wired to `unified_jobs` only

`collect_hourly_metrics` builds the hook when `collector_type == "unified_jobs"` and the `DASHBOARD_COLLECTION` feature flag is enabled. The hook:

1. Filters the DataFrame to `status IN ('failed', 'successful')` and `launch_type != 'sync'` (matching the original `dashboard_jobs` filter)
2. Selects only the columns needed for `JobData`
3. Converts pandas Timestamps to ISO strings for JSON serialisation
4. Creates a `sync_dashboard_job_records` Task via `Task.objects.get_or_create` (unique name per hour prevents duplicates on retries)

### `sync_dashboard_job_records` task

A new dispatcherd task that receives the serialised job rows in `task_data.raw_jobs` and writes them to `JobData` via the existing `create_or_update_from_awx` path. Passes `host_summaries=None` (not `[]`) to preserve `JobHostSummary` records created by the initial backfill — a `None` guard was added to `_sync_host_summaries` for this purpose.

### Initial backfill

`collect_dashboard_reports_initial_data` still runs once via `dashboard_jobs` to populate up to N days of historical data (default 90, configurable via `settings.DASHBOARD_COLLECTION['INITIAL_BACKFILL_DAYS']`). After it completes, no follow-up cron task is created — ongoing sync is driven automatically by the `unified_jobs` hook.

### New `unified_jobs_dashboard` collector (metrics-utility)

Rather than modifying `unified_jobs` (which is used by the CLI billing/CCSP pipeline), a new collector `unified_jobs_dashboard` was created that extends the base query with the additional fields the dashboard needs.

| New column | Source |
|---|---|
| `modified` | `main_unifiedjob.modified` |
| `project_id` | `main_project.unifiedjobtemplate_ptr_id` |
| `project_name` | new `ujp` alias on `main_unifiedjobtemplate` |
| `launched_by_id` | CASE on `launch_type IN ('manual','relaunch')` + `auth_user.id` |
| `launched_by_username` | same CASE + `auth_user.username` |
| `label_ids` | correlated subquery: `STRING_AGG` over `main_unifiedjob_labels` |
| `num_hosts` | correlated subquery: `COUNT(*)` over `main_jobhostsummary` |

New JOINs: `LEFT JOIN auth_user`, `LEFT JOIN main_unifiedjobtemplate AS ujp`.

`unified_jobs` is unchanged. In metrics-service the `"unified_jobs"` registry entry in `collect_hourly_metrics` now points to `unified_jobs_dashboard` as its collector function; `JobsAnonymizedRollup` ignores the extra columns.

### Batched initial backfill

The `dashboard_jobs` collector and its queries were extended to support cursor-based pagination so the 90-day backfill does not load all records into memory at once.

**How it works:**

1. `_get_job_id_range` runs `SELECT MIN(id), MAX(id)` for the filtered window to establish bounds
2. `_collect_data` loops: fetches up to `BACKFILL_BATCH_SIZE` records with `id > after_id ORDER BY id LIMIT batch_size`, commits each batch atomically, then advances the cursor
3. On retry after failure, the cursor is recovered from the DB — `MAX(job_id)` of already-synced `JobData` records within `[min_id, max_id]` — so no records are re-fetched

New query functions added to `metrics_utility/library/collectors/dashboard/queries.py`:

| Function | Purpose |
|---|---|
| `get_min_max_job_id_query` | Returns `MIN(id)` / `MAX(id)` for the window |
| `get_jobs_batch_query` | Cursor-paginated jobs query (`id > after_id ORDER BY id LIMIT n`) |
| `get_job_labels_for_ids_query` | Fetches labels for a known set of job IDs via `ANY(%s)` |
| `get_job_host_summaries_for_ids_query` | Fetches host summaries for a known set of job IDs |

`dashboard_jobs` accepts two new optional keyword arguments (`after_id`, `batch_size`). When neither is provided the collector behaves exactly as before — full backward compatibility for the CLI.

---

## Timestamp semantic change

`dashboard_jobs` filtered by `modified`; `unified_jobs` filters by `finished`. For terminal-state jobs these are nearly always the same moment. Switching to `finished` is intentional — it is consistent with the rest of the rollup pipeline and more predictable.

---

## What was removed

- `daily_dashboard_collection` task from `DASHBOARD_COLLECTION_GROUP` — no longer needed
- The follow-up task creation logic in `collect_dashboard_reports_initial_data`
- `Task` and `DASHBOARD_COLLECTION_GROUP` imports from `dashboard_reports/tasks.py`

## What was kept unchanged

- `collect_dashboard_reports_initial_data` — still calls `dashboard_jobs` for the historical backfill
- `dashboard_jobs` collector in metrics-utility — kept for the initial backfill path
- `collect_dashboard_reports_data` — kept as a registered callable for manual/ad-hoc use
- `JobData`, `JobLabel`, `JobHostSummary` models
- `HourlyMetricsCollection`, `DailyMetricsSummary`, anonymised rollup pipeline
- All other hourly/snapshot collectors and their rollup processors
- `cleanup_dashboard_reports_old_data`
