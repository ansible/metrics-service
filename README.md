# AAP Service Template

A modern Django service template following Ansible Automation Platform (AAP) standards and best practices.

## 🚀 Using This Template

### 1. Create Your Service

Click **"Use this template"** to create a new repository from this template.

### 2. Customize Your Service

Replace the following template variables throughout your codebase:

| Find                               | Replace With                   | Example                      |
| ---------------------------------- | ------------------------------ | ---------------------------- |
| `metrics-service`                  | Your service name (kebab-case) | `inventory-service`          |
| `metrics_service`                  | Your service name (snake_case) | `inventory_service`          |
| `Metrics Service`                  | Your service display name      | `Inventory Service`          |
| `AAP Emerging Services`            | Your team name                 | `Inventory Team`             |
| `aap-emerging-services@redhat.com` | Your team email                | `inventory-team@company.com` |

### 3. Setup Options

#### Option A: Full Development Setup (Recommended for AAP development)

```bash
# Automated setup with all AAP features
chmod +x scripts/dev-setup.sh
./scripts/dev-setup.sh
```

#### Option B: Basic Django Setup (For immediate use)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install basic dependencies
pip install Django>=4.2 djangorestframework>=3.15 drf-spectacular>=0.27 django-cors-headers>=4.0

# Set up minimal configuration
cp config/settings.yaml.example config/settings.yaml
# Edit database configuration as needed

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

#### Option C: Docker Setup

```bash
# Start all services (includes automatic initialization)
docker-compose up

# Or start in background
docker-compose up -d

# View logs
docker-compose logs -f metrics-service
```

The Docker setup includes automatic initialization that will:

- ✅ Wait for database to be ready
- ✅ Run database migrations automatically
- ✅ Initialize Django-Ansible-Base ServiceID
- ✅ Create static files directory
- ✅ Start the Django development server

Your service will be available at http://localhost:8000

**Default admin credentials:** `admin` / `admin123` (create with: `docker-compose exec metrics-service python manage.py createsuperuser`)

## Current Status

### ✅ Template Features Ready

- ✅ GitHub template configuration
- ✅ Modern project structure
- ✅ Docker composition with PostgreSQL and Redis
- ✅ Development scripts and automation
- ✅ Comprehensive documentation
- ✅ Requirements and dependency management
- ✅ Template variable placeholders
- ✅ **Comprehensive Test Suite** - 35%+ coverage with 8 new test files
- ✅ **Integration Tests** - Management commands, API endpoints, utilities
- ✅ **Test Automation** - Coverage reporting and CI-ready test structure

### ⚠️ DAB Features (Requires Development Setup)

The template includes advanced AAP features that require the full development environment:

- Django-Ansible-Base integration (RBAC, authentication, etc.)
- Activity stream and audit logging
- OAuth2 and JWT authentication
- Resource registry and cross-service communication
- Advanced permission management

**Note**: For immediate basic Django development, the DAB features can be enabled gradually by uncommenting sections in the models and settings files.

## Overview

This template provides a production-ready foundation for building AAP services with:

- ✅ **Modern Django Architecture** - Django 4.2+ with apps-based structure
- ✅ **Django-Ansible-Base Integration** - Full RBAC, authentication, and DAB components
- ✅ **API-First Design** - RESTful APIs with DRF, versioning, and OpenAPI documentation
- ✅ **Modern Tooling** - Ruff, Black, mypy, pytest with comprehensive configuration
- ✅ **Settings Management** - Dynaconf-based configuration with environment overrides
- ✅ **Background Tasks** - Dispatcherd integration with multi-worker support, health monitoring, and scheduled tasks
- ✅ **Health Monitoring** - Comprehensive health checks for Kubernetes deployment
- ✅ **AAP-Dev Integration** - Ready for local development with AAP ecosystem
- ✅ **Security** - OAuth2, JWT, and role-based access control
- ✅ **Testing** - Unit, integration, and functional test structure
- ✅ **Immediate Runability** - Uses PostgreSQL for production-ready deployment
- ✅ **Template Ready** - Configured for GitHub template repository use

## Setup and Development

### Initial Setup

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd platform-service-template
   ```

2. **Set up Python environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Database setup**

   ```bash
   python manage.py migrate
   python manage.py init_service_id  # Initialize ServiceID for ansible-base
   ```

4. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

### ServiceID Initialization

This project uses `django-ansible-base` which requires a `ServiceID` object to exist in the database for the resource registry system to function properly.

**Important**: Always run `python manage.py init_service_id` after initial migrations to avoid resource registry errors.

This command:

- Creates a ServiceID if none exists
- Shows the existing ServiceID if one is already present
- Is safe to run multiple times

### Development

### Prerequisites

- Python 3.10+
- PostgreSQL 13+
- Redis 6+
- Git

### Local Development Setup

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd platform-service-template
   ```

2. **Create virtual environment**:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:

   ```bash
   pip install -e ".[dev]"
   ```

4. **Set up environment**:

   ```bash
   # Copy example configuration
   cp config/settings.yaml.example config/settings.yaml

   # Edit config/settings.yaml with your local settings
   ```

5. **Set up database**:

   ```bash
   # Create PostgreSQL database
   createdb metrics_service

   # Run migrations
   python manage.py migrate

   # Create superuser
   python manage.py createsuperuser
   ```

6. **Run development server**:

   ```bash
   python manage.py runserver
   ```

7. **Access the service**:
   - API: http://localhost:8000/api/v1/
   - Admin: http://localhost:8000/admin/
   - API Docs: http://localhost:8000/api/docs/
   - Health: http://localhost:8000/health/

## Configuration

### Environment Variables

Configure the service using environment variables with the `metrics_service_` prefix:

```bash
# Core settings
METRICS_SERVICE_ENV=development
METRICS_SERVICE_SECRET_KEY=your-secret-key
metrics_service_ALLOWED_HOSTS=localhost,127.0.0.1

# Database
METRICS_SERVICE_DB_HOST=localhost
METRICS_SERVICE_DB_PORT=55432
METRICS_SERVICE_DB_USER=metrics_service
METRICS_SERVICE_DB_PASSWORD=metrics_service
METRICS_SERVICE_DB_NAME=metrics_service

# Cache
metrics_service_REDIS_URL=redis://localhost:6379/0

# Feature Flags
metrics_service_DISPATCHERD_ENABLED=false

# Background Tasks (Dispatcherd)
metrics_service_DISPATCHERD_WORKERS=4
metrics_service_DISPATCHERD_MAX_TASKS=100
metrics_service_DISPATCHERD_TIMEOUT=3600
```

### Dynaconf Settings

Use `config/settings.yaml` for complex configuration:

```yaml
environment: development

databases:
  default:
    engine: django.db.backends.postgresql
    host: localhost
    port: 55432
    user: metrics_service
    password: metrics_service
    name: metrics_service

feature_flags:
  dispatcherd_enabled: false

dispatcherd:
  workers: 4
  max_tasks: 100
  timeout: 3600
```

## API Documentation

### Endpoints

- **Users**: `/api/v1/users/` - User management
- **Organizations**: `/api/v1/organizations/` - Organization management
- **Teams**: `/api/v1/teams/` - Team management
### Authentication

The API supports multiple authentication methods:

1. **Session Authentication** - For web interface
2. **OAuth2 Tokens** - For third-party integrations
3. **JWT Tokens** - For service-to-service communication

### API Features

- **Versioning**: URL-based versioning (`/api/v1/`, `/api/v2/`)
- **Filtering**: Field-based filtering with operators (`?name__icontains=test`)
- **Search**: Full-text search (`?search=keyword`)
- **Pagination**: Cursor-based pagination (25 items per page)
- **Sorting**: Multi-field sorting (`?ordering=-created,name`)

## Development

### Code Style

This project uses modern Python tooling:

```bash
# Format code
black .

# Lint code
ruff check .

# Type checking
mypy .

# Sort imports
isort .
```

### Testing

This project maintains comprehensive test coverage with multiple test categories:

#### 🎯 Test Coverage Status

- **Overall Coverage**: 35%+ (significantly improved from baseline)
- **Key Modules Coverage**:
  - `metrics_service.py` command: 90% (comprehensive integration tests)
  - API serializers: 61% (base_serializers.py)
  - API views: 79% (views.py), 48% (tasks/views.py)
  - Core models: 39%
  - Admin interfaces: 75%+

#### 🧪 Test Categories

- **Unit Tests** (`tests/unit/`): Individual component testing with extensive mocking
- **Integration Tests** (`tests/integration/`): Component interaction testing
- **API Tests**: Comprehensive REST API endpoint testing
- **Management Command Tests**: Django command functionality testing

#### 🚀 Running Tests

```bash
# Quick test with Docker PostgreSQL (recommended)
./scripts/run-tests.sh

# Test with local PostgreSQL
./scripts/run-tests.sh --local

# Run specific test path
./scripts/run-tests.sh --path=tests/unit/

# Verbose output
./scripts/run-tests.sh --verbose

# Manual testing (after environment setup)
pytest --cov=apps --cov=metrics_service --cov-report=html --cov-report=term-missing

# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Test specific modules
pytest tests/unit/test_metrics_service_command.py  # Management command tests
pytest tests/unit/test_api_views_extended.py        # API functionality tests
pytest tests/unit/test_final_coverage.py           # Utility and mixin tests
```

#### 📊 Coverage Reporting

```bash
# Generate HTML coverage report
pytest --cov=apps --cov=metrics_service --cov-report=html

# View coverage report
open htmlcov/index.html
```

#### 🎯 Test Highlights

- **Management Commands**: Comprehensive tests for `metrics_service` command including process management, threading, signal handling
- **API Layer**: Full CRUD operations, serialization, validation, and error handling
- **Core Utilities**: Helper functions, mixins, and utility classes
- **Authentication**: Permission systems and user management
- **Background Tasks**: Task execution and dispatcher functionality

### Database Migrations

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Reset database (development only)
python manage.py flush
```

### Background Tasks & Dispatcherd

This template includes comprehensive background task processing using `dispatcherd>=2025.5.21`.

#### 🔧 Core Features

- **Optional Integration** - Include with `pip install -e ".[dispatcherd]"`
- **Feature Flag Control** - Enable/disable via `DISPATCHERD_ENABLED`
- **Multi-worker Support** - Configurable worker processes with auto-respawning
- **Health Monitoring** - Built-in health checks and monitoring
- **Predefined Tasks** - Ready-to-use task examples
- **Scheduled Tasks** - Cron-like scheduling support

#### ⚙️ Configuration

**Environment Variables:**

```bash
metrics_service_DISPATCHERD_ENABLED=true    # Enable/disable dispatcherd
metrics_service_DISPATCHERD_WORKERS=4       # Number of worker processes
metrics_service_DISPATCHERD_MAX_TASKS=100   # Max tasks per worker before respawn
metrics_service_DISPATCHERD_TIMEOUT=3600    # Task timeout in seconds
```

**YAML Configuration:**

```yaml
feature_flags:
  dispatcherd_enabled: true

dispatcherd:
  workers: 4
  max_tasks: 100
  timeout: 3600
```

#### 🚀 Running Workers

**Basic Usage:**

```bash
# Enable dispatcherd
export metrics_service_DISPATCHERD_ENABLED=true

# Start with default settings
python manage.py run_dispatcher

# Start with custom configuration
python manage.py run_dispatcher --workers 8 --timeout 7200 --max-tasks 200 --log-level DEBUG
```

**Command Options:**

- `--workers` - Number of worker processes (default: 4)
- `--timeout` - Task timeout in seconds (default: 3600)
- `--max-tasks` - Max tasks per worker before respawn (default: 100)
- `--log-level` - Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)

#### 📋 Built-in Tasks

**Available Task Functions:**

1. **`cleanup_old_data`** - Clean up old system data

   ```python
   # Usage data
   {"days_old": 30}
   ```

2. **`send_notification_email`** - Send notification emails

   ```python
   # Usage data
   {"recipient": "user@example.com", "subject": "Notification", "message": "..."}
   ```

3. **`process_user_data`** - Background user data processing
   ```python
   # Usage data
   {"user_id": 123, "operation": "sync"}  # operations: sync, validate
   ```

#### ⏰ Scheduled Tasks

Configure automatic task scheduling:

```python
SCHEDULED_TASKS = {
    "daily_cleanup": {
        "function": "cleanup_old_data",
        "schedule": 86400,  # Run daily (in seconds)
        "data": {"days_old": 30},
    },
}
```

#### 🏥 Health Monitoring

Check dispatcherd status:

```bash
# Check dispatcherd health
curl http://localhost:8000/health/?check=dispatcherd

# Response
{
  "status": "healthy|disabled|unhealthy",
  "enabled": true,
  "config": {...},
  "details": "Dispatcherd configuration healthy"
}
```

#### 🔧 Adding Custom Tasks

1. **Define your task function in `apps/core/tasks.py`:**

   ```python
   def my_custom_task(data: Dict[str, Any]) -> Dict[str, Any]:
       """Your custom background task."""
       try:
           # Your task logic here
           return {"status": "success", "result": "..."}
       except Exception as e:
           return {"status": "error", "error": str(e)}
   ```

2. **Register in `TASK_FUNCTIONS`:**

   ```python
   TASK_FUNCTIONS = {
       # ... existing tasks ...
       "my_custom_task": my_custom_task,
   }
   ```

3. **Execute via dispatcherd:**
   ```python
   # Your task will be available to the dispatcher
   ```

## Deployment

### Docker

```bash
# Build image
docker build -t metrics-service .

# Run container (requires database)
docker run -p 8000:8000 \
  -e METRICS_SERVICE_DB_HOST=your-db-host \
  -e METRICS_SERVICE_DB_USER=your-db-user \
  -e METRICS_SERVICE_DB_PASSWORD=your-db-password \
  -e METRICS_SERVICE_DB_NAME=your-db-name \
  metrics-service

# Or use docker-compose for complete stack
docker-compose up -d
```

**Automatic Initialization**: The Docker container includes an entrypoint script (`scripts/docker-entrypoint.sh`) that automatically:

- Waits for database availability
- Runs Django migrations
- Initializes Django-Ansible-Base ServiceID
- Creates required directories
- Starts the application

**Environment Variables**: See `docker-compose.yml` for all available configuration options.

### Kubernetes

For AAP-dev integration:

```bash
# Enable service in AAP-dev
export AAP_METRICS_SERVICE=true
export AAP_VERSION=2.6

# Deploy to AAP-dev
make aap
```

### Production Settings

Set these environment variables for production:

```bash
METRICS_SERVICE_ENV=production
metrics_service_DEBUG=false
METRICS_SERVICE_SECRET_KEY=<secure-secret-key>
metrics_service_ALLOWED_HOSTS=yourdomain.com
METRICS_SERVICE_DB_HOST=<production-db-host>
metrics_service_REDIS_URL=<production-redis-url>
```

## Architecture

### Project Structure

```
metrics-service/
├── apps/                          # Django applications
│   ├── api/                       # API endpoints (versioned)
│   │   └── v1/                    # API version 1
│   ├── core/                      # Core business logic
│   │   ├── models.py              # Database models
│   │   ├── tasks.py               # Background tasks
│   │   └── management/            # Management commands
│   └── health/                    # Health check endpoints
├── metrics_service/                    # Main Django project
│   └── settings/                  # Split settings
├── tests/                         # Test suite
│   ├── unit/                      # Unit tests
│   ├── integration/               # Integration tests
│   └── functional/                # Functional tests
├── config/                        # Configuration files
├── manifests/                     # Kubernetes manifests
├── skaffolding/                   # AAP-dev integration
└── pyproject.toml                 # Modern Python configuration
```

### Key Features

#### Django-Ansible-Base Integration

- **RBAC**: Role-based access control with permission registry
- **Authentication**: Multi-backend authentication (local, LDAP, SAML, OAuth)
- **Resource Registry**: Cross-service resource synchronization
- **Activity Stream**: Audit logging for all model changes
- **Feature Flags**: Runtime feature control

#### API Design

- **RESTful**: Following REST principles with proper HTTP methods
- **Versioned**: URL-based API versioning for backward compatibility
- **Filtered**: Comprehensive filtering with field lookups
- **Paginated**: Efficient pagination with metadata
- **Documented**: OpenAPI 3.0 with Swagger UI and ReDoc

#### Monitoring & Health

- **Health Checks**: Database, cache, and service-specific checks
- **Kubernetes Probes**: Liveness and readiness probes
- **Logging**: Structured logging with request ID tracking
- **Metrics**: Ready for Prometheus integration

## Contributing

### Development Workflow

1. **Create feature branch**: `git checkout -b feature/my-feature`
2. **Make changes**: Follow code style and add tests
3. **Run tests**: `pytest` and ensure all pass
4. **Run linting**: `ruff check .` and `black .`
5. **Commit changes**: Use conventional commits
6. **Create PR**: Submit for review

### Code Standards

- **Line Length**: 120 characters (configurable in pyproject.toml)
- **Imports**: Sorted with isort, grouped by type
- **Docstrings**: Required for public APIs
- **Type Hints**: Encouraged for new code
- **Tests**: Required for new features

### Pre-commit Hooks

Install pre-commit hooks for automatic code quality:

```bash
pre-commit install
```

## AAP Integration

### Resource Server

Configure for AAP Gateway integration:

```yaml
# In config/settings.yaml
resource_server:
  url: https://aap-gateway:9080
  secret_key: your-service-secret
  validate_https: true
```

### Service Registration

The service automatically registers with AAP Gateway when deployed in AAP-dev:

- **Service Type**: `metrics-service`
- **API Endpoints**: `/api/metrics-service/`
- **Health Check**: `/api/metrics-service/health/`

## Troubleshooting

### Common Issues

1. **Database Connection**:

   ```bash
   # Check database settings
   python manage.py dbshell
   ```

2. **Migration Issues**:

   ```bash
   # Reset migrations (development only)
   python manage.py migrate core zero
   python manage.py migrate
   ```

3. **Permission Errors**:
   ```bash
   # Rebuild RBAC permissions
   python manage.py migrate_to_rbac
   ```

### Debug Mode

Enable debug mode for development:

```bash
export METRICS_SERVICE_ENV=development
export DJANGO_DEBUG=true
```

### Logs

Check application logs:

```bash
# Development
tail -f logs/metrics_service.log

# Kubernetes
kubectl logs deployment/metrics-service
```

## License

This project is licensed under the Apache License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: Check the `docs/` directory for detailed guides
- **Issues**: Report bugs and feature requests via GitHub issues
- **AAP Community**: Join the AAP community for support and discussions
