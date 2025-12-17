#!/bin/bash
#
# Run Metrics Service containers locally with Podman
#
# This script runs all three containers locally for testing purposes.
# For production, use systemd units or OpenShift deployment.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_ENGINE="${CONTAINER_ENGINE:-podman}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-localhost}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
NETWORK_MODE="${NETWORK_MODE:-host}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Running Metrics Service Containers${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if images exist
for image in metrics-service-web metrics-service-dispatcher metrics-service-scheduler; do
    if ! ${CONTAINER_ENGINE} image exists "${IMAGE_REGISTRY}/${image}:${IMAGE_TAG}"; then
        echo -e "${RED}Error: Image ${IMAGE_REGISTRY}/${image}:${IMAGE_TAG} not found${NC}"
        echo "Run ./deployment/scripts/build-containers.sh first"
        exit 1
    fi
done

# Stop existing containers
echo -e "${YELLOW}Stopping existing containers...${NC}"
${CONTAINER_ENGINE} stop metrics-service-web 2>/dev/null || true
${CONTAINER_ENGINE} stop metrics-service-dispatcher 2>/dev/null || true
${CONTAINER_ENGINE} stop metrics-service-scheduler 2>/dev/null || true
${CONTAINER_ENGINE} rm metrics-service-web 2>/dev/null || true
${CONTAINER_ENGINE} rm metrics-service-dispatcher 2>/dev/null || true
${CONTAINER_ENGINE} rm metrics-service-scheduler 2>/dev/null || true
echo ""

# Create shared volume for SQLite database
echo -e "${YELLOW}Creating shared volume for SQLite database...${NC}"
${CONTAINER_ENGINE} volume create metrics-service-sqlite 2>/dev/null || true
echo ""

# Start web container
echo -e "${YELLOW}Starting web container...${NC}"
${CONTAINER_ENGINE} run -d \
    --name metrics-service-web \
    --network="${NETWORK_MODE}" \
    -e METRICS_SERVICE_MODE=production \
    -e METRICS_SERVICE_DB_HOST=localhost \
    -e METRICS_SERVICE_SECRET_KEY=dev-secret-key-change-in-production \
    -e METRICS_SERVICE_ALLOWED_HOSTS=localhost,127.0.0.1 \
    -v metrics-service-sqlite:/opt/app-root/src:Z \
    -p 8000:8000 \
    "${IMAGE_REGISTRY}/metrics-service-web:${IMAGE_TAG}"
echo -e "${GREEN}✓ Web container started (http://localhost:8000)${NC}"
echo ""

# Start dispatcher container
echo -e "${YELLOW}Starting dispatcher container...${NC}"
${CONTAINER_ENGINE} run -d \
    --name metrics-service-dispatcher \
    --network="${NETWORK_MODE}" \
    -e METRICS_SERVICE_MODE=production \
    -e METRICS_SERVICE_DB_HOST=localhost \
    -e METRICS_SERVICE_SECRET_KEY=dev-secret-key-change-in-production \
    -v metrics-service-sqlite:/opt/app-root/src:Z \
    "${IMAGE_REGISTRY}/metrics-service-dispatcher:${IMAGE_TAG}"
echo -e "${GREEN}✓ Dispatcher container started${NC}"
echo ""

# Start scheduler container
echo -e "${YELLOW}Starting scheduler container...${NC}"
${CONTAINER_ENGINE} run -d \
    --name metrics-service-scheduler \
    --network="${NETWORK_MODE}" \
    -e METRICS_SERVICE_MODE=production \
    -e METRICS_SERVICE_DB_HOST=localhost \
    -e METRICS_SERVICE_SECRET_KEY=dev-secret-key-change-in-production \
    -v metrics-service-sqlite:/opt/app-root/src:Z \
    "${IMAGE_REGISTRY}/metrics-service-scheduler:${IMAGE_TAG}"
echo -e "${GREEN}✓ Scheduler container started${NC}"
echo ""

# Show container status
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}All containers running!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
${CONTAINER_ENGINE} ps --filter "name=metrics-service-"
echo ""

echo "View logs:"
echo "  ${CONTAINER_ENGINE} logs -f metrics-service-web"
echo "  ${CONTAINER_ENGINE} logs -f metrics-service-dispatcher"
echo "  ${CONTAINER_ENGINE} logs -f metrics-service-scheduler"
echo ""
echo "Stop containers:"
echo "  ${CONTAINER_ENGINE} stop metrics-service-web metrics-service-dispatcher metrics-service-scheduler"
echo ""
echo "Access application:"
echo "  http://localhost:8000"
echo ""
