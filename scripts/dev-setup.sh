#!/bin/bash
set -e

echo "🚀 Setting up AAP Service Template for development..."

# Function to check if we're in a virtual environment
in_venv() {
    [ -n "$VIRTUAL_ENV" ]
}

# Function to activate virtual environment
activate_venv() {
    if [ -f "venv/bin/activate" ]; then
        echo "🔧 Activating existing virtual environment..."
        source venv/bin/activate
    else
        echo "❌ Virtual environment not found. Please create one first."
        exit 1
    fi
}

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" = "$required_version" ]; then
    echo "✅ Python $python_version is compatible"
else
    echo "❌ Python $required_version or higher is required (found $python_version)"
    exit 1
fi

# Check if Docker is available
if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    echo "✅ Docker and Docker Compose are available"
    DOCKER_AVAILABLE=true
else
    echo "⚠️  Docker not available - will use local PostgreSQL"
    DOCKER_AVAILABLE=false
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi

# Ensure we're in the virtual environment
if ! in_venv; then
    activate_venv
fi

echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -e ".[dev]"

# Copy example configuration if it doesn't exist
if [ ! -f "config/settings.yaml" ]; then
    echo "⚙️  Setting up configuration..."
    cp config/settings.yaml.example config/settings.yaml
    echo "✅ Configuration copied from example"
else
    echo "✅ Configuration already exists"
fi

# Setup database
if [ "$DOCKER_AVAILABLE" = true ]; then
    echo "🐳 Setting up PostgreSQL with Docker..."
    echo "🔧 Starting PostgreSQL container..."
    docker-compose up -d postgres redis
    
    echo "⏳ Waiting for PostgreSQL to be ready..."
    max_attempts=30
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if docker-compose exec -T postgres pg_isready -U metrics_service -d metrics_service > /dev/null 2>&1; then
            echo "✅ PostgreSQL is ready!"
            break
        fi
        attempt=$((attempt + 1))
        echo "Waiting for PostgreSQL... (attempt $attempt/$max_attempts)"
        sleep 2
    done
    
    if [ $attempt -eq $max_attempts ]; then
        echo "❌ PostgreSQL failed to start after $max_attempts attempts"
        echo "Please check Docker setup or use local PostgreSQL"
        exit 1
    fi
    
    # Set environment variables for Docker PostgreSQL
    export METRICS_SERVICE_DB_HOST="127.0.0.1"
    export METRICS_SERVICE_DB_PORT="55432"
    export METRICS_SERVICE_DB_USER="metrics_service"
    export METRICS_SERVICE_DB_PASSWORD="metrics_service"
    export METRICS_SERVICE_DB_NAME="metrics_service"
    export METRICS_SERVICE_REDIS_URL="redis://127.0.0.1:6379/0"
else
    echo "🗄️  Using local PostgreSQL configuration..."
    echo "⚠️  Make sure PostgreSQL is installed and running locally"
    echo "    Database: metrics_service"
    echo "    User: metrics_service"
    echo "    Password: metrics_service"
fi

echo "🗄️  Running database migrations..."
python manage.py migrate

echo "🔍 Running health check..."
python manage.py check

# Create superuser if in development
echo ""
echo "🔐 Would you like to create a superuser? (y/n)"
read -r create_superuser
if [ "$create_superuser" = "y" ] || [ "$create_superuser" = "Y" ]; then
    python manage.py createsuperuser
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "To start the development server:"
echo "  source venv/bin/activate"
echo "  python manage.py runserver"
echo ""
echo "Your service will be available at:"
echo "  • API: http://localhost:8000/api/v1/"
echo "  • Admin: http://localhost:8000/admin/"
echo "  • API Docs: http://localhost:8000/api/docs/"
echo "  • Health: http://localhost:8000/health/"
echo ""
if [ "$DOCKER_AVAILABLE" = true ]; then
    echo "Database services are running in Docker containers:"
    echo "  • PostgreSQL: localhost:55432"
    echo "  • Redis: localhost:6379"
    echo ""
    echo "To stop containers: docker-compose down"
    echo "To start full stack: docker-compose up"
fi
echo "" 