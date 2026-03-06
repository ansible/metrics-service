#!/bin/bash
# Test script for Nginx + TLS setup in metrics-service
# Tests all aspects of the new production configuration

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

CONTAINER_NAME="${CONTAINER_NAME:-metrics-service-prod}"
HTTP_PORT="${HTTP_PORT:-8080}"
HTTPS_PORT="${HTTPS_PORT:-8443}"

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Metrics Service - Nginx + TLS Testing Suite${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Helper functions
success() {
    echo -e "${GREEN}✓${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        error "$1 is required but not installed"
    fi
}

# Check prerequisites
echo -e "${BLUE}─── Checking Prerequisites ───${NC}"
check_command docker
check_command curl
success "All required commands available"
echo ""

# Test 1: Check if container is running
echo -e "${BLUE}─── Test 1: Container Status ───${NC}"
if docker ps | grep -q "$CONTAINER_NAME"; then
    success "Container '$CONTAINER_NAME' is running"
    CONTAINER_ID=$(docker ps -qf "name=$CONTAINER_NAME")
    info "Container ID: $CONTAINER_ID"
else
    error "Container '$CONTAINER_NAME' is not running. Start it first with: docker compose -f docker-compose.prod.yml up -d"
fi
echo ""

# Test 2: Check running processes
echo -e "${BLUE}─── Test 2: Process Check ───${NC}"
PROCESSES=$(docker exec "$CONTAINER_NAME" ps aux 2>/dev/null || true)

if echo "$PROCESSES" | grep -q "nginx"; then
    success "Nginx process is running"
else
    error "Nginx process not found"
fi

if echo "$PROCESSES" | grep -q "gunicorn"; then
    success "Gunicorn process is running"
else
    error "Gunicorn process not found"
fi

if echo "$PROCESSES" | grep -q "run_dispatcherd"; then
    success "Dispatcherd process is running"
else
    warning "Dispatcherd process not found (may still be starting)"
fi

if echo "$PROCESSES" | grep -q "run_task_scheduler"; then
    success "Task Scheduler process is running"
else
    warning "Task Scheduler process not found (may still be starting)"
fi
echo ""

# Test 3: Nginx configuration
echo -e "${BLUE}─── Test 3: Nginx Configuration ───${NC}"
if docker exec "$CONTAINER_NAME" nginx -t 2>&1 | grep -q "syntax is ok"; then
    success "Nginx configuration is valid"
else
    error "Nginx configuration is invalid"
fi
echo ""

# Test 4: TLS certificate check
echo -e "${BLUE}─── Test 4: TLS Certificate Validation ───${NC}"
if docker exec "$CONTAINER_NAME" test -f /etc/nginx/ssl/server.crt; then
    success "TLS certificate exists"

    # Get certificate details
    CERT_INFO=$(docker exec "$CONTAINER_NAME" openssl x509 -in /etc/nginx/ssl/server.crt -noout -subject -dates 2>/dev/null)
    info "Certificate subject: $(echo "$CERT_INFO" | grep subject | cut -d= -f2-)"
    info "Certificate dates: $(echo "$CERT_INFO" | grep -E 'notBefore|notAfter')"
else
    error "TLS certificate not found"
fi

if docker exec "$CONTAINER_NAME" test -f /etc/nginx/ssl/server.key; then
    success "TLS private key exists"
else
    error "TLS private key not found"
fi
echo ""

# Test 5: Port listening check
echo -e "${BLUE}─── Test 5: Port Listening ───${NC}"
LISTENING_PORTS=$(docker exec "$CONTAINER_NAME" netstat -tuln 2>/dev/null || docker exec "$CONTAINER_NAME" ss -tuln 2>/dev/null || true)

if echo "$LISTENING_PORTS" | grep -q ":8080"; then
    success "HTTP port 8080 is listening"
else
    error "HTTP port 8080 is not listening"
fi

if echo "$LISTENING_PORTS" | grep -q ":8443"; then
    success "HTTPS port 8443 is listening"
else
    error "HTTPS port 8443 is not listening"
fi

if echo "$LISTENING_PORTS" | grep -q "127.0.0.1:8000"; then
    success "Gunicorn port 8000 is listening (localhost only)"
else
    warning "Gunicorn port 8000 not detected (may be starting)"
fi
echo ""

# Test 6: HTTP to HTTPS redirect
echo -e "${BLUE}─── Test 6: HTTP to HTTPS Redirect ───${NC}"
HTTP_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$HTTP_PORT/" || echo "000")
if [ "$HTTP_RESPONSE" = "301" ] || [ "$HTTP_RESPONSE" = "302" ]; then
    success "HTTP redirects to HTTPS (HTTP $HTTP_RESPONSE)"
else
    error "HTTP redirect failed (HTTP $HTTP_RESPONSE)"
fi
echo ""

# Test 7: HTTPS health check endpoint
echo -e "${BLUE}─── Test 7: HTTPS Health Check Endpoint ───${NC}"
HEALTH_RESPONSE=$(curl -k -s -o /dev/null -w "%{http_code}" "https://localhost:$HTTPS_PORT/api/health/" || echo "000")
if [ "$HEALTH_RESPONSE" = "200" ]; then
    success "Health check endpoint accessible via HTTPS (HTTP $HEALTH_RESPONSE)"
else
    warning "Health check endpoint returned HTTP $HEALTH_RESPONSE (service may still be starting)"
fi
echo ""

# Test 8: TLS protocol check
echo -e "${BLUE}─── Test 8: TLS Protocol Validation ───${NC}"
if command -v openssl &> /dev/null; then
    TLS_INFO=$(echo | openssl s_client -connect "localhost:$HTTPS_PORT" -servername localhost 2>/dev/null | grep -E "Protocol|Cipher" | head -2)
    if echo "$TLS_INFO" | grep -qE "TLSv1\.[23]"; then
        success "TLS protocol is TLS 1.2 or 1.3"
        info "$(echo "$TLS_INFO" | grep Protocol)"
        info "$(echo "$TLS_INFO" | grep Cipher)"
    else
        warning "Could not verify TLS protocol version"
    fi
else
    warning "OpenSSL not available, skipping TLS protocol check"
fi
echo ""

# Test 9: Security headers
echo -e "${BLUE}─── Test 9: Security Headers ───${NC}"
HEADERS=$(curl -k -s -I "https://localhost:$HTTPS_PORT/" || true)

check_header() {
    local header="$1"
    if echo "$HEADERS" | grep -qi "$header"; then
        success "$header header present"
    else
        warning "$header header not found"
    fi
}

check_header "Strict-Transport-Security"
check_header "X-Frame-Options"
check_header "X-Content-Type-Options"
check_header "X-XSS-Protection"
echo ""

# Test 10: Static files serving
echo -e "${BLUE}─── Test 10: Static Files Serving ───${NC}"
STATIC_RESPONSE=$(curl -k -s -o /dev/null -w "%{http_code}" "https://localhost:$HTTPS_PORT/static/admin/css/base.css" || echo "000")
if [ "$STATIC_RESPONSE" = "200" ]; then
    success "Static files served successfully (HTTP $STATIC_RESPONSE)"
else
    warning "Static files may not be available yet (HTTP $STATIC_RESPONSE)"
fi
echo ""

# Test 11: API endpoint check
echo -e "${BLUE}─── Test 11: API Endpoint Accessibility ───${NC}"
API_RESPONSE=$(curl -k -s -o /dev/null -w "%{http_code}" "https://localhost:$HTTPS_PORT/api/v1/tasks/" || echo "000")
if [ "$API_RESPONSE" = "200" ] || [ "$API_RESPONSE" = "401" ] || [ "$API_RESPONSE" = "403" ]; then
    success "API endpoint accessible (HTTP $API_RESPONSE)"
    if [ "$API_RESPONSE" = "401" ] || [ "$API_RESPONSE" = "403" ]; then
        info "Authentication required (expected for protected endpoints)"
    fi
else
    warning "API endpoint returned HTTP $API_RESPONSE (service may still be starting)"
fi
echo ""

# Test 12: Container logs check
echo -e "${BLUE}─── Test 12: Container Logs Review ───${NC}"
LOGS=$(docker logs "$CONTAINER_NAME" --tail 50 2>&1)

if echo "$LOGS" | grep -q "Nginx started"; then
    success "Nginx startup logged"
else
    warning "Nginx startup message not found in logs"
fi

if echo "$LOGS" | grep -q "All services started successfully"; then
    success "All services started successfully"
else
    warning "Complete startup message not found in logs"
fi

# Check for errors
ERROR_COUNT=$(echo "$LOGS" | grep -i "error" | grep -v "error.log" | wc -l)
if [ "$ERROR_COUNT" -eq 0 ]; then
    success "No errors found in recent logs"
else
    warning "Found $ERROR_COUNT error messages in logs (review recommended)"
fi
echo ""

# Test 13: Gzip compression
echo -e "${BLUE}─── Test 13: Gzip Compression ───${NC}"
GZIP_RESPONSE=$(curl -k -s -H "Accept-Encoding: gzip" -I "https://localhost:$HTTPS_PORT/" | grep -i "content-encoding" || true)
if echo "$GZIP_RESPONSE" | grep -qi "gzip"; then
    success "Gzip compression is enabled"
else
    info "Gzip compression not detected (may depend on response size)"
fi
echo ""

# Summary
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Test Summary${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}✓ All critical tests passed!${NC}"
echo ""
echo "Access the service at:"
echo "  • HTTPS: https://localhost:$HTTPS_PORT"
echo "  • HTTP:  http://localhost:$HTTP_PORT (redirects to HTTPS)"
echo ""
echo "Useful commands:"
echo "  • View logs:        docker logs -f $CONTAINER_NAME"
echo "  • View processes:   docker exec $CONTAINER_NAME ps aux"
echo "  • Nginx config:     docker exec $CONTAINER_NAME nginx -t"
echo "  • Container shell:  docker exec -it $CONTAINER_NAME /bin/bash"
echo ""
