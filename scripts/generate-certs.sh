#!/bin/bash
# Generate self-signed TLS certificates for development/testing
# In production, mount proper certificates from secrets/configmaps

set -e

CERT_DIR="${CERT_DIR:-/etc/nginx/ssl}"
CERT_FILE="${CERT_DIR}/server.crt"
KEY_FILE="${CERT_DIR}/server.key"

# Check if certificates already exist
if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "✓ TLS certificates already exist at ${CERT_DIR}"
    exit 0
fi

echo "⚠ TLS certificates not found, generating self-signed certificates..."
echo "  (In production, mount proper certificates from secrets)"

# Create certificate directory if it doesn't exist
mkdir -p "$CERT_DIR"

# Generate self-signed certificate (valid for 365 days)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -subj "/C=US/ST=NC/L=Durham/O=Red Hat/OU=Ansible/CN=metrics-service" \
    -addext "subjectAltName=DNS:localhost,DNS:metrics-service,IP:127.0.0.1" \
    2>/dev/null

# Set proper permissions (readable by nginx user 1001)
chmod 644 "$CERT_FILE"
chmod 600 "$KEY_FILE"

echo "✓ Self-signed TLS certificates generated at ${CERT_DIR}"
echo "  Certificate: ${CERT_FILE}"
echo "  Private Key: ${KEY_FILE}"
