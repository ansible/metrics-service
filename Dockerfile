# Dockerfile - Production build with Nginx + TLS
# Uses pre-built Python wheels (binaries) for faster builds
# Includes Nginx for TLS termination and reverse proxy

FROM registry.access.redhat.com/ubi9/python-312:latest

# Set working directory
WORKDIR /app

# Set environment variables for build and runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 


# Install only runtime dependencies (no build tools)
# Use pre-built Python wheels instead of building from source
USER root
RUN dnf update -y && \
    dnf install -y \
        # Production runtime: Nginx for reverse proxy and TLS termination
        nginx \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# Create app directory and set permissions
RUN mkdir -p /app && chown -R 1001:1001 /app

# Copy the application code
COPY --chown=1001:1001 . /app/

# Switch to non-root user for install
USER 1001

# Install Python dependencies using pre-built wheels (binaries)
# Prefer binary packages to avoid compilation during build
RUN pip install --no-cache-dir --prefer-binary --only-binary :all: . || \
    pip install --no-cache-dir --prefer-binary .

# Copy and set up entrypoint script, Nginx config, and certificate generator
USER root
COPY --chown=1001:1001 scripts/docker-entrypoint.sh /usr/local/bin/
COPY --chown=1001:1001 scripts/generate-certs.sh /usr/local/bin/
COPY --chown=1001:1001 scripts/nginx/nginx.conf /etc/nginx/nginx.conf
RUN chmod 555 /usr/local/bin/docker-entrypoint.sh && \
    chmod 555 /usr/local/bin/generate-certs.sh && \
    chmod 644 /etc/nginx/nginx.conf

# Create necessary directories with proper permissions
# Nginx directories need to be writable by user 1001
RUN mkdir -p /etc/nginx/ssl /var/log/nginx /var/lib/nginx && \
    chown -R 1001:1001 /etc/nginx /var/log/nginx /var/lib/nginx && \
    chmod 755 /etc/nginx/ssl /var/log/nginx /var/lib/nginx
USER 1001

# Collect static files into STATIC_ROOT for production serving by Nginx
# This creates /app/staticfiles owned by user 1001
RUN mkdir -p /app/logs /app/staticfiles && \
    python3.12 manage.py collectstatic --noinput --clear

# Make app directory read-only (except logs and staticfiles)
USER root
RUN chmod -R a-w /app && \
    chmod 555 /app && \
    chmod 755 /app/logs /app/staticfiles
USER 1001

# Expose ports (8080 for HTTP, 8443 for HTTPS, 8000 for direct backend access)
# Non-privileged ports allow running as non-root user (1001)
# In Kubernetes, use Service to map 80→8080 and 443→8443
EXPOSE 8080 8443 8000

# Set entrypoint and default command.
# Production runner: Nginx + Gunicorn (web) + Dispatcher + Scheduler
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python3.12", "manage.py", "metrics_service", "run", "--host", "127.0.0.1", "--port", "8000", "--workers", "4"]

LABEL com.redhat.component="ansible-automation-platform-tech-preview-metrics-service-rhel9" \
    name="ansible-automation-platform-tech-preview/metrics-service-rhel9" \
    version="1.0.0" \
    summary="Metrics Service" \
    description="Backend utility for Ansible Automation Platform" \
    cpe="cpe:/a:redhat:metrics_utility:1.0::rhel9" \
    org.opencontainers.image.created="${BUILD_DATE:-$(date -u +'%Y-%m-%dT%H:%M:%SZ')}"
