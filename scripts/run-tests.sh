#!/bin/bash
set -e

echo "🧪 Running tests for AAP Service Template..."

# Default values
USE_DOCKER=true
VERBOSE=false
COVERAGE=true
TEST_PATH="tests/"
CLEANUP=true

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --local)
            USE_DOCKER=false
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --no-coverage)
            COVERAGE=false
            shift
            ;;
        --no-cleanup)
            CLEANUP=false
            shift
            ;;
        --path=*)
            TEST_PATH="${1#*=}"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --local         Use local PostgreSQL instead of Docker"
            echo "  --verbose, -v   Verbose test output"
            echo "  --no-coverage   Skip coverage reporting"
            echo "  --no-cleanup    Don't cleanup Docker containers after tests"
            echo "  --path=PATH     Run tests from specific path (default: tests/)"
            echo "  --help, -h      Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Function to check if we're in a virtual environment
in_venv() {
    [ -n "$VIRTUAL_ENV" ]
}

# Function to cleanup on exit
cleanup() {
    if [ "$CLEANUP" = true ] && [ "$USE_DOCKER" = true ]; then
        echo "🧹 Cleaning up Docker containers..."
        docker-compose -f docker-compose.test.yml down -v --remove-orphans 2>/dev/null || true
    fi
}

# Set trap to cleanup on script exit
if [ "$CLEANUP" = true ]; then
    trap cleanup EXIT INT TERM
fi

# Check if we're in a virtual environment
if ! in_venv; then
    echo "⚠️  Not in a virtual environment. Activating..."
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        echo "❌ Virtual environment not found. Please run dev-setup.sh first."
        exit 1
    fi
fi

# Setup test environment
if [ "$USE_DOCKER" = true ]; then
    echo "🐳 Starting test database containers..."
    docker-compose -f docker-compose.test.yml up -d
    
    echo "⏳ Waiting for PostgreSQL to be ready..."
    max_attempts=30
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if docker-compose -f docker-compose.test.yml exec -T postgres-test pg_isready -U metrics_service -d test_metrics_service > /dev/null 2>&1; then
            echo "✅ PostgreSQL is ready!"
            break
        fi
        attempt=$((attempt + 1))
        echo "Waiting for PostgreSQL... (attempt $attempt/$max_attempts)"
        sleep 2
    done
    
    if [ $attempt -eq $max_attempts ]; then
        echo "❌ PostgreSQL failed to start after $max_attempts attempts"
        exit 1
    fi
    
    # Set environment variables for Docker PostgreSQL
    export METRICS_SERVICE_DB_HOST="127.0.0.1"
    export METRICS_SERVICE_DB_PORT="55433"
    export METRICS_SERVICE_DB_USER="metrics_service"
    export METRICS_SERVICE_DB_PASSWORD="metrics_service"
    export METRICS_SERVICE_TEST_DB_NAME="test_metrics_service"
    export METRICS_SERVICE_REDIS_URL="redis://127.0.0.1:6380/0"
else
    echo "🗄️  Using local PostgreSQL..."
    echo "⚠️  Make sure PostgreSQL is running with test database configured"
    
    # Set default environment variables for local PostgreSQL
    export METRICS_SERVICE_DB_HOST="${METRICS_SERVICE_DB_HOST:-127.0.0.1}"
    export METRICS_SERVICE_DB_PORT="${METRICS_SERVICE_DB_PORT:-5432}"
    export METRICS_SERVICE_DB_USER="${METRICS_SERVICE_DB_USER:-metrics_service}"
    export METRICS_SERVICE_DB_PASSWORD="${METRICS_SERVICE_DB_PASSWORD:-metrics_service}"
    export METRICS_SERVICE_TEST_DB_NAME="${METRICS_SERVICE_TEST_DB_NAME:-test_metrics_service}"
fi

# Set Django settings
export DJANGO_SETTINGS_MODULE="metrics_service.settings.test"

echo "🗄️  Running migrations..."
python manage.py migrate --settings=metrics_service.settings.test

echo "🔍 Running health check..."
python manage.py check --settings=metrics_service.settings.test

# Build pytest command
pytest_cmd="python -m pytest $TEST_PATH"

if [ "$VERBOSE" = true ]; then
    pytest_cmd="$pytest_cmd -v"
fi

if [ "$COVERAGE" = true ]; then
    pytest_cmd="$pytest_cmd --cov=metrics_service --cov=apps --cov-report=term-missing --cov-report=html --cov-report=xml"
fi

pytest_cmd="$pytest_cmd --tb=short --strict-markers"

echo "🧪 Running tests..."
echo "Command: $pytest_cmd"
eval $pytest_cmd

echo "🎉 Tests completed successfully!"

if [ "$COVERAGE" = true ]; then
    echo ""
    echo "📊 Coverage reports generated:"
    echo "  • Terminal: Displayed above"
    echo "  • HTML: htmlcov/index.html"
    echo "  • XML: coverage.xml"
fi
