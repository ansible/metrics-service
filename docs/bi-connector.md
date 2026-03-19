# BI Connector Guide

This service exposes two sets of read-only REST API endpoints that BI tools can query directly, acting as a single data source for both pre-aggregated metrics and live Controller data.

## Authentication

All endpoints require a long-lived API token.

```bash
# Create a token for a user
uv run ./manage.py drf_create_token <username>
```

Pass the token in every request:

```
Authorization: Token <your-token>
```

---

## Endpoints

### Layer 1 — Pre-aggregated metrics (metrics-service DB)

These return data already collected and rolled up by the metrics pipeline. Fast, no AWX DB load.

| Endpoint | Description | Key filters |
|---|---|---|
| `GET /api/v1/metrics/daily/` | List daily summaries | `summary_date`, `summary_date__gte`, `summary_date__lte`, `status` |
| `GET /api/v1/metrics/daily/<date>/` | Single day detail (e.g. `2025-06-13`) | — |
| `GET /api/v1/metrics/hourly/` | List hourly collections | `collector_type`, `collection_timestamp__gte`, `collection_timestamp__lte`, `status` |
| `GET /api/v1/metrics/hourly/<id>/` | Single hourly record with raw data | — |

The daily list endpoint flattens `aggregated_metrics` into top-level fields per collector type:

- `metrics_unified_jobs`
- `metrics_job_host_summary_service`
- `metrics_credentials_service`
- `metrics_main_jobevent_service`
- `metrics_execution_environments`
- `metrics_controller_version_service`
- `metrics_table_metadata`

### Layer 2 — Live Controller data (AWX DB)

These query the AWX database directly. Mandatory `since`/`until` parameters protect the production DB from unbounded queries.

| Endpoint | Collector | Max window |
|---|---|---|
| `GET /api/v1/controller/jobs/` | Unified jobs | 7 days |
| `GET /api/v1/controller/hosts/` | Job host summaries | 7 days |
| `GET /api/v1/controller/credentials/` | Credentials usage | 7 days |
| `GET /api/v1/controller/events/` | Job events (event modules) | **3 days** |
| `GET /api/v1/controller/snapshot/` | Current state (EEs, version, table metadata, config) | — |

`since` and `until` must be ISO 8601 datetimes. Requests exceeding the max window return `400`.

The snapshot endpoint optionally accepts a `?collectors=` query param to subset results:

```
GET /api/v1/controller/snapshot/?collectors=config,controller_version_service
```

---

## Example requests

```bash
TOKEN="your-token-here"

# Daily summary list
curl -H "Authorization: Token $TOKEN" \
  "http://localhost:8000/api/v1/metrics/daily/?summary_date__gte=2025-01-01"

# Single day detail
curl -H "Authorization: Token $TOKEN" \
  "http://localhost:8000/api/v1/metrics/daily/2025-06-13/"

# Hourly collections for unified_jobs
curl -H "Authorization: Token $TOKEN" \
  "http://localhost:8000/api/v1/metrics/hourly/?collector_type=unified_jobs"

# Live jobs (max 7-day window)
curl -H "Authorization: Token $TOKEN" \
  "http://localhost:8000/api/v1/controller/jobs/?since=2025-03-12T00:00:00Z&until=2025-03-19T00:00:00Z"

# Current state snapshot
curl -H "Authorization: Token $TOKEN" \
  "http://localhost:8000/api/v1/controller/snapshot/"
```

---

## Testing with Grafana

[Grafana](https://grafana.com/) with the [Infinity datasource plugin](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/) can call the REST endpoints directly — no database driver needed.

### Install

```bash
brew install grafana

# Install the Infinity plugin (requires sudo or fixing directory ownership first)
sudo grafana cli plugins install yesoreyeram-infinity-datasource
# OR fix ownership then install without sudo:
sudo chown -R $(whoami) /usr/local/var/lib/grafana/plugins
grafana cli plugins install yesoreyeram-infinity-datasource

brew services restart grafana
```

Open `http://localhost:3000` (default credentials: admin / admin).

### Add the datasource

1. **Connections → Add new connection → search "Infinity"**
2. Set base URL to `http://127.0.0.1:8000`
3. Under **Auth → Custom HTTP Headers**, add:
   - Header: `Authorization`
   - Value: `Token <your-token>`
4. Save and test

### Example panels

**Daily jobs trend (time series)**
- Type: Time series
- URL: `http://127.0.0.1:8000/api/v1/metrics/daily/`
- Parser: JSON
- Rows/Root: `results`
- Columns: `summary_date`, `metrics_unified_jobs.jobs_total`

**Hourly collection status (table)**
- URL: `http://127.0.0.1:8000/api/v1/metrics/hourly/?collector_type=unified_jobs`
- Parser: JSON
- Rows/Root: `results`

**Current Controller state (stat panels)**
- URL: `http://127.0.0.1:8000/api/v1/controller/snapshot/`
- Parser: JSON
- Extract nested fields from `collectors.controller_version_service`, `collectors.table_metadata`, etc.

---

## Alternative BI tools

### Metabase (no REST support — connects to PostgreSQL directly)

```bash
docker run -d -p 3001:3000 --name metabase metabase/metabase
```

Connect to the metrics-service PostgreSQL database. Use SQL questions to query `tasks_dailymetricssummary` and `tasks_hourlymetricscollection` directly. JSON column extraction requires PostgreSQL `->` / `->>` operators.

### Evidence (code-based, SQL-driven)

```bash
npx degit evidence-dev/template my-metrics-reports
cd my-metrics-reports && npm install && npm run dev
```

Write SQL in markdown files, connect to the metrics-service PostgreSQL.

---

## Building a custom connector (.mez / .taco)

For enterprise BI tools (Tableau, Power BI) that require a native connector:

1. **Auth**: Use the token endpoint or configure OAuth2 (DAB includes `ansible_base.oauth2_provider`)
2. **Schema declaration**: Map the flat fields from `/api/v1/metrics/daily/` to typed columns
3. **Data fetching**: Call the Layer 1 endpoints with date range filters; handle the paginated `results` array
4. **Layer 2**: Call the controller endpoints with mandatory `since`/`until` params; handle the `data` key in the response

The connector declares a unified schema spanning both layers. From the BI tool's perspective it is one data source; the split between pre-aggregated and live data is an implementation detail.
