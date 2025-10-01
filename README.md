# Metrics Service

A modern Django-based service built for the Ansible Automation Platform (AAP) ecosystem, featuring comprehensive task management, REST APIs, and background job processing.

## Features

- **🚀 Modern Django Architecture** - Django 4.2+ with clean app-based structure
- **📊 Task Management System** - Background task processing with scheduling and monitoring
- **🔌 REST API** - Versioned RESTful APIs with OpenAPI documentation
- **🔐 Authentication & Authorization** - Django-Ansible-Base integration with RBAC
- **📈 Real-time Dashboard** - Web-based task monitoring and management interface
- **🐳 Docker Ready** - Complete containerization with PostgreSQL
- **🧪 Comprehensive Testing** - Unit and integration tests with coverage reporting
- **📝 API Documentation** - Interactive Swagger/OpenAPI documentation

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd metrics-service

# Start all services
docker-compose up -d

# Create a superuser (optional)
docker-compose exec metrics-service python manage.py createsuperuser
```

Your service will be available at:
- **Application**: http://localhost:8000
- **API Documentation**: http://localhost:8000/api/docs/
- **Admin Interface**: http://localhost:8000/admin/
- **Task Dashboard**: http://localhost:8000/dashboard/

### Option 2: Local Development

```bash
# Prerequisites: Python 3.10+, PostgreSQL 13+

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Configure database (update as needed)
cp .env.example .env

# Set up database
python manage.py migrate
python manage.py init_service_id
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

## Architecture

### Project Structure

```
metrics-service/
├── apps/
│   ├── api/v1/              # REST API endpoints
│   ├── core/                # Core models and business logic
│   ├── dashboard/           # Web dashboard interface
│   └── tasks/               # Background task system
├── metrics_service/
│   ├── settings/            # Environment-specific settings
│   └── urls.py              # URL configuration
├── tests/                   # Test suite
├── config/                  # Configuration files
└── docker-compose.yml       # Container orchestration
```

### Key Components

**Core Models** (`apps/core/models.py`)
- User management with Django-Ansible-Base
- Organization and team hierarchy
- RBAC permissions and roles

**Task System** (`apps/tasks/`)
- Database-driven background tasks
- Task scheduling and dependencies
- Execution tracking and monitoring
- Built-in task functions for common operations

**API Layer** (`apps/api/v1/`)
- RESTful endpoints with filtering and pagination
- OpenAPI/Swagger documentation
- Authentication and permission controls

**Dashboard** (`apps/dashboard/`)
- Real-time task monitoring
- Task creation and management interface
- Live status updates every 5 seconds

## API Usage

### Authentication

The API supports multiple authentication methods:
- Session authentication (for web interface)
- Token authentication
- OAuth2 tokens (for third-party integrations)

### Core Endpoints

```bash
# List all tasks
GET /api/v1/tasks/

# Create a new task
POST /api/v1/tasks/
{
  "name": "Data Cleanup",
  "function_name": "cleanup_old_data",
  "task_data": {"days_old": 30}
}

# Get running tasks
GET /api/v1/tasks/running/

# Retry a failed task
POST /api/v1/tasks/{id}/retry/

# Available task functions
GET /api/v1/tasks/available_functions/
```

### Built-in Task Functions

- `cleanup_old_data` - Clean up old system data
- `send_notification_email` - Send notification emails
- `process_user_data` - Process user data in background
- `execute_db_task` - Execute database-defined tasks

## Background Tasks

The service includes a powerful background task system using Dispatcherd:

### Running Task Workers

```bash
# Start task dispatcher
python manage.py run_dispatcherd

# Start with custom configuration
python manage.py run_dispatcherd --workers 4 --timeout 3600

# Using Docker (automatic with docker-compose)
docker-compose up metrics-dispatcher
```

### Task Management

Create and manage tasks through:
- **REST API** - Programmatic task creation
- **Web Dashboard** - Visual task management
- **Django Admin** - Administrative interface
- **Management Commands** - CLI task operations

## Development

### Code Quality Tools

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

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=apps --cov=metrics_service --cov-report=html

# Run specific test categories
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
```

### Database Operations

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Initialize DAB ServiceID (required after first migration)
python manage.py init_service_id
```

## Configuration

### Environment Variables

Key configuration options:

```bash
# Database
METRICS_SERVICE_DB_HOST=localhost
METRICS_SERVICE_DB_PORT=55432
METRICS_SERVICE_DB_USER=metrics_service
METRICS_SERVICE_DB_PASSWORD=metrics_service
METRICS_SERVICE_DB_NAME=metrics_service

# Django
METRICS_SERVICE_SECRET_KEY=your-secret-key
METRICS_SERVICE_DEBUG=false
METRICS_SERVICE_ALLOWED_HOSTS=localhost,yourdomain.com

```

### Settings Files

Configuration is managed through:
- **Environment variables** - Runtime configuration
- **`config/settings.yaml`** - Complex configuration via Dynaconf

## Deployment

### Docker Production

```bash
# Build production image
docker build -t metrics-service .

# Run with production settings
docker run -p 8000:8000 \
  -e METRICS_SERVICE_ENV=production \
  -e METRICS_SERVICE_SECRET_KEY=your-secret-key \
  -e METRICS_SERVICE_DB_HOST=your-db-host \
  metrics-service


## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes with tests
4. Run the test suite: `pytest`
5. Run code quality checks: `ruff check . && black . && mypy .`
6. Submit a pull request

### Development Standards

- **Code Style**: Black formatting, 120 character line length
- **Type Hints**: Required for all new code
- **Documentation**: Docstrings for public APIs
- **Testing**: Test coverage for new features
- **Commits**: Conventional commit messages

## License

This project is licensed under the Apache License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: Check the [CLAUDE.md](CLAUDE.md) file for detailed development guidance
- **Issues**: Report bugs and feature requests via GitHub issues
- **API Documentation**: Interactive docs available at `/api/docs/` when running
