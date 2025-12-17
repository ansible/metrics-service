#!/bin/bash
#
# Install Metrics Service systemd units
#
# This script installs the systemd service files for the metrics service
# production deployment. It should be run with sudo/root privileges.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}Installing Metrics Service systemd units...${NC}"
echo ""

# Set deployment directory (adjust if needed)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_SOURCE_DIR="${SCRIPT_DIR}/../systemd"
SYSTEMD_TARGET_DIR="/etc/systemd/system"

# Copy systemd unit files
echo -e "${YELLOW}Copying systemd unit files...${NC}"
cp -v "${SYSTEMD_SOURCE_DIR}/metrics-service.target" "${SYSTEMD_TARGET_DIR}/"
cp -v "${SYSTEMD_SOURCE_DIR}/metrics-service-web.service" "${SYSTEMD_TARGET_DIR}/"
cp -v "${SYSTEMD_SOURCE_DIR}/metrics-service-dispatcher.service" "${SYSTEMD_TARGET_DIR}/"
cp -v "${SYSTEMD_SOURCE_DIR}/metrics-service-scheduler.service" "${SYSTEMD_TARGET_DIR}/"

# Set proper permissions
echo -e "${YELLOW}Setting permissions...${NC}"
chmod 644 "${SYSTEMD_TARGET_DIR}/metrics-service.target"
chmod 644 "${SYSTEMD_TARGET_DIR}/metrics-service-web.service"
chmod 644 "${SYSTEMD_TARGET_DIR}/metrics-service-dispatcher.service"
chmod 644 "${SYSTEMD_TARGET_DIR}/metrics-service-scheduler.service"

# Reload systemd
echo -e "${YELLOW}Reloading systemd daemon...${NC}"
systemctl daemon-reload

echo ""
echo -e "${GREEN}✓ Systemd units installed successfully!${NC}"
echo ""
echo "Next steps:"
echo "  1. Ensure /opt/metrics-service is installed with code and virtualenv"
echo "  2. Create metrics-service user: sudo useradd -r -s /bin/false metrics-service"
echo "  3. Create required directories:"
echo "     sudo mkdir -p /var/log/metrics-service /run/metrics-service"
echo "     sudo chown metrics-service:metrics-service /var/log/metrics-service /run/metrics-service"
echo "  4. Create environment file: /etc/metrics-service/environment"
echo "  5. Enable services:"
echo "     sudo systemctl enable metrics-service.target"
echo "  6. Start services:"
echo "     sudo systemctl start metrics-service.target"
echo "  7. Check status:"
echo "     sudo systemctl status metrics-service.target"
echo ""
