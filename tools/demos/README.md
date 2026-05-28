# Metrics Service — BI Connector Demo

A self-contained Docker Compose environment that proves BI tools can connect to
live AAP metrics via the metrics-service REST API: token-authenticated, per-user
throttled, and feature-flag gated.

This environment is designed for stakeholder demos and POC sign-off of the BI
connector feature.

---

## What's included

| Service | Container | URL |
|---|---|---|
| PostgreSQL (both DBs) | `demo-postgres` | `localhost:5432` |
| Metrics Service API | `demo-metrics-web` | http://localhost:8000 |
| Grafana | `demo-grafana` | http://localhost:3000 |
| Init (one-shot) | `demo-metrics-init` | — |

Two databases run on the single PostgreSQL instance:

| Database | User | Password | Contents |
|---|---|---|---|
| `awx` | `awx` | `awx` | Full AWX controller schema + seeded jobs, hosts, credentials, instances |
| `metrics_service` | `metrics_service` | `metrics_service` | Metrics service application data |

---

## Quick start

```bash
cd tools/demos
docker compose up --build
```

Wait for `demo-metrics-init` to exit successfully — it runs migrations, seeds
demo data, and sets up the API token. Check its output with:

```bash
docker compose logs demo-metrics-init
```

Once it exits, the following are ready:

- **Metrics Service API:** http://localhost:8000
- **Interactive API docs:** http://localhost:8000/api/docs/
- **Grafana:** http://localhost:3000

---

## Demo credentials

| Resource | Value |
|---|---|
| API login | `demo_admin` / `demo_password` |
| BI connector token | `demo-bi-connector-token` |
| Grafana | `admin` / `admin` |

The token is fixed on every boot — no need to copy it from logs.

---

## Pre-loaded demo data

### AWX controller database (seeded from SQL at first boot)

- **5 controller instances** — versions 4.7.2, 1.0, 24.1.0, 24.2.0, 23.5.0
- **100 host metrics** — spread across multiple inventories
- **Unified jobs** — 3 jobs per hour with matching job host summaries
- **Job events** — partitioned `main_jobevent` table with events per job
- **Credentials** — 5 types linked to jobs
- **Feature flags** — 3 DAB feature flags

### Metrics service database (seeded by `seed_bi_demo_data`)

- **30 days** of `DailyMetricsSummary` records
- **7 days** of `HourlyMetricsCollection` records
- **100** `HostMetric` automation records (Layer 1 stored)
- **300** `JobHostSummary` records (Layer 1 stored)
- **5** collection batch records

---

## BI Connector endpoints

All endpoints require the `Authorization: Token demo-bi-connector-token` header.
Replace `localhost:8000` with `demo-metrics-web:8000` when calling from inside
another container (e.g., Grafana panels).

### Layer 1 — Pre-aggregated metrics

These endpoints return data from the metrics-service database directly.
Responses are synchronous (200 OK).

```bash
# 30 days of daily summaries
curl -s \
  -H "Authorization: Token demo-bi-connector-token" \
  http://localhost:8000/api/v1/bi/metrics/daily/ | python3 -m json.tool

# 7 days of hourly collections
curl -s \
  -H "Authorization: Token demo-bi-connector-token" \
  http://localhost:8000/api/v1/bi/metrics/hourly/ | python3 -m json.tool
```

### Layer 1 — Stored billing data

```bash
# 100 host automation records
curl -s \
  -H "Authorization: Token demo-bi-connector-token" \
  http://localhost:8000/api/v1/bi/stored/host-metrics/

# 300 job-host summary records
curl -s \
  -H "Authorization: Token demo-bi-connector-token" \
  http://localhost:8000/api/v1/bi/stored/job-host-summaries/

# Collection batch history
curl -s \
  -H "Authorization: Token demo-bi-connector-token" \
  http://localhost:8000/api/v1/bi/stored/batches/
```

### Layer 2 — Live AWX data (async)

Layer 2 queries run against the live AWX controller database. Because these can
be slow, they are **asynchronous**: the initial request returns `202 Accepted`
with a `task_id`, and you poll for the result.

> **Note:** Date windows are enforced. The default maximum is **7 days** for
> jobs/hosts/credentials and **3 days** for events. Requests outside this range
> are rejected.

**Step 1 — submit the request:**

```bash
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "Authorization: Token demo-bi-connector-token" \
  "http://localhost:8000/api/v1/bi/controller/jobs/?since=2025-06-01T00:00:00Z&until=2025-06-07T23:59:59Z")

TASK_ID=$(echo "$RESPONSE" | head -1 | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
echo "Task ID: $TASK_ID"
```

**Step 2 — poll until complete:**

```bash
curl -s \
  -H "Authorization: Token demo-bi-connector-token" \
  "http://localhost:8000/api/v1/tasks/${TASK_ID}/" | python3 -m json.tool
# Repeat until "status": "completed" — then read result_data.data
```

**Other Layer 2 endpoints:**

```bash
# Snapshot of controller state (synchronous)
curl -s \
  -H "Authorization: Token demo-bi-connector-token" \
  http://localhost:8000/api/v1/bi/controller/snapshot/
```

---

## Grafana walkthrough

1. Open http://localhost:3000 and log in as **admin / admin**.
2. Navigate to **Dashboards → Metrics Service** folder.
3. Open **"Metrics Service — Overview"**.

### Dashboards

| Dashboard | UID | Source | Description |
|---|---|---|---|
| Metrics Service — Overview | `metrics-service-overview` | Metrics Service DB + AWX DB | Task health, collection status, AWX jobs and instances |
| BI — Host Automation Analytics | `bi-host-automation` | Metrics Service DB | Host counts, top hosts by automation, first/last active timeseries, host inventory table |
| BI — Job Execution Analytics | `bi-job-execution` | Metrics Service DB | Job execution counts, breakdown by org/inventory, top hosts, executions over time |
| BI — Daily Metrics Trends | `bi-metrics-trends` | Metrics Service DB | Daily job trends (30 days), host tracking, credential breakdown, success rate gauge, hourly volume |

### Metrics Service — Overview panels

| Panel | Source | What it shows |
|---|---|---|
| Total / Running / Failed Tasks | Metrics Service DB | Live task counts |
| Daily Summaries | Metrics Service DB | Count of seeded daily records |
| Hourly Collections | Metrics Service DB | Count of seeded hourly records |
| Task Status Distribution | Metrics Service DB | Pie chart of task states |
| Hourly Collections by Collector Type | Metrics Service DB | Breakdown by collector |
| Daily Metrics Summaries (last 30 days) | Metrics Service DB | Table of daily data |
| Recent Tasks | Metrics Service DB | Latest task executions |
| AWX — Recent Unified Jobs | AWX DB | Jobs from the seeded AWX data |
| AWX — Controller Instances | AWX DB | Instance inventory |

### Infinity datasource (BI Connector panels)

The **Metrics Service BI Connector** Infinity datasource is pre-provisioned and
configured with the fixed token. You can build panels against any BI connector
endpoint directly in Grafana.

Example panel configuration:

- **URL:** `http://demo-metrics-web:8000/api/v1/bi/metrics/daily/`
- **Parser:** JSON
- **Rows root:** `results`
- **Header:** `Authorization` = `Token demo-bi-connector-token`

---

## Connecting Power BI

1. Open **Power BI Desktop**.
2. **Home → Get Data → Web**.
3. Select **Advanced**.
4. **URL:** `http://localhost:8000/api/v1/bi/metrics/daily/`
5. Under **HTTP request headers**, add:
   - Header: `Authorization`
   - Value: `Token demo-bi-connector-token`
6. Click **OK → JSON** → expand the `results` list.
7. Repeat for other endpoints as separate queries and combine in the data model
   using shared keys (e.g., `date`, `collector_type`).

> **Note:** Power BI scheduled refresh requires a publicly accessible URL. For
> a local demo, use the **Direct Connection** option or run the service on an
> accessible host.

---

## Feature flag control

The `BI_CONNECTOR` flag gates all `/api/v1/bi/` endpoints. When disabled, every
endpoint returns **404 Not Found**.

### Toggle via environment variable (no DB required)

```bash
# Disable (add to docker-compose.yml environment or .env)
METRICS_SERVICE_FEATURE_ENABLED__BI_CONNECTOR=false

# Re-enable
METRICS_SERVICE_FEATURE_ENABLED__BI_CONNECTOR=true
```

### Toggle via API at runtime

```bash
# Disable
curl -s -X PATCH \
  -H "Authorization: Token demo-bi-connector-token" \
  -H "Content-Type: application/json" \
  -d '{"current_value": "false"}' \
  http://localhost:8000/api/v1/feature_flags/BI_CONNECTOR/

# Re-enable
curl -s -X PATCH \
  -H "Authorization: Token demo-bi-connector-token" \
  -H "Content-Type: application/json" \
  -d '{"current_value": "true"}' \
  http://localhost:8000/api/v1/feature_flags/BI_CONNECTOR/
```

Verify a BI endpoint returns 404 while the flag is off:

```bash
curl -v \
  -H "Authorization: Token demo-bi-connector-token" \
  http://localhost:8000/api/v1/bi/metrics/daily/
# Expect: HTTP/1.1 404 Not Found
```

---

## Throttle behaviour

Each user is limited to **30 requests per hour** on all BI connector endpoints.
Exceeding the limit returns `429 Too Many Requests`. The demo uses a single
`demo_admin` token, so all requests share one bucket.

---

## Stopping and cleanup

```bash
# Stop (preserve data volumes — state survives restart)
docker compose down

# Stop and wipe all data volumes (fresh start next time)
docker compose down -v
```

After `docker compose down -v`, the next `docker compose up --build` will
re-seed everything from scratch.

---

## Useful commands

| Command | Purpose |
|---|---|
| `docker compose logs -f` | Tail all service logs |
| `docker compose logs -f demo-metrics-web` | Tail web service only |
| `docker compose logs demo-metrics-init` | Check init output and token |
| `docker exec demo-metrics-web python manage.py shell` | Django shell |
| `docker exec demo-metrics-web python manage.py seed_bi_demo_data` | Re-seed BI demo data |
| `docker exec -it demo-postgres psql -U metrics_service -d metrics_service` | Connect to metrics DB |
| `docker exec -it demo-postgres psql -U awx -d awx` | Connect to AWX DB |
