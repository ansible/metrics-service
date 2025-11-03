# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup and Database

```bash
# Modern setup using uv (recommended)
uv sync --extra dev

# OR traditional pip setup
pip install -e ".[dev]"

# Run database migrations
python manage.py migrate

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
# Run all tests (automatically uses .venv)
pytest

# Run with coverage
pytest --cov=metrics_service --cov=apps

# Run unit tests only
pytest -m unit

# Run integration tests only
pytest -m integration

# Run specific test file
pytest tests/unit/test_models.py

# Run tests for specific app
pytest tests/unit/tasks/
pytest tests/unit/core/
```

### Code Quality

```bash
# Format code
black .

# Lint code
ruff check .

# Fix linting issues
ruff check . --fix

# Type checking
mypy .

# Sort imports
isort .

# Run pre-commit hooks
pre-commit run --all-files
```

### Requirements Management

```bash
# Sync requirements files from uv.lock (when pyproject.toml changes)
make sync-requirements

# OR run script directly
./sync-requirements.sh

# Check if requirements are in sync
make requirements-check

# Modern dependency management with uv
uv add <package>              # Add runtime dependency
uv add --dev <package>        # Add dev dependency  
uv remove <package>           # Remove dependency
uv sync                       # Install dependencies
uv sync --extra dev           # Install with dev dependencies
```

### Background Tasks (Dispatcherd)

```bash
# Dispatcherd is always enabled in this service

# Run complete service (includes dispatcher and scheduler)
python manage.py metrics_service run

# OR run individual components (for development/debugging)
python manage.py metrics_service run --workers 2 --log-level DEBUG

# Create sample tasks (using Django shell or admin interface)
python manage.py shell
```

### Docker

```bash
# Start full stack with PostgreSQL and task dispatcher
docker compose up

# Start in background
docker compose up -d

# View logs
docker compose logs -f metrics-service
docker compose logs -f postgres

# Using make command (if available)
make docker-compose
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

# Cron scheduler management
python manage.py metrics_service cron start
python manage.py metrics_service cron stop
python manage.py metrics_service cron status
python manage.py metrics_service cron list

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
- **`cron`** - Manage cron-based task scheduler (start, stop, status, list, add, remove)

#### Command Examples:

```bash
# Get help for any command
python manage.py metrics_service --help
python manage.py metrics_service tasks --help
python manage.py metrics_service cron --help

# Run service with custom configuration
python manage.py metrics_service run --host 0.0.0.0 --port 8080 --workers 4 --log-level DEBUG

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
- **OpenAPI documentation** - Available at `/api/docs/`

### Background Task System (`apps/tasks/` and `apps/core/tasks.py`)

The service includes a comprehensive background task system with:

- **Task functions** - `cleanup_old_data`, `send_notification_email`, `process_user_data`, `execute_db_task`
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
- **Feature Flags** - Runtime feature control

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


## Development Notes

### Virtual Environment Usage

This project uses a `.venv` virtual environment in the project root. Commands automatically use this environment:

```bash
# All Python commands automatically use .venv when present
python manage.py migrate
pytest
ruff check .

# Virtual environment is automatically activated in scripts
# No need to manually activate unless using interactive shell
```

### Code Style Standards

- **Line length** - 120 characters (configured in pyproject.toml)
- **Import organization** - Sorted with isort, grouped by type
- **Type hints** - Required for all new code, comprehensive type coverage
- **Docstrings** - Required for all public methods and classes
- **Code duplication** - Extensive use of mixins and utility functions to reduce duplication

### Custom User Model

The project uses a custom User model (`core.User`) that extends AbstractDABUser with enhanced functionality including access control and password handling.

### Feature Flags

Dispatcherd is permanently enabled. Other feature flags can be controlled via:

```python
FEATURE_FLAGS = {
    "DISPATCHERD_ENABLED": True,  # Always True
}
```

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
2. Add to `TASK_FUNCTIONS` dictionary in `apps/tasks/tasks.py`
3. Create Task model instance or use programmatic scheduling
4. Test with dispatcherd: `python manage.py run_dispatcherd`
5. OR test with unified command: `python manage.py metrics_service run`

### API Development

1. Use base classes (`BaseViewSet`, `UserManagementMixin`) to reduce duplication
2. Follow existing filtering and serialization patterns
3. Add OpenAPI documentation with `@extend_schema`
4. Test API endpoints thoroughly
