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
python manage.py init_service_id

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
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

# Run task dispatcher
python manage.py run_dispatcher

# Run task scheduler (polls for ready tasks)
python manage.py run_task_scheduler

# Create sample tasks
python examples/create_sample_tasks.py
```

### Docker
```bash
# Start full stack with PostgreSQL and Redis
docker-compose up

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f metrics-service
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
- **Animal** - Example model demonstrating AAP patterns (replace with actual business logic)
- **Task/TaskExecution/TaskChain** - Comprehensive background task system with dependencies and scheduling

### API Architecture (`apps/api/v1/`)
- **Base classes** - `BaseViewSet` and `UserManagementMixin` reduce code duplication
- **Versioned endpoints** - URL-based versioning (`/api/v1/`)
- **Comprehensive filtering** - Field-based filtering, search, pagination, and sorting
- **OpenAPI documentation** - Available at `/api/docs/`

### Background Task System (`apps/core/tasks.py`)
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
- **Development** - SQLite by default for immediate setup
- **Production** - PostgreSQL with environment variable configuration
- **Docker** - Includes PostgreSQL and Redis services

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
4. Test with dispatcherd: `python manage.py run_dispatcher`

### API Development
1. Use base classes (`BaseViewSet`, `UserManagementMixin`) to reduce duplication
2. Follow existing filtering and serialization patterns
3. Add OpenAPI documentation with `@extend_schema`
4. Test API endpoints thoroughly