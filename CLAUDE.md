# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup

```bash
# Install dependencies (project uses uv)
uv sync --dev

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

# Shared compose environment (requires ../metrics-utility checkout)
# Base containers only (postgres + minio)
make compose
# Then in another terminal — run migrations, start dev server
tools/dev.sh --init

# Full service stack (web + dispatcher + scheduler)
make compose-service
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

# Or directly
.venv/bin/ruff format . && .venv/bin/ruff check . --fix
```

### Running Django Commands with Imports

```bash
# For one-off commands that need Django context
python manage.py shell -c "from apps.tasks.tasks import TASK_FUNCTIONS; print(list(TASK_FUNCTIONS))"

# Never use plain python -c for Django imports — it fails without Django setup
```

## Architecture Overview

Full architecture docs with Mermaid diagrams: [`docs/README.md`](docs/README.md).

| Topic | Doc |
|-------|-----|
| Core, DAB, RBAC | [`docs/core-rbac.md`](docs/core-rbac.md) |
| Task system | [`docs/task-system.md`](docs/task-system.md) |
| Task states / recovery | [`docs/task-state-machine.md`](docs/task-state-machine.md) |
| APScheduler | [`docs/apscheduler.md`](docs/apscheduler.md) |
| Collectors | [`docs/collectors.md`](docs/collectors.md) |
| Dashboard sync | [`docs/dashboard-sync.md`](docs/dashboard-sync.md) |

### App Structure

```
apps/
  core/           # Custom User/Organization/Team models, DAB integration, RBAC
  tasks/          # Background task system (models, scheduling, execution)
  dynamic_settings/ # Runtime DB-backed feature enablement settings (Setting model)
  dashboard_reports/ # Job data for automation-reports API
  settings/       # Dynaconf settings layering (see below)
metrics_service/
  settings/       # Split Django settings (development, production, test)
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

### Task System (`apps/tasks/`)

See [`docs/task-system.md`](docs/task-system.md). Key files: `task_groups.py` (source of truth for system tasks), `cron_scheduler.py`, `dispatcherd_config.py`, `collectors/`, `v1/`.

`task_groups.py` defines five task groups; **four** are gated by feature
enablement settings (`METRICS_COLLECTION`, `ANONYMIZED_DATA_COLLECTION`,
`DASHBOARD_COLLECTION`, `INDIRECT_NODE_COLLECTION` — distinct from platform
feature flags / DAB `AAPFlag`). `SYSTEM_TASKS_GROUP` is always enabled.
Settings are checked at task execution time via DB/API without restart; env var
changes require restart.

### API Structure

Each app exposes its own versioned API under a `v1/` subdirectory:
- `apps/tasks/v1/` — Task management endpoints (`/api/v1/tasks/`)
- `apps/core/v1/` — Core resource endpoints
- `apps/dynamic_settings/v1/` — Settings API

All viewsets use `BaseViewSet` / `UserManagementMixin` base classes. OpenAPI docs at `/api/docs/`.

### Dynamic Settings (`apps/dynamic_settings/`)

Provides a DB-backed `Setting` model for runtime configuration. Feature
enablement settings for task groups are checked at task execution time — no
restart needed when toggling via DB/API. Managed via:
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

- `tests/unit/` and `apps/core/tests/` — unit tests (both are testpaths)
- `tests/integration/` — integration tests
- `apps/dynamic_settings/tests/` — app-local tests
- Markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
