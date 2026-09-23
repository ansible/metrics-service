# Analytics Collection

Analytics collection stores the raw output of enabled metrics-utility collectors
in `AnalyticsPayload`. The stored row is a collection envelope: collector name,
source, collection bounds, collection timestamps, and the raw JSON payload.

The read API is available under `/api/v1/analytics/` and is restricted to users
with the System Administrator or Platform Auditor role.

## Collector Registry

The registry is the source of truth in
[`apps/analytics/registry.py`](../apps/analytics/registry.py). Each entry has:

- `name`: public/API/storage name, in `group.function` form
- `collector_type`: internal task registry key
- `mode`: `hourly`, `daily`, or `snapshot`
- `enabled`: whether the collector is persisted and exposed
- `database`: source database, defaulting to `awx`
- `note`: explanation for disabled or excluded entries

`accepts_since_until` is derived from `mode`. It describes whether the collector
can receive `since` and `until` bounds; it does not require both bounds to be
present.

## Enabled Collectors

All enabled collectors are persisted and exposed by the read API.

| Name | `collector_type` | Mode | `accepts_since_until` |
| --- | --- | --- | --- |
| `controller.unified_jobs_dashboard` | `unified_jobs` | hourly | yes |
| `controller.job_host_summary_service` | `job_host_summary_service` | hourly | yes |
| `controller.credentials_service` | `credentials_service` | hourly | yes |
| `controller.main_jobevent_service` | `main_jobevent_service` | hourly | yes |
| `controller.events_table` | `events_table` | hourly | yes |
| `controller.workflow_job_node_table` | `workflow_job_node_table` | hourly | yes |
| `controller.query_info` | `query_info` | hourly | yes |
| `controller.execution_environments` | `execution_environments` | snapshot | no |
| `controller.config` | `config` | snapshot | no |
| `controller.controller_version_service` | `controller_version_service` | snapshot | no |
| `controller.table_metadata` | `table_metadata` | snapshot | no |
| `controller.feature_flags_service` | `feature_flags_service` | snapshot | no |
| `controller.counts` | `counts` | snapshot | no |
| `controller.cred_type_counts` | `cred_type_counts` | snapshot | no |
| `controller.host_metric_summary_monthly_table` | `host_metric_summary_monthly_table` | snapshot | no |
| `controller.instance_info` | `instance_info` | snapshot | no |
| `controller.inventory_counts` | `inventory_counts` | snapshot | no |
| `controller.org_counts` | `org_counts` | snapshot | no |
| `controller.projects_by_scm_type` | `projects_by_scm_type` | snapshot | no |
| `controller.unified_job_template_table` | `unified_job_template_table` | snapshot | no |
| `controller.workflow_job_template_node_table` | `workflow_job_template_node_table` | snapshot | no |
| `controller.main_host` | `main_host` | snapshot | no |
| `controller.main_host_daily` | `main_host_daily` | daily | yes |
| `controller.main_hostmetric` | `main_hostmetric` | daily | yes |

## Disabled And Excluded Collectors

These entries remain in the registry so their status and reason are visible to
developers. They are not persisted or exposed by the analytics API.

| Name | `collector_type` | Status | Reason |
| --- | --- | --- | --- |
| `service.task_executions_service` | `task_executions_service` | disabled | Reads metrics-service operational task data, not customer data; product decision needed. |
| `controller.main_indirectmanagednodeaudit` | `indirect_managed_nodes` | disabled | Requires the ANSTRAT-2160 path to reach GA. |
| `controller.job_host_summary` | `job_host_summary` | excluded | Legacy collector superseded by `job_host_summary_service`. |
| `controller.main_jobevent` | `main_jobevent_legacy` | excluded | Legacy collector superseded by `main_jobevent_service`. |
| `controller.unified_jobs` | `unified_jobs_base` | excluded | Base collector superseded by `unified_jobs_dashboard`. |
| `controller.config_django` | `config_django` | excluded | AWX in-process collector superseded by the SQL `config` collector. |
| `others.total_workers_vcpu` | `total_workers_vcpu` | excluded | Prometheus/CLI billing path, not registered in metrics-service. |
| `dashboard.dashboard_jobs` | `dashboard_jobs` | excluded | Belongs to the separate dashboard synchronization pipeline. |

## Read API

The analytics root lists enabled collectors and their row URLs:

```http
GET /api/v1/analytics/
```

The response contains entries such as:

```json
{
  "collectors": [
    {
      "name": "controller.config",
      "mode": "snapshot",
      "accepts_since_until": false,
      "rows_url": "https://metrics.example.com/api/v1/analytics/controller.config/"
    }
  ]
}
```

The collector endpoint returns paginated collection envelopes:

```http
GET /api/v1/analytics/controller.unified_jobs_dashboard/
```

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 42,
      "collector": "controller.unified_jobs_dashboard",
      "source": "local",
      "since": "2026-08-17T10:00:00Z",
      "until": "2026-08-17T11:00:00Z",
      "started_at": "2026-08-17T11:01:02Z",
      "finished_at": "2026-08-17T11:01:08Z",
      "payload": [
        {"id": 100, "status": "successful"},
        {"id": 101, "status": "failed"}
      ]
    }
  ]
}
```

The actual list response includes `count`, `next`, `previous`, and `results`.
Use `page` and `page_size` for pagination. `count_disabled=true` can omit the
count and navigation links when supported by the paginator.

### Window Filters

Filtering uses half-open interval overlap. A stored row matches a query when:

```text
stored_until IS NULL OR stored_until > query_since
stored_since IS NULL OR stored_since < query_until
```

The comparisons are applied only when the corresponding query bound is present.
Therefore:

- No query bounds returns every collection for the collector, newest first.
- `?since=2026-08-17T11:00:00Z` means `[11:00, +infinity)`.
- `?until=2026-08-17T11:00:00Z` means `(-infinity, 11:00)`.
- Both bounds filter the requested `[since, until)` interval.
- Invalid timestamps and `until <= since` return `400`.

Examples:

| Stored row | Query | Result |
| --- | --- | --- |
| `[10:00, 11:00)` | `[10:00, 11:00)` | match |
| `[10:00, 11:00)` | `[11:00, 12:00)` | no match |
| `[09:00, 10:00)` | `[10:00, 11:00)` | no match |
| `[10:00, infinity)` | `(-infinity, 11:00)` | match |
| `(-infinity, 11:00)` | `[11:00, 12:00)` | no match |
| `[null, null]` | any valid query | match |

Every successful collection is retained. Repeated windows and repeated snapshots
are not upserts.

## Creating Collection Tasks

Tasks are created through `POST /api/v1/tasks/`. The task API accepts
`function_name`, JSON `task_data`, optional `scheduled_time`, and optional
`cron_expression`. Immediate tasks omit both scheduling fields. The scheduler
submits immediate tasks during its periodic sync; recurring task rows create a
new child task on each cron fire.

### One Snapshot With Defaults

For a snapshot, only the public collector name is needed:

```http
POST /api/v1/tasks/
```

```json
{
  "name": "analytics-config-once",
  "function_name": "collect_analytics_on_demand",
  "task_data": {
    "collector": "controller.config"
  },
  "scheduled_time": null,
  "cron_expression": null
}
```

The task uses the collector's default behavior. A snapshot receives no
`since`/`until` bounds.

### Daily Cron Task

Use the dedicated recurring-task endpoint when a recurring daily schedule is wanted:

```http
POST /api/v1/tasks/schedule_recurring/
```

```json
{
  "name": "analytics-main-host-daily",
  "function_name": "collect_daily_metrics",
  "task_data": {
    "collector_type": "main_host_daily"
  },
  "cron_expression": "0 2 * * *"
}
```

The response contains a success message and `task_id`. The recurring row is a
template. Each cron fire creates a non-recurring child task, which is then
dispatched normally.

### Custom Window Task

For a specific collection window, pass ISO timestamps in `task_data`:

```json
{
  "name": "analytics-unified-jobs-hour",
  "function_name": "collect_analytics_on_demand",
  "task_data": {
    "collector": "controller.unified_jobs_dashboard",
    "since": "2026-08-17T10:00:00Z",
    "until": "2026-08-17T11:00:00Z"
  },
  "scheduled_time": null,
  "cron_expression": null
}
```

The intended on-demand POST mapping is the same task data: a future
`POST /api/v1/analytics/<collector>/collect/` with no body would correspond to
the name-only snapshot task, while a request body containing `since` and `until`
would correspond to the custom-window task. The read-only analytics API does not
currently expose that POST route; claim and re-collection semantics are still
under review.
