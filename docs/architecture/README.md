# metrics-service Architecture

Architecture diagrams for the metrics-service Django application. Each diagram focuses on a distinct subsystem. Mermaid diagrams render natively on GitHub; `.drawio` files can be opened in [draw.io](https://app.diagrams.net) for editing.

## Diagrams

| # | File | Topic |
|---|------|-------|
| 1 | [System Overview](01-system-overview.md) | 4-container deployment, external integrations, top-level data flows |
| 2 | [Task System](02-task-system.md) | Task model, TaskExecution, dispatcherd claim/execute, advisory locks, stuck-task detection |
| 3 | [APScheduler & Task Groups](03-apscheduler.md) | Scheduled job groups, cron triggers, feature flags gating, dispatch to PostgreSQL |
| 4 | [Dashboard Collection](04-dashboard-collection.md) | AWX job data mirroring pipeline, JobData models, ROI report API |
| 5 | [Metrics Data Pipeline](05-metrics-pipeline.md) | Hourly collection → daily rollup → anonymization → Segment shipping |
| 6 | [Authentication & Request Flow](06-auth-flow.md) | JWT auth via Gateway, ServicePrefixMiddleware, RBAC, resource registry sync |

## Key Concepts

### Deployment Stack

metrics-service runs as four containers that share a single image, differentiated by entrypoint:

| Container | Entrypoint | Role |
|-----------|-----------|------|
| `init` | migrations + `init-system-tasks` | One-shot setup on startup |
| `web` | Gunicorn + Nginx | Serves REST API on :8080/:8443 |
| `scheduler` | APScheduler process | Cron scheduling + pg_notify dispatch |
| `dispatcherd` | pg_notify listener | Background task execution |

### Django Apps

| App | Purpose |
|-----|---------|
| `apps.core` | User/Org/Team models, JWT middleware, Prometheus view, Swagger docs |
| `apps.tasks` | Task + TaskExecution models, all collectors and pipeline functions, task REST API |
| `apps.dynamic_settings` | DB-backed runtime feature flags (Setting model) |
| `apps.dashboard_reports` | Automation Dashboard: JobData models, ROI report API, AWX filter dropdowns |

### Feature Flags

| Flag | Default | Gates |
|------|---------|-------|
| `METRICS_COLLECTION` | `true` | All hourly/snapshot/daily collectors and rollup |
| `ANONYMIZED_DATA_COLLECTION` | `true` | Anonymization and Segment shipping |
| `DASHBOARD_COLLECTION` | `true` | Dashboard collection, sync tasks, cleanup |
| `INDIRECT_NODE_COLLECTION` | `false` | Indirect managed node daily audit |

Toggle at runtime via `POST /api/v1/dynamic_settings/` (no restart required) or via `METRICS_SERVICE_FEATURE__<KEY>=false` env var (requires restart).

### External Dependencies

| Service | Connection | Purpose |
|---------|-----------|---------|
| AAP Gateway | JWT (`X-DAB-JW-TOKEN`) + service key | Auth + resource registry sync |
| AWX PostgreSQL | Direct psycopg3 read-only connection | Source of all metrics data |
| Segment.com | `SEGMENT_WRITE_KEY` | Daily anonymized payload destination |
| Own PostgreSQL | Django ORM + pg_notify | State, task queue, advisory locks |
