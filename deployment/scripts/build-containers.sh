#!/bin/bash
#
# Build all Metrics Service container images
#
# This script builds the container images for all metrics service components
# using Podman (or Docker if CONTAINER_ENGINE=docker is set).
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
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Metrics Service Container Build${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Container Engine:${NC} ${CONTAINER_ENGINE}"
echo -e "${YELLOW}Registry:${NC} ${IMAGE_REGISTRY}"
echo -e "${YELLOW}Tag:${NC} ${IMAGE_TAG}"
echo -e "${YELLOW}Project Root:${NC} ${PROJECT_ROOT}"
echo ""

# Check if container engine is available
if ! command -v "${CONTAINER_ENGINE}" &> /dev/null; then
    echo -e "${RED}Error: ${CONTAINER_ENGINE} not found${NC}"
    echo "Please install ${CONTAINER_ENGINE} or set CONTAINER_ENGINE=docker"
    exit 1
fi

cd "${PROJECT_ROOT}"

# Build base image first
echo -e "${YELLOW}[1/4] Building base image...${NC}"
${CONTAINER_ENGINE} build \
    -f deployment/containers/Containerfile.base \
    -t "${IMAGE_REGISTRY}/metrics-service-base:${IMAGE_TAG}" \
    .
echo -e "${GREEN}✓ Base image built${NC}"
echo ""

# Build web image
echo -e "${YELLOW}[2/4] Building web image...${NC}"
${CONTAINER_ENGINE} build \
    -f deployment/containers/Containerfile.web \
    -t "${IMAGE_REGISTRY}/metrics-service-web:${IMAGE_TAG}" \
    .
echo -e "${GREEN}✓ Web image built${NC}"
echo ""

# Build dispatcher image
echo -e "${YELLOW}[3/4] Building dispatcher image...${NC}"
${CONTAINER_ENGINE} build \
    -f deployment/containers/Containerfile.dispatcher \
    -t "${IMAGE_REGISTRY}/metrics-service-dispatcher:${IMAGE_TAG}" \
    .
echo -e "${GREEN}✓ Dispatcher image built${NC}"
echo ""

# Build scheduler image
echo -e "${YELLOW}[4/4] Building scheduler image...${NC}"
${CONTAINER_ENGINE} build \
    -f deployment/containers/Containerfile.scheduler \
    -t "${IMAGE_REGISTRY}/metrics-service-scheduler:${IMAGE_TAG}" \
    .
echo -e "${GREEN}✓ Scheduler image built${NC}"
echo ""

# List images
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Build complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Built images:"
${CONTAINER_ENGINE} images | grep metrics-service | grep "${IMAGE_TAG}"
echo ""

echo "To push to a registry:"
echo "  ${CONTAINER_ENGINE} push ${IMAGE_REGISTRY}/metrics-service-web:${IMAGE_TAG}"
echo "  ${CONTAINER_ENGINE} push ${IMAGE_REGISTRY}/metrics-service-dispatcher:${IMAGE_TAG}"
echo "  ${CONTAINER_ENGINE} push ${IMAGE_REGISTRY}/metrics-service-scheduler:${IMAGE_TAG}"
echo ""
echo "To run locally:"
echo "  ./deployment/scripts/run-containers-local.sh"
echo ""
