# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup

```bash
# Install dependencies (project uses uv)
uv sync --dev

# Copy and edit local settings (git-ignored)
cp settings.local.py.example settings.local.py

# Run database migrations
.venv/bin/python manage.py migrate

# Initialize required objects (run after every migration)
python manage.py metrics_service init-service-id       # Required for DAB resource registry
python manage.py metrics_service init-default-settings  # Initialize feature flag DB table
python manage.py metrics_service init-system-tasks      # Register scheduled background tasks

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

# Install pre-commit hooks
pre-commit install
pre-commit run --all-files
```

### Running Django Commands with Imports

```bash
# For one-off commands that need Django context
python manage.py shell -c "from apps.tasks.tasks import TASK_FUNCTIONS; print(list(TASK_FUNCTIONS))"

# Never use plain python -c for Django imports — it fails without Django setup

# Debug a single task manually
uv run ./scripts/run_task.py hello_world

# Inspect settings load order and variable resolution
uv run dynaconf inspect -m debug -f yaml        # full loading history
uv run dynaconf inspect -k VARIABLE_NAME        # single variable
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
  dashboard_reports/ # AWX job data ingestion and reporting models for automation-reports integration
metrics_service/
  settings/         # Split Django settings (development, production, test)
```

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

### URL Loading

`metrics_service/urls.py` is framework-managed. Each app in `project_applications` (defined in `apps/settings/defaults.py`) has its `urls.py` auto-discovered and appended. Cross-app URL overrides go in `apps/urls.py`. URL loading order follows `project_applications` order — first match wins, so order matters when patterns overlap.

### Task System (`apps/tasks/`)

The task system has several layers:

- **`models.py`** — `Task`, `TaskExecution`, `TaskChain` DB models
- **`tasks.py`** — `TASK_FUNCTIONS` registry mapping function names to callables; also defines queue routing per function
- **`task_groups.py`** — `TASK_GROUPS` config: defines what tasks run, their cron schedules, args, and which feature flag controls them. This is the source of truth for scheduled tasks — edit here, then run `init-system-tasks` to sync to DB.
- **`tasks_system.py`** — `execute_db_task` is the sole dispatcherd entry point; all DB tasks route through it. Also contains `submit_task_to_dispatcher` and `create_system_tasks`.
- **`cron_scheduler.py`** — APScheduler integration for recurring tasks
- **`dispatcherd_config.py`** — Dispatcherd worker configuration
- **`collectors/`** — Metrics collection functions (`collect_hourly_metrics`, `collect_snapshot_metrics`, `collect_daily_metrics`, `daily_metrics_rollup`, `daily_anonymize_and_prepare`, `send_anonymized_to_segment`)
- **`cleanup/`** — Cleanup functions (`cleanup_old_tasks`, `cleanup_activitystream`, `cleanup_metrics_data`)
- **`simple/`** — Simple tasks (`hello_world`)
- **`services/`** — Output formatting utilities
- **`v1/`** — REST API for task CRUD (`/api/v1/tasks/`)

### Task Groups and Feature Flags

`task_groups.py` defines four groups:

| Group | Feature Flag | Default | Purpose |
|-------|-------------|---------|---------|
| `SYSTEM_TASKS_GROUP` | None (always on) | — | `cleanup_old_tasks` (daily 5 AM), `hello_world` (hourly) |
| `METRICS_COLLECTION_GROUP` | `METRICS_COLLECTION` | true | Hourly/daily collectors, `daily_metrics_rollup`, `collect_daily_metrics`, `cleanup_metrics_data` |
| `ANONYMIZATION_GROUP` | `ANONYMIZED_DATA_COLLECTION` | true (customer opt-out) | `daily_anonymize_and_prepare`, `send_anonymized_to_segment` — data transmitted to Red Hat |
| `DASHBOARD_COLLECTION_GROUP` | `DASHBOARD_COLLECTION` | false (customer opt-in) | `collect_dashboard_reports_data`, `collect_dashboard_reports_initial_data`, `cleanup_dashboard_reports_old_data` |

Feature flags are stored in the `dynamic_settings_setting` DB table (managed by `apps/dynamic_settings/`). They fall back to `FEATURE_ENABLED` in Django settings if not in DB.

```bash
# Toggle at runtime without restart
METRICS_SERVICE_FEATURE_ENABLED__ANONYMIZED_DATA_COLLECTION=false
METRICS_SERVICE_FEATURE_ENABLED__METRICS_COLLECTION=false
METRICS_SERVICE_FEATURE_ENABLED__DASHBOARD_COLLECTION=true
```

### Dashboard Reports (`apps/dashboard_reports/`)

Stores AWX job execution data for the automation-reports integration. Key models: `JobData`, `JobLabel`, `JobHostSummary`, `SubscriptionCost`, `FilterSet`, `TemplateMetadata`. Data is ingested via the `DASHBOARD_COLLECTION_GROUP` tasks and served through viewsets under `apps/dashboard_reports/viewsets/`.

### API Structure

Each app exposes its own versioned API under a `v1/` subdirectory:
- `apps/tasks/v1/` — Task management endpoints (`/api/v1/tasks/`)
- `apps/core/v1/` — Core resource endpoints
- `apps/dynamic_settings/v1/` — Settings API
- `apps/dashboard_reports/` — Dashboard reporting endpoints

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

### Adding a New App

1. Create the app under `apps/`
2. Add it to `project_applications` in `apps/settings/defaults.py` — this controls both settings and URL loading order

### Code Style

- Line length: 120 characters
- Ruff rules include security (bandit), complexity (mccabe/pylint), and style checks
- All new code requires type hints and docstrings on public methods
- Migrations excluded from linting

### Test Organization

- `tests/unit/` and `apps/core/tests/` — unit tests (both are testpaths)
- `tests/integration/` — integration tests
- `apps/dynamic_settings/tests/` — app-local tests
- Markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
