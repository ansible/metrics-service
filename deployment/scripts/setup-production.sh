#!/bin/bash
#
# Setup Metrics Service for Production Deployment
#
# This script sets up the complete production environment including:
# - System user creation
# - Directory structure
# - Virtual environment
# - Dependencies installation
# - Initial database setup
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/metrics-service"
SERVICE_USER="metrics-service"
SERVICE_GROUP="metrics-service"
LOG_DIR="/var/log/metrics-service"
RUN_DIR="/run/metrics-service"
CONFIG_DIR="/etc/metrics-service"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Metrics Service Production Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Create service user
echo -e "${YELLOW}[1/8] Creating service user...${NC}"
if id "${SERVICE_USER}" &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} User '${SERVICE_USER}' already exists"
else
    useradd -r -s /bin/false -d "${INSTALL_DIR}" "${SERVICE_USER}"
    echo -e "  ${GREEN}✓${NC} Created user '${SERVICE_USER}'"
fi

# Step 2: Create directories
echo -e "${YELLOW}[2/8] Creating directories...${NC}"
mkdir -p "${INSTALL_DIR}"
mkdir -p "${LOG_DIR}"
mkdir -p "${RUN_DIR}"
mkdir -p "${CONFIG_DIR}"
echo -e "  ${GREEN}✓${NC} Created directory structure"

# Step 3: Copy application files
echo -e "${YELLOW}[3/8] Installing application files...${NC}"
if [ ! -d "${INSTALL_DIR}/metrics_service" ]; then
    echo -e "  ${YELLOW}!${NC} Please copy your application code to ${INSTALL_DIR}"
    echo -e "  ${YELLOW}!${NC} Example: rsync -av --exclude='.git' ./ ${INSTALL_DIR}/"
else
    echo -e "  ${GREEN}✓${NC} Application files found"
fi

# Step 4: Set up Python virtual environment
echo -e "${YELLOW}[4/8] Setting up Python virtual environment...${NC}"
if [ ! -d "${INSTALL_DIR}/.venv" ]; then
    cd "${INSTALL_DIR}"
    python3.12 -m venv .venv
    echo -e "  ${GREEN}✓${NC} Created virtual environment"
else
    echo -e "  ${GREEN}✓${NC} Virtual environment already exists"
fi

# Step 5: Install dependencies
echo -e "${YELLOW}[5/8] Installing Python dependencies...${NC}"
cd "${INSTALL_DIR}"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
.venv/bin/pip install uwsgi
echo -e "  ${GREEN}✓${NC} Installed dependencies"

# Step 6: Set up environment file
echo -e "${YELLOW}[6/8] Creating environment configuration...${NC}"
if [ ! -f "${CONFIG_DIR}/environment" ]; then
    cat > "${CONFIG_DIR}/environment" << 'EOF'
# Metrics Service Environment Configuration
# Edit this file to customize your deployment

# Django Settings
DJANGO_SETTINGS_MODULE=metrics_service.settings
METRICS_SERVICE_MODE=production

# Database Configuration
METRICS_SERVICE_DB_HOST=localhost
METRICS_SERVICE_DB_PORT=5432
METRICS_SERVICE_DB_NAME=metrics_service
METRICS_SERVICE_DB_USER=metrics_service
METRICS_SERVICE_DB_PASSWORD=changeme

# Django Secret Key (CHANGE THIS!)
METRICS_SERVICE_SECRET_KEY=changeme-generate-a-secure-random-key

# Allowed Hosts (comma-separated)
METRICS_SERVICE_ALLOWED_HOSTS=localhost,127.0.0.1

# Logging
METRICS_SERVICE_LOG_LEVEL=INFO

# Feature Flags
METRICS_SERVICE_ANONYMIZED_DATA=true
METRICS_SERVICE_METRICS_COLLECTION=false
METRICS_SERVICE_DEVELOPER_MODE_ENABLED=false
EOF
    echo -e "  ${GREEN}✓${NC} Created environment file at ${CONFIG_DIR}/environment"
    echo -e "  ${RED}!${NC} IMPORTANT: Edit ${CONFIG_DIR}/environment and set SECRET_KEY and database credentials"
else
    echo -e "  ${GREEN}✓${NC} Environment file already exists"
fi

# Step 7: Set permissions
echo -e "${YELLOW}[7/8] Setting permissions...${NC}"
chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${LOG_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${RUN_DIR}"
chmod 750 "${INSTALL_DIR}"
chmod 750 "${LOG_DIR}"
chmod 750 "${RUN_DIR}"
chmod 640 "${CONFIG_DIR}/environment"
echo -e "  ${GREEN}✓${NC} Set ownership and permissions"

# Step 8: Database setup
echo -e "${YELLOW}[8/8] Database initialization...${NC}"
echo -e "  ${YELLOW}!${NC} Run these commands manually after configuring the database:"
echo -e "      cd ${INSTALL_DIR}"
echo -e "      sudo -u ${SERVICE_USER} .venv/bin/python manage.py migrate"
echo -e "      sudo -u ${SERVICE_USER} .venv/bin/python manage.py metrics_service init-service-id"
echo -e "      sudo -u ${SERVICE_USER} .venv/bin/python manage.py metrics_service init-system-tasks"
echo -e "      sudo -u ${SERVICE_USER} .venv/bin/python manage.py createsuperuser"
echo -e "      sudo -u ${SERVICE_USER} .venv/bin/python manage.py collectstatic --noinput"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Production setup complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Edit ${CONFIG_DIR}/environment with your configuration"
echo "  2. Set up PostgreSQL database"
echo "  3. Run database migrations (commands shown above)"
echo "  4. Install systemd services: ./install-systemd-services.sh"
echo "  5. Start services: systemctl start metrics-service.target"
echo ""
