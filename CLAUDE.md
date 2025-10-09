# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup and Database

```bash
# Install dependencies
pip install -e ".[dev]"

# Run database migrations
python manage.py migrate

# Initialize ServiceID for ansible-base (required)
python manage.py metric_service init-service-id

# Initialize system tasks (cleanup, metrics collection)
python manage.py metric_service init-system-tasks

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver

# OR run complete metrics service (Django + dispatcher + scheduler)
python manage.py metric_service run
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
```

### Background Tasks (Dispatcherd)

```bash
# Dispatcherd is always enabled in this service

# Run complete service (includes dispatcher and scheduler)
python manage.py metric_service run

# OR run individual components (for development/debugging)
python manage.py metric_service run --workers 2 --log-level DEBUG

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
python manage.py metric_service run

# Or start only Django development server
python manage.py runserver

# Access the dashboard at http://localhost:8000/dashboard/
```

### Metrics Service Management

The `metric_service` command provides centralized management with a unified entry point:

```bash
# Run complete service (Django server + task dispatcher + scheduler)
python manage.py metric_service run

# Initialize ServiceID for ansible-base
python manage.py metric_service init-service-id

# Initialize/update system tasks
python manage.py metric_service init-system-tasks

# List current system tasks
python manage.py metric_service init-system-tasks --list

# Dry run (see what would be done)
python manage.py metric_service init-system-tasks --dry-run

# Force update all system tasks
python manage.py metric_service init-system-tasks --force

# Task management
python manage.py metric_service tasks create --name "My Task" --function "cleanup_old_data"
python manage.py metric_service tasks list
python manage.py metric_service tasks show 1
python manage.py metric_service tasks cancel 1
python manage.py metric_service tasks retry 1

# Cron scheduler management
python manage.py metric_service cron start
python manage.py metric_service cron stop
python manage.py metric_service cron status
python manage.py metric_service cron list

# Custom service configuration
python manage.py metric_service run --host 0.0.0.0 --port 8080 --workers 8
```

### Unified Command Structure

The `metric_service` command consolidates all service management operations into a single entry point:

#### Main Commands:

- **`run`** - Start the complete metrics service (Django + dispatcher + scheduler)
- **`init-service-id`** - Initialize ServiceID for ansible-base resource registry
- **`init-system-tasks`** - Initialize system-defined tasks (cleanup, metrics collection)
- **`tasks`** - Manage database tasks (create, list, show, cancel, retry)
- **`cron`** - Manage cron-based task scheduler (start, stop, status, list, add, remove)

#### Command Examples:

```bash
# Get help for any command
python manage.py metric_service --help
python manage.py metric_service tasks --help
python manage.py metric_service cron --help

# Run service with custom configuration
python manage.py metric_service run --host 0.0.0.0 --port 8080 --workers 4 --log-level DEBUG

# Task management
python manage.py metric_service tasks create --name "Cleanup" --function "cleanup_old_data" --cron "0 2 * * *"
python manage.py metric_service tasks list --status pending --limit 10
python manage.py metric_service tasks show 1
python manage.py metric_service tasks cancel 1
python manage.py metric_service tasks retry 1

# System initialization
python manage.py metric_service init-service-id
python manage.py metric_service init-system-tasks --list
python manage.py metric_service init-system-tasks --dry-run
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

- **Task functions** - `cleanup_old_data`, `send_notification_email`, `process_user_data`, `execute_db_task`
- **Database-driven tasks** - Tasks defined in DB with dependency management
- **Dispatcherd integration** - Always enabled, multi-worker task processing with health monitoring
- **Scheduling** - Cron-like recurring tasks and dependency chains
- **Type safety** - Full type hints on all task functions and utilities

## Django-Ansible-Base Integration

### Important: ServiceID Initialization

Always run `python manage.py init_service_id` after migrations. This creates the required ServiceID object for DAB's resource registry system.

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

The system includes these built-in task functions:

- **`cleanup_old_data`** - Clean up old data from the system
- **`send_notification_email`** - Send notification emails to users
- **`process_user_data`** - Process user data in the background
- **`execute_db_task`** - Execute database-defined tasks with full lifecycle management

## Development Notes

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
2. Add to `TASK_FUNCTIONS` dictionary
3. Create Task model instance or use programmatic scheduling
4. Test with dispatcherd: `python manage.py run_dispatcherd`

### API Development

1. Use base classes (`BaseViewSet`, `UserManagementMixin`) to reduce duplication
2. Follow existing filtering and serialization patterns
3. Add OpenAPI documentation with `@extend_schema`
4. Test API endpoints thoroughly
