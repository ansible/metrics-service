#!/bin/bash
set -e

echo "🚀 Setting up AAP Service Template for development..."

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

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

echo "🔧 Activating virtual environment..."
source venv/bin/activate

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

# Run database migrations
echo "🗄️  Setting up database..."
python manage.py migrate

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
echo "For Docker setup:"
echo "  docker-compose up"
echo "" 