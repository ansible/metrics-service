# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup and Database

```bash
# Install dependencies (project uses uv for package management)
pip install -e ".[dev]"
# OR using uv (faster, project default)
uv sync --dev

# Run database migrations
python manage.py migrate
# OR with virtual environment
.venv/bin/python manage.py migrate

# Initialize ServiceID for ansible-base (required)
python manage.py metrics_service init-service-id

# Initialize system tasks (cleanup, metrics collection)
python manage.py metrics_service init-system-tasks

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver

# OR run complete metrics service (Django + dispatcher + scheduler)
python manage.py metrics_service run
```

### Testing

```bash
# Run all tests (automatically uses .venv if available)
pytest
# OR explicitly with virtual environment
.venv/bin/python -m pytest

# Run with coverage (configured for 80% minimum)
pytest --cov=metrics_service --cov=apps
.venv/bin/python -m pytest --cov=metrics_service --cov=apps

# Run unit tests only
pytest -m unit

# Run integration tests only
pytest -m integration

# Run specific test file
pytest tests/unit/test_models.py
.venv/bin/python -m pytest tests/unit/test_models.py

# Run tests with verbose output and short traceback
.venv/bin/python -m pytest -v --tb=short

# Run tests with coverage report
.venv/bin/python -m pytest --cov=apps --cov=metrics_service --cov-report=term-missing -v
```

### Code Quality

```bash
# Format code (120 character line length)
black .

# Lint code (extensive rule set including security, complexity)
ruff check .
.venv/bin/ruff check .

# Fix linting issues automatically
ruff check . --fix
.venv/bin/ruff check . --fix

# Fix unsafe issues (use with caution)
.venv/bin/ruff check . --unsafe-fixes --fix

# Type checking (configured for gradual adoption)
mypy .

# Sort imports (black-compatible profile)
isort .

# Run all quality checks together
black . && ruff check . --fix && mypy . && isort .
```

### Pre-commit Hooks and Requirements Management

```bash
# Install pre-commit hooks (automatically syncs requirements)
pre-commit install

# Run hooks on all files
pre-commit run --all-files

# Manually sync requirements files from pyproject.toml/uv.lock
./sync-requirements.sh
# OR using make
make sync-requirements

# Check if requirements are in sync
make requirements-check
```

### Django Shell and Debugging

```bash
# Start Django shell for interactive testing
python manage.py shell
.venv/bin/python manage.py shell

# Start shell with specific settings
.venv/bin/python manage.py shell --settings=metrics_service.settings.development

# Create tasks programmatically in shell
python manage.py shell
>>> from apps.tasks.models import Task
>>> task = Task.objects.create(name="Test Task", function_name="cleanup_old_data")

# Check dispatcherd status and logs
docker-compose logs -f metrics-dispatcher
```

### Background Tasks (Dispatcherd)

```bash
# Dispatcherd is always enabled in this service

# Run complete service (includes dispatcher and scheduler)
python manage.py metrics_service run

# OR run individual components (for development/debugging)
python manage.py metrics_service run --workers 2

# Create sample tasks (using Django shell or admin interface)
python manage.py shell
```

### Docker

```bash
# Start full stack with PostgreSQL and task dispatcher
docker-compose up

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f metrics-service
docker-compose logs -f metrics-dispatcher
```

### Quick Start with Task Dashboard

```bash
# Start with Docker Compose (includes web server + task dispatcher)
docker-compose up

# Or manually start complete metrics service (Django + dispatcher + scheduler)
python manage.py metrics_service run

# Or start only Django development server
python manage.py runserver

# Access the dashboard at http://localhost:8000/dashboard/
```

### Metrics Service Management

The `metrics_service` command provides centralized management with a unified entry point:

```bash
# Run complete service (Django server + task dispatcher + scheduler)
python manage.py metrics_service run

# Initialize ServiceID for ansible-base
python manage.py metrics_service init-service-id

# Initialize/update system tasks
python manage.py metrics_service init-system-tasks

# List current system tasks
python manage.py metrics_service init-system-tasks --list

# Dry run (see what would be done)
python manage.py metrics_service init-system-tasks --dry-run

# Force update all system tasks
python manage.py metrics_service init-system-tasks --force

# Task management
python manage.py metrics_service tasks create --name "My Task" --function "cleanup_old_data"
python manage.py metrics_service tasks list
python manage.py metrics_service tasks show 1
python manage.py metrics_service tasks cancel 1
python manage.py metrics_service tasks retry 1

# Custom service configuration
python manage.py metrics_service run --host 0.0.0.0 --port 8080 --workers 8
```

### Unified Command Structure

The `metrics_service` command consolidates all service management operations into a single entry point:

#### Main Commands:

- **`run`** - Start the complete metrics service (Django + dispatcher + scheduler)
- **`init-service-id`** - Initialize ServiceID for ansible-base resource registry
- **`init-system-tasks`** - Initialize system-defined tasks (cleanup, metrics collection)
- **`tasks`** - Manage database tasks (create, list, show, cancel, retry)

#### Command Examples:

```bash
# Get help for any command
python manage.py metrics_service --help
python manage.py metrics_service tasks --help

# Run service with custom configuration
python manage.py metrics_service run --host 0.0.0.0 --port 8080 --workers 4

# Task management
python manage.py metrics_service tasks create --name "Cleanup" --function "cleanup_old_data" --cron "0 2 * * *"
python manage.py metrics_service tasks list --status pending --limit 10
python manage.py metrics_service tasks show 1
python manage.py metrics_service tasks cancel 1
python manage.py metrics_service tasks retry 1

# System initialization
python manage.py metrics_service init-service-id
python manage.py metrics_service init-system-tasks --list
python manage.py metrics_service init-system-tasks --dry-run
```

## Architecture Overview

### Project Structure

This is a Django-based service following Ansible Automation Platform (AAP) standards with these key components:

- **`apps/core/`** - Core business logic, models, and background tasks
- **`apps/api/v1/`** - Versioned REST API endpoints with reduced code duplication
- **`apps/health/`** - Health check endpoints for Kubernetes deployment
- **`apps/dashboard/`** - Web-based task management dashboard with real-time monitoring
- **`metrics_service/settings/`** - Split Django settings (development, production, test)
- **`tests/`** - Comprehensive test suite (unit, integration, functional)

### Key Models (`apps/core/models.py`)

- **User** - Custom user model with Django-Ansible-Base integration
- **Organization** - Organizations with user/admin management
- **Team** - Teams within organizations with hierarchical support

- **Task/TaskExecution/TaskChain** - Comprehensive background task system with dependencies and scheduling (see `apps/tasks/models.py`)

### API Architecture (`apps/api/v1/`)

- **Base classes** - `BaseViewSet` and `UserManagementMixin` reduce code duplication
- **Versioned endpoints** - URL-based versioning (`/api/v1/`)
- **Comprehensive filtering** - Field-based filtering, search, pagination, and sorting
- **Task Management APIs** - Full CRUD operations for tasks with real-time status monitoring
- **OpenAPI documentation** - Available at `/api/docs/`

### Task Dashboard (`apps/dashboard/`)

The web-based dashboard provides a centralized interface for task management:

- **Real-time Monitoring** - Live updates of running and pending tasks every 5 seconds
- **Task Visualization** - Separate sections for running tasks, pending tasks, and complete history
- **Task Creation** - Interactive form with function selection, parameter input, and scheduling
- **Task Controls** - Retry failed tasks, cancel pending/running tasks
- **Statistics Dashboard** - Live counters for task statuses (running, pending, completed, failed)
- **Responsive Design** - Mobile-friendly interface using Tailwind CSS

#### Dashboard Features

- **URL**: `/dashboard/` (requires authentication)
- **Auto-refresh**: Updates every 5 seconds without page reload
- **Task Actions**: Create, retry, cancel tasks directly from the interface
- **Function Discovery**: Automatically loads available task functions from the system
- **JSON Parameter Input**: Support for complex task parameters via JSON input
- **DateTime Scheduling**: Built-in date/time picker for scheduling future tasks

### Background Task System (`apps/tasks/` and `apps/core/tasks.py`)

The service includes a comprehensive background task system with:

- **Task functions** - `cleanup_old_data`, `cleanup_old_tasks`, `execute_db_task`, `hello_world`
- **Database-driven tasks** - Tasks defined in DB with dependency management
- **Dispatcherd integration** - Always enabled, multi-worker task processing with health monitoring
- **Scheduling** - Cron-like recurring tasks and dependency chains
- **Type safety** - Full type hints on all task functions and utilities

## Django-Ansible-Base Integration

### Important: ServiceID Initialization

Always run `python manage.py metrics_service init-service-id` after migrations. This creates the required ServiceID object for DAB's resource registry system.

### DAB Features Available

- **RBAC** - Role-based access control with permission registry
- **Authentication** - Multiple backends (local, LDAP, SAML, OAuth)
- **Resource Registry** - Cross-service resource synchronization
- **Activity Stream** - Audit logging for model changes
- **Feature Enabled** - Runtime feature control via FEATURE_ENABLED settings

### Settings Configuration

- **Environment variables** - Use `METRICS_SERVICE_` prefix for configuration
- **Dynaconf integration** - Complex configuration via `config/settings.yaml`
- **Split settings** - Separate files for development, production, and testing

## Testing Strategy

### Test Organization

- **`tests/unit/`** - Unit tests for individual components
- **`tests/integration/`** - Integration tests for component interactions
- **`tests/conftest.py`** - Shared test fixtures and configuration

### Test Markers

Use pytest markers for test categorization:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Slow-running tests

### Coverage Requirements

- Minimum 80% coverage enforced via pytest configuration
- Coverage reports generated in HTML and XML formats

## Task Management API Endpoints

### Core Task Endpoints

```bash
# Get all tasks with filtering and pagination
GET /api/v1/tasks/
GET /api/v1/tasks/?status=running
GET /api/v1/tasks/?status=pending

# Create a new task
POST /api/v1/tasks/
{
  "name": "My Task",
  "function_name": "cleanup_old_data",
  "task_data": {"days_old": 30},
  "scheduled_time": "2024-09-04T15:30:00Z"  // Optional
}

# Get running tasks only
GET /api/v1/tasks/running/

# Get pending tasks only
GET /api/v1/tasks/pending/

# Retry a failed task
POST /api/v1/tasks/{id}/retry/

# Cancel a pending or running task
POST /api/v1/tasks/{id}/cancel/

# Get available task functions
GET /api/v1/tasks/available_functions/
```

### Available Task Functions

The system includes these built-in task functions organized by feature groups:

**System Tasks** (always enabled):

- **`cleanup_old_data`** - Clean up old data from the system
- **`cleanup_old_tasks`** - Clean up completed/failed tasks
- **`execute_db_task`** - Execute database-defined tasks with full lifecycle management

**Anonymized Data Collection** (controlled by `ANONYMIZED_DATA_COLLECTION`):

- **`collect_anonymous_metrics`** - Collect anonymous system metrics
- **`collect_config_metrics`** - Collect configuration information

**Metrics Collection** (controlled by `METRICS_COLLECTION_ENABLED`):

- **`collect_host_metrics`** - Collect host performance data
- **`collect_job_host_summary`** - Collect job execution statistics
- **`collect_all_metrics`** - Run multiple collectors in sequence

## Development Notes

### Code Style Standards

- **Line length** - 120 characters (configured in pyproject.toml)
- **Import organization** - Sorted with isort, grouped by type
- **Type hints** - Required for all new code, comprehensive type coverage
- **Docstrings** - Required for all public methods and classes
- **Code duplication** - Extensive use of mixins and utility functions to reduce duplication

### Custom User Model

The project uses a custom User model (`core.User`) that extends AbstractDABUser with enhanced functionality including access control and password handling.

### Feature Enabled Configuration

Dispatcherd is permanently enabled. Other features can be controlled via the `FEATURE_ENABLED` setting:

```python
FEATURE_ENABLED = {
    "DISPATCHERD_ENABLED": True,  # Always True, cannot be disabled
    "ANONYMIZED_DATA_COLLECTION": True,  # Default enabled
    "METRICS_COLLECTION_ENABLED": False,  # Default disabled (customer opt-in)
}
```

**Environment Variable Mapping:**

- `METRICS_SERVICE_ANONYMIZED_DATA=true/false` → Controls anonymized data collection tasks
- `METRICS_SERVICE_METRICS_COLLECTION=true/false` → Controls metrics collection tasks

**Task Groups Controlled by Feature Enabled:**

- **System Tasks** - Always enabled (cleanup, maintenance)
- **Anonymized Data Collection** - Controlled by `ANONYMIZED_DATA_COLLECTION` (default: enabled)
- **Metrics Collection** - Controlled by `METRICS_COLLECTION_ENABLED` (default: disabled)

**Automatic Database Initialization:**

Feature flags are automatically created in the `dynamic_settings_setting` table on application startup:
- If a setting doesn't exist, it's created with the default value from `FEATURE_ENABLED`
- If a setting already exists, it's not modified (preserves user changes)
- Settings can be queried/modified via SQL, Django shell, or API

**Runtime Feature Flag Checking:**

Hourly collection tasks automatically check feature flags before execution:
- Tasks skip execution when their feature flag is disabled
- No scheduler restart needed - changes take effect immediately
- Logged when tasks are skipped for visibility

### Logging Configuration

**Setting Log Level:**

The log level is controlled by the `METRICS_SERVICE_LOG_LEVEL` environment variable:

```bash
# For development - see everything
export METRICS_SERVICE_LOG_LEVEL=DEBUG

# For production - standard informational logging (default)
export METRICS_SERVICE_LOG_LEVEL=INFO

# For troubleshooting - warnings and errors only
export METRICS_SERVICE_LOG_LEVEL=WARNING

# For critical issues only
export METRICS_SERVICE_LOG_LEVEL=ERROR
```

**Quick Debug Mode:**

```bash
# Run server with debug logging
METRICS_SERVICE_LOG_LEVEL=DEBUG python manage.py runserver

# Run tests with debug logging
METRICS_SERVICE_LOG_LEVEL=DEBUG pytest
```

**How It Works:**

- \*\* Django logging- we use built in django logging in conjunction with Dynaconf to help us handle out logging level. The logging level is established at app start up and defaults to "INFO". If you need to change the log level, you will have to restart the app after updating the environment variable METRICS_SERVICE_LOG_LEVEL.

### Database Configuration

- **Development** - PostgreSQL for consistent development/production setup
- **Production** - PostgreSQL with environment variable configuration
- **Docker** - Includes PostgreSQL service

### Code Architecture Patterns

- **Utility functions** - Common functionality in `apps/core/utils.py`
- **Mixins** - Reusable model and serializer functionality
- **Base classes** - `BaseViewSet`, `BaseModelSerializer` for consistent API patterns
- **Type safety** - All methods have type hints and return type annotations

## Common Workflows

### Adding New Models

1. Create model in `apps/core/models.py` following existing patterns
2. Create migrations: `python manage.py makemigrations`
3. Apply migrations: `python manage.py migrate`
4. Add to API if needed in `apps/api/v1/`

### Adding Background Tasks

1. Define task function in `apps/core/tasks.py`
2. Add to `TASK_FUNCTIONS` dictionary
3. Create Task model instance or use programmatic scheduling
4. Test with dispatcherd: `python manage.py metrics_service run`

### API Development

1. Use base classes (`BaseViewSet`, `UserManagementMixin`) to reduce duplication
2. Follow existing filtering and serialization patterns
3. Add OpenAPI documentation with `@extend_schema`
4. Test API endpoints thoroughly

## Key Development Patterns

### Package Management and Environment

- **UV Package Manager**: This project uses `uv` for fast dependency management (`uv sync --dev`)
- **Virtual Environment**: Commands should use `.venv/bin/python` for consistency
- **Requirements Sync**: Requirements files are automatically synced via pre-commit hooks when `pyproject.toml` or `uv.lock` changes

### Essential Initialization Steps

- **ServiceID**: Always run `python manage.py metrics_service init-service-id` after migrations (required for DAB)
- **System Tasks**: Run `python manage.py metrics_service init-system-tasks` to initialize background tasks

### Testing and Quality Patterns

- **Test Coverage**: 80% minimum coverage enforced, use `.venv/bin/python -m pytest --cov=apps --cov=metrics_service --cov-report=term-missing -v`
- **Code Quality**: 120-char lines, comprehensive ruff rules including security checks
- **Test Markers**: Use `@pytest.mark.unit` and `@pytest.mark.integration` for categorization

### Task System Architecture

- **Dispatcherd**: Always enabled and integrates with the unified `metrics_service` command
- **Task Routing**: Automatic task routing - immediate tasks go to dispatcherd, scheduled tasks use APScheduler
- **Management Command**: Use `python manage.py metrics_service run` for complete service (Django + dispatcher + scheduler)
- **Task Groups**: Tasks organized into feature-controlled groups (System, Anonymized Data, Metrics Collection)

### Feature Enabled System

- **Configuration**: Use `FEATURE_ENABLED` dict in Django settings or environment variables with `METRICS_SERVICE_` prefix
- **Task Groups**: System tasks always enabled, anonymized data default enabled, metrics collection default disabled
- **Environment Variables**: `METRICS_SERVICE_ANONYMIZED_DATA` and `METRICS_SERVICE_METRICS_COLLECTION` control task groups
- **Runtime Control**: Features can be toggled via database settings or environment variables

### Code Organization

- **Apps Structure**: `core/` (models, business logic), `api/v1/` (REST endpoints), `tasks/` (background tasks), `dashboard/` (web UI)
- **Mixins**: Extensive use of mixins (`AccessControlMixin`, `StatusTrackingMixin`) to reduce code duplication
- **Type Safety**: All new code requires type hints and return type annotations
