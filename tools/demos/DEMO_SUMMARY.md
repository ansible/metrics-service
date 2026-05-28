# Metrics Service — BI Connector POC Demo

**Purpose:** Sign-off demo for the BI connector feature.  
**Date:** May 2026 | **Branch:** `BI-Connector`

---

## Quick Start

```bash
cd tools/demos

# First run — builds images and seeds all data (~5 min)
podman-compose up --build

# Subsequent runs (data already seeded, volumes intact)
podman-compose up -d
```

Watch for `demo-metrics-init` to exit successfully before using the API:

```bash
podman logs -f demo-metrics-init
# Look for: "=== Demo initialisation complete ==="
```

Redash takes an extra ~30 seconds after `demo-metrics-init` completes.

---

## Stack Services

| Container | Role |
|---|---|
| `demo-postgres` | Single PostgreSQL instance hosting `awx`, `metrics_service`, and `redash` databases |
| `demo-metrics-init` | One-shot: runs migrations, seeds demo data, creates API token |
| `demo-metrics-web` | Metrics service (Django + dispatcherd + APScheduler) |
| `demo-grafana` | Grafana with pre-provisioned datasources and 13 dashboards |
| `demo-redash-redis` | Redis (required by Redash job queue) |
| `demo-redash-init` | One-shot: initialises Redash DB schema |
| `demo-redash` | Redash web server |
| `demo-redash-worker` | Redash background query worker |
| `demo-redash-setup` | One-shot: creates admin user, data source, queries, dashboards |

---

## Access

| Service | URL | Credentials |
|---|---|---|
| Metrics Service API | http://localhost:8000/api/v1/ | `demo_admin` / `demo_password` |
| API Docs (Swagger) | http://localhost:8000/api/docs/ | — |
| BI Admin UI | http://localhost:8000/bi-admin/ | `demo_admin` / `demo_password` |
| Grafana | http://localhost:3000 | `admin` / `admin` |
| Redash | http://localhost:5002 | `admin@demo.com` / `demo_password` |
| PostgreSQL (metrics) | `localhost:5432` db=`metrics_service` | `metrics_service` / `metrics_service` |
| PostgreSQL (AWX) | `localhost:5432` db=`awx` | `awx` / `awx` |

**BI Connector API token (all endpoints):**
```
Authorization: Token demo-bi-connector-token
```

---

## Stopping the Stack

```bash
# Stop, keep data volumes (resume later)
podman-compose down

# Stop and wipe all data (full fresh start)
podman-compose down -v
```

---

## What's Seeded

### AWX Controller Database
| Table | Records | Details |
|---|---|---|
| `main_unifiedjob` | 56 | Jobs spanning ~21 days (successful / failed / canceled) |
| `main_jobevent` | 780 | 15 events per job across 8 task types and 3 environments |
| `main_jobhostsummary` | 12 | Per-host job summary records |
| `main_hostmetric` | 9 | Host automation metrics |
| `main_instance` | 7 | Controller instances (versions 4.7.2, 24.1.0, 24.2.0, etc.) |

### Metrics Service Database
| Table | Records | Details |
|---|---|---|
| `tasks_hourlymetricscollection` | 3,792 | 4 collector types × multiple days; `main_jobevent_service` includes `module_stats` and `organizations` |
| `tasks_dailymetricssummary` | 90 | 90 days; includes unified_jobs, credentials, events, org and module breakdowns |
| `bi_connector_storedhostmetric` | 100 | Hostnames across prod / staging / dev environments |
| `bi_connector_storedjobhostsummary` | 300 | Job-host pairs across 3 orgs and 5 inventories |
| `bi_connector_collectionbatch` | 16 | Scheduled and backfill batch history |

---

## BI Connector API Endpoints

All endpoints require `Authorization: Token demo-bi-connector-token`.  
Base URL: `http://localhost:8000`

### Layer 1 — Pre-aggregated Metrics (synchronous, 200 OK)

| Endpoint | Returns | Key Fields |
|---|---|---|
| `GET /api/v1/bi/metrics/daily/` | 90 daily summaries | `summary_date`, `metrics_unified_jobs.*`, `metrics_credentials_service.*`, `metrics_main_jobevent_service.*` |
| `GET /api/v1/bi/metrics/hourly/` | Hourly collection log | `collection_timestamp`, `collector_type`, `status`, `data_size_bytes` |
| `GET /api/v1/bi/metrics/modules/` | Module-level compute hours | `module`, `task_runs`, `unique_hosts`, `total_duration_hours`, `pct_of_total_hours` |
| `GET /api/v1/bi/metrics/organizations/` | Per-org job/task totals | `org_name`, `job_count`, `task_count` |
| `GET /api/v1/bi/metrics/compute-hours/` | Headline compute time | `total_automation_hours`, `person_work_days_8hr`, `person_years_240days` |

### Layer 1 — Stored Billing Data (synchronous, 200 OK)

| Endpoint | Returns | Key Filters |
|---|---|---|
| `GET /api/v1/bi/stored/host-metrics/` | 100 host records | `deleted=true/false`, `first_automation__gte=`, `hostname__icontains=` |
| `GET /api/v1/bi/stored/job-host-summaries/` | 300 job-host pairs | `organization_id=`, `job_id=`, `modified__gte=` |
| `GET /api/v1/bi/stored/batches/` | Batch history | `collector_type=`, `status=`, `batch_type=` |
| `GET /api/v1/bi/stored/indirect-audits/` | Indirect node audits | `organization_id=`, `job_id=` |

### Layer 2 — Live AWX Data (asynchronous — returns 202)

Poll `GET /api/v1/tasks/<task_id>/` until `status == "completed"`, then read `result_data.data`.

| Endpoint | Max Window | Data |
|---|---|---|
| `GET /api/v1/bi/controller/jobs/?since=&until=` | 7 days | Live unified jobs from AWX DB |
| `GET /api/v1/bi/controller/hosts/?since=&until=` | 7 days | Job host summaries from AWX DB |
| `GET /api/v1/bi/controller/credentials/?since=&until=` | 7 days | Credential usage from AWX DB |
| `GET /api/v1/bi/controller/events/?since=&until=` | 3 days | Job events from AWX DB |
| `GET /api/v1/bi/controller/snapshot/` | — | Sync: controller versions, EEs, table metadata |

**Example Layer 2 flow:**
```bash
# 1. Submit request
curl -s -H "Authorization: Token demo-bi-connector-token" \
  "http://localhost:8000/api/v1/bi/controller/jobs/?since=2025-06-13T09:00:00Z&until=2025-06-13T12:00:00Z"
# → {"task_id": 42, "status": "pending", "results_url": "/api/v1/tasks/42/"}

# 2. Poll until completed
curl -s -H "Authorization: Token demo-bi-connector-token" \
  "http://localhost:8000/api/v1/tasks/42/"
# → {"status": "completed", "result_data": {"data": [...]}}
```

### Feature Flag Control

```bash
# All /api/v1/bi/ endpoints return 404 when the flag is off
METRICS_SERVICE_FEATURE_ENABLED__BI_CONNECTOR=false

# Toggle at runtime via API (no restart needed)
curl -s -u demo_admin:demo_password -X PATCH \
  "http://localhost:8000/api/v1/feature_flags/BI_CONNECTOR/" \
  -H "Content-Type: application/json" -d '{"current_value": "false"}'
```

---

## Grafana Dashboards

Open http://localhost:3000 → Dashboards → **Metrics Service** folder.

### ✅ Live — Infinity REST API (13 dashboards)

| Dashboard | URL | What it shows |
|---|---|---|
| **BI — Automation Analytics** | `/d/bi-automation-analytics` | Compute hours, module-level breakdown, org breakdown, credential trends |
| **BI Connector Demo** | `/d/bi-connector-demo` | API metadata — daily/hourly counts, host count, batch history |
| **BI — Collection Health & Volume** | `/d/bi-collection-health` | Pipeline stats, batch history, hourly log, daily summary log |
| **BI — Credential Analytics** | `/d/bi-credentials` | 30-day credential trend by type (SSH / Vault / AWS) |
| **BI — Host Automation Analytics** | `/d/bi-host-automation` | Total/active/deleted hosts, full inventory, deleted detail |
| **BI — Host Lifecycle** | `/d/bi-host-lifecycle` | Host churn — new, stale, deleted |
| **BI — Job Events Analytics** | `/d/bi-events` | 90-day event trend, outcome breakdown, hourly log; org filter dropdown |
| **BI — Job Execution Analytics** | `/d/bi-job-execution` | Job totals, per-org filtered tables |
| **BI — Metrics Trends** | `/d/bi-metrics-trends` | 30-day jobs / hosts / credentials tables |
| **BI — Unified Jobs Trends** | `/d/bi-unified-jobs` | Daily job totals, success / failed / canceled breakdown |

### ⚠️ Mixed / Reference

| Dashboard | URL | Note |
|---|---|---|
| **BI — BHP vs Live API Gap Analysis** *(MIXED DATA)* | `/d/bi-bhp-gap-analysis` | Amber panels = BHP PDF reference (hardcoded); Blue panels = live API. Identifies API coverage gaps. |

### ❌ Not Live

| Dashboard | URL | Note |
|---|---|---|
| **BHP — AAP Forensic Analysis** *(NOT LIVE — HARDCODED)* | `/d/bi-bhp-forensic` | 35-panel recreation of a customer PDF report. All figures hardcoded from the document. |
| **Metrics Service — Overview** *(SQL DATA)* | `/d/metrics-service-overview` | Direct PostgreSQL queries — not via the BI connector API. |

---

## BI Admin UI

Available at **http://localhost:8000/bi-admin/** — login: `demo_admin` / `demo_password`

- **Status cards** — host count, job summaries, active batches, BI connector flag state
- **Collector toggles** — enable/disable individual collectors
- **Backfill form** — select collector type, date range, submit a run
- **Batch history** — auto-refreshes every 10 s, colour-coded status badges

---

## Redash — REST API BI Tool

Redash demonstrates that the BI connector API works with multiple BI tools. Its **JSON (HTTP) data source** calls the REST API directly — the same mechanism as Power BI's Web connector.

**Access:** http://localhost:5002 → `admin@demo.com` / `demo_password`

### 10 pre-loaded queries

All queries use the `Metrics Service BI Connector` data source with `Authorization: Token demo-bi-connector-token` embedded in the YAML query.

| Query | Endpoint |
|---|---|
| Host Automation - All Hosts | `/api/v1/bi/stored/host-metrics/?limit=100` |
| Host Automation - Active Hosts | `?deleted=false` |
| Host Automation - Deleted Hosts | `?deleted=true` |
| Job Execution Summary | `/api/v1/bi/stored/job-host-summaries/?limit=200` |
| Collection Batch History | `/api/v1/bi/stored/batches/?limit=50` |
| Daily Metrics — 90 Days | `/api/v1/bi/metrics/daily/?limit=90` |
| Module Compute Hours | `/api/v1/bi/metrics/modules/` |
| Organization Breakdown | `/api/v1/bi/metrics/organizations/` |
| Compute Hours Summary | `/api/v1/bi/metrics/compute-hours/` |
| Hourly Event Collections | `/api/v1/bi/metrics/hourly/?collector_type=main_jobevent_service` |

### 4 pre-built dashboards

| Dashboard | URL | Panels |
|---|---|---|
| **Host Automation Analytics** | `/dashboard/host-automation-analytics_1` | Active/deleted counters · all-hosts table · active & deleted side-by-side |
| **Compute & Module Analytics** | `/dashboard/compute-module-analytics_1` | Compute hour/work-day/year counters · module compute bar chart · org task pie · org job bar · module & org tables |
| **Job & Pipeline Health** | `/dashboard/job-pipeline-health_1` | Batch counter · batch history · job execution · hourly events tables |
| **Daily Metrics Trends** | `/dashboard/daily-metrics-trends_1` | 90-day daily metrics table · compute summary table |

### Writing a Redash query manually

In the Redash query editor, use YAML format — this allows custom HTTP headers:

```yaml
url: http://demo-metrics-web:8000/api/v1/bi/stored/host-metrics/?limit=100
headers:
  Authorization: Token demo-bi-connector-token
path: results
```

- `url` — full endpoint URL (use the internal Docker hostname `demo-metrics-web`)
- `headers` — HTTP headers sent with every request
- `path` — JSON path to the rows array (`results` for paginated endpoints, omit for top-level objects)

---

## Power BI Connection

1. Open **Power BI Desktop**
2. **Home → Get Data → Web → Advanced**
3. URL: `http://localhost:8000/api/v1/bi/stored/host-metrics/`
4. Add HTTP request header: `Authorization` = `Token demo-bi-connector-token`
5. **OK → JSON** → expand the `results` list
6. Repeat for other endpoints and combine in the data model

> For scheduled refresh, Power BI requires a publicly accessible URL. Use Direct Connection for local demos.

---

## API Coverage — What the BI Connector Provides vs Gaps

### Covered ✅
| Metric | Endpoint |
|---|---|
| Host automation history | `/api/v1/bi/stored/host-metrics/` |
| Job-host relationships | `/api/v1/bi/stored/job-host-summaries/` |
| Daily job totals (success/fail/cancel) | `/api/v1/bi/metrics/daily/` |
| Event type breakdowns (ok/failed/skipped) | `/api/v1/bi/metrics/daily/` + `/api/v1/bi/metrics/hourly/` |
| Credential counts by type | `/api/v1/bi/metrics/daily/` (dot notation) |
| Module-level compute hours | `/api/v1/bi/metrics/modules/` |
| Organisation job/task breakdown | `/api/v1/bi/metrics/organizations/` |
| Total compute hours / person-work-days / person-years | `/api/v1/bi/metrics/compute-hours/` |
| Collection pipeline health | `/api/v1/bi/stored/batches/` |
| Live AWX job/host/event data | `/api/v1/bi/controller/*` (async) |

### Remaining Gaps ❌
| Metric | Reason |
|---|---|
| Unique job templates count | No templates endpoint — not in stored models |
| Inventory scope (hosts per inventory) | Inventory data not collected by metrics-utility |
| Avg tasks/run per template | Requires template-level event correlation |

---

## Useful Commands

```bash
# Tail all logs
podman-compose logs -f

# Tail a single service
podman logs -f demo-metrics-web

# Seed additional BI demo data (idempotent)
podman exec demo-metrics-web python manage.py seed_bi_demo_data

# Django shell
podman exec -it demo-metrics-web python manage.py shell

# Connect to metrics DB
podman exec -it demo-postgres psql -U metrics_service -d metrics_service

# Connect to AWX DB
podman exec -it demo-postgres psql -U awx -d awx

# Connect to Redash DB
podman exec -it demo-postgres psql -U redash -d redash

# Trigger a backfill via API
curl -s -u demo_admin:demo_password -X POST \
  "http://localhost:8000/api/v1/bi/collector-settings/batches/" \
  -H "Content-Type: application/json" \
  -d '{"collector_type": "main_host_daily", "since": "2025-01-01T00:00:00Z", "until": "2025-06-01T00:00:00Z", "batch_type": "backfill"}'

# Reload Grafana dashboards from disk
curl -s -u admin:admin -X POST http://localhost:3000/api/admin/provisioning/dashboards/reload

# Get BI connector token (printed at end of init)
podman logs demo-metrics-init 2>&1 | grep "Token"

# Get Redash admin API key
podman exec demo-postgres psql -U redash -d redash -t \
  -c "SELECT api_key FROM users WHERE email='admin@demo.com';"
```
