#!/bin/bash
set -e

echo "🧪 Testing AAP Service Template with PostgreSQL..."

# Function to cleanup on exit
cleanup() {
    echo "🧹 Cleaning up..."
    if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
        kill "$server_pid" 2>/dev/null || true
    fi
    if [ -d "test_env" ]; then
        deactivate 2>/dev/null || true
        rm -rf test_env
    fi
    docker-compose -f docker-compose.test.yml down -v --remove-orphans 2>/dev/null || true
}

# Set trap to cleanup on script exit
trap cleanup EXIT INT TERM

# Clean up any existing test environment
rm -rf test_env

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

echo "📦 Creating test virtual environment..."
python3 -m venv test_env
source test_env/bin/activate

echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -e ".[test]"

# Set environment variables for testing with Docker PostgreSQL
export DJANGO_SETTINGS_MODULE="metrics_service.settings.test"
export METRICS_SERVICE_DB_HOST="127.0.0.1"
export METRICS_SERVICE_DB_PORT="55433"
export METRICS_SERVICE_DB_USER="metrics_service"
export METRICS_SERVICE_DB_PASSWORD="metrics_service"
export METRICS_SERVICE_TEST_DB_NAME="test_metrics_service"
export METRICS_SERVICE_REDIS_URL="redis://127.0.0.1:6380/0"

echo "🗄️  Running migrations..."
python manage.py migrate --settings=metrics_service.settings.test

echo "🔍 Running health check..."
python manage.py check --settings=metrics_service.settings.test

echo "🧪 Running tests..."
python -m pytest tests/ -v --tb=short --cov=metrics_service --cov=apps

echo "🚀 Testing development server startup..."
timeout 15s python manage.py runserver 0.0.0.0:8001 --settings=metrics_service.settings.test &
server_pid=$!

sleep 5

echo "📡 Testing API endpoints..."
if curl -f http://localhost:8001/health/ > /dev/null 2>&1; then
    echo "✅ Health endpoint working"
else
    echo "❌ Health endpoint failed"
fi

if curl -f http://localhost:8001/api/v1/ > /dev/null 2>&1; then
    echo "✅ API endpoint working"
else
    echo "❌ API endpoint failed"
fi

echo "🎉 All tests completed successfully!"
echo "✅ The template works with PostgreSQL backend" 