# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup

```bash
# Install dependencies (project uses uv)
uv sync --dev

# Install pre-commit hooks
pre-commit install

# Configure local overrides (optional)
cp settings.local.py.example settings.local.py

# Run database migrations
.venv/bin/python manage.py migrate

# Initialize required objects (run after every migration)
python manage.py metrics_service init-service-id      # Required for DAB resource registry
python manage.py metrics_service init-default-settings # Initialize feature flag DB table
python manage.py metrics_service init-system-tasks     # Register scheduled background tasks

# Create superuser
python manage.py createsuperuser
```

### Running the Service

```bash
# Full service (Django + dispatcherd + APScheduler)
python manage.py metrics_service run

# Development server only
python manage.py runserver

# With Docker (includes PostgreSQL)
docker-compose up
```

To develop against a local `metrics-utility` checkout, add to `pyproject.toml`:
```toml
[tool.uv.sources]
metrics-utility = { path = "../metrics-utility", editable = true }
```

### Testing

```bash
# Run all tests (--reuse-db is set by default in pytest config, DB is reused between runs)
uv run pytest

# Force DB recreation when schema changes
uv run pytest --create-db

# Run specific subset
uv run pytest tests/unit/tasks/
uv run pytest -m unit
uv run pytest -m integration

# With coverage (80% minimum enforced)
uv run pytest --cov=apps --cov=metrics_service --cov-report=term-missing
```

**Coverage measurement:** Always run coverage on the module (`--cov=apps.tasks`), never on file paths. Run the full test suite, not individual files, to get accurate coverage.

### Code Quality

```bash
# Format + lint + test (via poe task runner)
uv run poe check

# Individual poe tasks
uv run poe format   # ruff format
uv run poe lint     # ruff check
uv run poe unit-test

# Type checking (gradual adoption — not enforced in CI)
mypy .
```

### Debugging

```bash
# Run a single task function directly (needs Django context)
uv run ./scripts/run_task.py hello_world

# Django shell one-liners
python manage.py shell -c "from apps.tasks.tasks import TASK_FUNCTIONS; print(list(TASK_FUNCTIONS))"

# Inspect Dynaconf settings loading (useful for diagnosing env var precedence)
uv run dynaconf inspect -m debug -f yaml    # full loading history
uv run dynaconf inspect -k VARIABLE_NAME    # single variable

# Never use plain python -c for Django imports — it fails without Django setup
```

## Architecture Overview

### App Structure

```
apps/
  core/             # Custom User/Organization/Team models, DAB integration, RBAC
  tasks/            # Background task system (models, scheduling, execution)
  dynamic_settings/ # Runtime DB-backed feature flags (Setting model)
  settings/         # Dynaconf settings layering (see below)
  dashboard/        # Web UI for task monitoring at /dashboard/
  bi_connector/     # BI tool API (Tableau, Power BI, Grafana) — token auth, per-user throttle
  dashboard_reports/ # automation-reports integration: AWX job/template data, cost models
  api/              # Thin shared API utilities
metrics_service/
  settings/         # Split Django settings (development, production, test)
```

Apps are registered in `apps/settings/defaults.py` under `project_applications`. The framework dynamically discovers URL patterns from each app by iterating `settings.LOADED_APPS` (apps starting with `apps.`) and importing their `urls.py`. URL loading order follows the order in `project_applications`; use `apps/urls.py` for patterns that must load before all app URLs.

### Databases

Two database connections are configured in `apps/settings/defaults.py`:

- **`default`** — metrics-service's own PostgreSQL DB (models, task records, settings)
- **`awx`** — read-only connection to the AWX/Controller PostgreSQL DB (BI connector Layer 2, metrics collectors). Configure via `METRICS_SERVICE_DATABASES__awx__HOST` etc. Host and password are required at runtime; they are blank by default.

### Settings Loading Order (Dynaconf)

Settings are merged in this order (later overrides earlier):

1. `metrics_service/settings.py` — framework defaults (read-only)
2. `apps/settings/defaults.py` — project-wide defaults
3. `apps/core/settings.py` — DAB-related settings
4. `apps/*/settings.py` — per-app settings
5. `apps/settings/{mode}.py` — mode-specific (dev/prod/test)
6. `settings.local.py` — local overrides (git-ignored)
7. `/etc/ansible-automation-platform/metrics_service/settings.yaml` — prod
8. `METRICS_SERVICE_*` environment variables

Use Dynaconf merge markers when extending lists/dicts in app settings:
```python
INSTALLED_APPS = "@merge_unique my_new_app"
DATABASES__default__PORT = 5433
```

### Task System (`apps/tasks/`)

The task system has several layers:

- **`models.py`** — `Task`, `TaskExecution`, `TaskChain` DB models
- **`tasks.py`** — `TASK_FUNCTIONS` registry mapping function names to callables; also `TASK_METADATA` (queue, category, parameters) and `TASK_LOCKS`
- **`tasks_system.py`** — execution machinery: wraps function calls, writes `result_data`, manages task lifecycle state
- **`task_groups.py`** — `TASK_GROUPS` config: defines what tasks run, their cron schedules, args, and which feature flag controls them. This is the source of truth for scheduled tasks — edit here, then run `init-system-tasks` to sync to DB.
- **`cron_scheduler.py`** — APScheduler integration for recurring tasks
- **`dispatcherd_config.py`** — Dispatcherd worker configuration
- **`collectors/`** — Metrics collection functions (`collect_hourly_metrics`, `collect_snapshot_metrics`, `collect_daily_metrics`, `daily_metrics_rollup`, `daily_anonymize_and_prepare`, `send_anonymized_to_segment`, `collect_dashboard_reports_data`)
- **`cleanup/`** — Cleanup functions (`cleanup_old_tasks`, `cleanup_activitystream`, `cleanup_metrics_data`)
- **`simple/`** — Simple tasks (`hello_world`)
- **`services/`** — Output formatting utilities
- **`v1/`** — REST API for task CRUD (`/api/v1/tasks/`)

### Task Groups and Feature Flags

`task_groups.py` defines five groups in `TASK_GROUPS`:

| Group | Feature Flag | Default | Purpose |
|-------|-------------|---------|---------|
| `SYSTEM_TASKS_GROUP` | none | always on | `cleanup_old_tasks` (daily 5 AM), `hello_world` (hourly), `cleanup_bi_collection_batches` (daily 4:15 AM), `cleanup_bi_stored_host_metrics` (daily 4:30 AM) |
| `METRICS_COLLECTION_GROUP` | `METRICS_COLLECTION` | enabled (opt-out) | Hourly/daily collection, rollup, `cleanup_metrics_data`. Disabling stops local scheduled collection; re-enable to backfill. |
| `ANONYMIZATION_GROUP` | `ANONYMIZED_DATA_COLLECTION` | enabled (opt-out) | `daily_anonymize_and_prepare` — anonymizes data for Red Hat. `send_anonymized_to_segment` exists in `TASK_FUNCTIONS` but is not scheduled via a task group. |
| `DASHBOARD_COLLECTION_GROUP` | `DASHBOARD_COLLECTION` | disabled (opt-in) | `collect_dashboard_reports_initial_data` (once on enable), `collect_dashboard_reports_data` (every 6 hours incremental), `cleanup_dashboard_reports_old_data` |
| `BI_BILLING_COLLECTION_GROUP` | `BI_CONNECTOR` | disabled (opt-in) | Runs metrics-utility billing collectors and stores output in DB for BI Layer 1 stored endpoints (`main_host_daily`, `job_host_summary`) |

Feature flag resolution order (first match wins): `Setting` DB row → `FEATURE_ENABLED[key]` in Django settings (incl. env overrides) → DAB `AAPFlag` boolean → function default.

```bash
# Toggle at runtime without restart
METRICS_SERVICE_FEATURE_ENABLED__METRICS_COLLECTION=false
METRICS_SERVICE_FEATURE_ENABLED__ANONYMIZED_DATA_COLLECTION=false
METRICS_SERVICE_FEATURE_ENABLED__DASHBOARD_COLLECTION=true
METRICS_SERVICE_FEATURE_ENABLED__BI_CONNECTOR=true
```

### BI Connector (`apps/bi_connector/`)

Multi-layer API for connecting BI tools (Tableau, Power BI, Grafana) to metrics data. All endpoints require **token authentication** (added via `bi_connector/settings.py`) and are subject to a per-user throttle of 30 req/hour (`BiConnectorThrottle`). Endpoints return 404 when the feature flag is off.

**Token setup for service accounts:**
```bash
python manage.py drf_create_token <username>
```

| Layer | Mount | Source | Feature Flag Required |
|-------|-------|--------|----------------------|
| Layer 1 — metrics DB | `/api/v1/bi/metrics/` | metrics-service DB (`DailyMetricsSummary`, `HourlyMetricsCollection`) | `BI_CONNECTOR` |
| Layer 1 — stored billing | `/api/v1/bi/stored/` | `StoredHostMetric`, `StoredJobHostSummary`, `StoredIndirectAudit`, `CollectionBatch` (populated by `BI_BILLING_COLLECTION_GROUP`) | `BI_CONNECTOR` |
| Layer 2 — live AWX DB | `/api/v1/bi/controller/` | Read-only queries against the `awx` DB connection | `BI_CONNECTOR` |
| Layer 3 — dashboard data | `/api/v1/bi/dashboard/` | `JobData`, `TemplateMetadata` models (local DB) | `BI_CONNECTOR` + `DASHBOARD_COLLECTION` |
| Admin | `/api/v1/bi/collector-settings/` | `CollectorSettings` config and `CollectionBatch` admin | `BI_CONNECTOR` |

Layer 2 endpoints (`/controller/jobs/`, `/hosts/`, `/credentials/`, `/events/`) are **asynchronous**: they return `202 Accepted` with a `task_id`. Poll `GET /api/v1/tasks/<task_id>/` until `status == "completed"`, then read `result_data.data`. Date windows are enforced (default 7 days; 3 days for events) via `METRICS_SERVICE_BI_CONNECTOR_MAX_DAYS_DEFAULT`.

**`bi_connector/collectors/`** contains the BI-specific collection logic:
- `collect_bi_controller_data.py` — invoked by Layer 2 async views; queries the AWX DB for live data
- `collect_bi_billing_data.py` — invoked by `BI_BILLING_COLLECTION_GROUP`; runs metrics-utility billing collectors and stores results in `StoredHostMetric` / `StoredJobHostSummary`
- `backfill_bi_collector.py` — manually triggered backfill for billing collector data
- `cleanup.py` — cleanup utilities for `CollectionBatch` and `StoredHostMetric` records

Feature flag guard mixins live in `apps/bi_connector/v1/mixins.py`:
- `BiConnectorEnabledMixin` — checks `BI_CONNECTOR` flag; also applies throttle
- `DashboardCollectionMixin` — additionally checks `DASHBOARD_COLLECTION` flag

Feature flags for BI connector are seeded from `apps/bi_connector/feature_flags.yaml` via a `post_migrate` signal on `dab_feature_flags`, so they survive DAB migration purge cycles without editing django-ansible-base's own YAML.

### Dashboard Reports (`apps/dashboard_reports/`)

Stores AWX job execution records locally for the automation-reports UI. Key models: `JobData`, `JobLabel`, `JobHostSummary`, `TemplateMetadata`, `SubscriptionCost`, `FilterSet`. Populated by `DASHBOARD_COLLECTION_GROUP` tasks. Exposes its own REST API at `/api/v1/dashboard_reports/`.

### API Structure

Each app exposes its own versioned API under a `v1/` subdirectory:
- `apps/tasks/v1/` — Task management endpoints (`/api/v1/tasks/`)
- `apps/core/v1/` — Core resource endpoints
- `apps/dynamic_settings/v1/` — Settings API (`/api/v1/feature_flags/`)
- `apps/bi_connector/v1/` — BI connector endpoints (`/api/v1/bi/`)
- `apps/dashboard_reports/` — Dashboard data endpoints (`/api/v1/dashboard_reports/`)

All viewsets use `BaseViewSet` / `UserManagementMixin` base classes. OpenAPI docs at `/api/docs/`.

### Dynamic Settings (`apps/dynamic_settings/`)

Provides a DB-backed `Setting` model for runtime configuration. Feature flags checked here at task execution time — no restart needed when toggling. Managed via:
- `python manage.py metrics_service init-default-settings` — seed defaults
- `python manage.py metrics_service remove-default-settings` — remove unmodified defaults
- `python manage.py dynamic_settings reload_config` — reload config from DB

## Key Development Patterns

### Adding a New Background Task

1. Implement the function in `apps/tasks/collectors/`, `apps/tasks/cleanup/`, or `apps/tasks/simple/`
2. Add to `TASK_FUNCTIONS` dict in `apps/tasks/tasks.py`
3. Add a task config entry to the appropriate `TaskGroup` in `apps/tasks/task_groups.py`
4. Run `python manage.py metrics_service init-system-tasks` to sync to DB

### Code Style

- Line length: 120 characters
- Ruff rules include security (bandit), complexity (mccabe/pylint), and style checks
- All new code requires type hints and docstrings on public methods
- Migrations excluded from linting

### Test Organization

- `tests/unit/` and `apps/core/tests/` — unit tests (both are testpaths in `pytest.ini_options`)
- `tests/integration/` — integration tests
- `apps/dynamic_settings/tests/` — app-local dynamic settings tests
- `apps/tasks/tests/` — app-local task system tests
- Markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
