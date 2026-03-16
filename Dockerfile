# Dockerfile - Production build with Nginx + TLS
# Uses pre-built Python wheels (binaries) for faster builds
# Includes Nginx for TLS termination and reverse proxy

FROM registry.access.redhat.com/ubi9/python-312:latest

# Set environment variables for build and runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/var/lib/ansible-automation-platform/metrics \
    METRICS_STATIC_ROOT=/var/lib/ansible-automation-platform/metrics/static \
    METRICS_MEDIA_ROOT=/var/lib/ansible-automation-platform/metrics/media

USER root

# Create metrics user/group matching production container (UID 1001)
RUN groupadd -r metrics && \
    useradd -r -u 1001 -g metrics -d /var/lib/ansible-automation-platform/metrics -s /bin/bash metrics

# Install only runtime dependencies (no build tools)
# Use pre-built Python wheels instead of building from source
RUN dnf update -y && \
    dnf install -y \
        # Production runtime: Nginx for reverse proxy and TLS termination
        nginx \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# Create directory structure matching production container
RUN mkdir -p \
        /var/lib/ansible-automation-platform/metrics/static \
        /var/lib/ansible-automation-platform/metrics/media \
        /var/lib/ansible-automation-platform/metrics/logs \
        /etc/ansible-automation-platform/metrics && \
    mkdir -m 770 -p /run/ansible-automation-platform/metrics && \
    chown -R metrics:metrics /var/lib/ansible-automation-platform/metrics && \
    chown metrics:root /var/lib/ansible-automation-platform/metrics && \
    chown metrics:root /var/lib/ansible-automation-platform/metrics/media && \
    chown metrics:root /var/lib/ansible-automation-platform/metrics/logs && \
    chmod 775 /var/lib/ansible-automation-platform/metrics && \
    chmod 775 /var/lib/ansible-automation-platform/metrics/media && \
    chmod 775 /var/lib/ansible-automation-platform/metrics/logs && \
    chown metrics:root /etc/ansible-automation-platform/metrics

WORKDIR /var/lib/ansible-automation-platform/metrics

# Copy the application code
COPY --chown=metrics:metrics . /var/lib/ansible-automation-platform/metrics/

# Red Hat Certification Requirement: Copy licenses directory to container root
# This satisfies the HasLicense preflight check
COPY --chown=root:root licenses /licenses

USER metrics

# Install Python dependencies using pre-built wheels (binaries)
# Prefer binary packages to avoid compilation during build
RUN pip install --no-cache-dir --prefer-binary --only-binary :all: . || \
    pip install --no-cache-dir --prefer-binary .

# Copy and set up entrypoint scripts, Nginx config, and certificate generator
USER root
COPY --chown=metrics:metrics scripts/docker-entrypoint.sh /usr/local/bin/
COPY --chown=metrics:metrics scripts/generate-certs.sh /usr/local/bin/
COPY --chown=metrics:metrics scripts/entrypoint-init.sh /usr/local/bin/
COPY --chown=metrics:metrics scripts/entrypoint-web.sh /usr/local/bin/
COPY --chown=metrics:metrics scripts/entrypoint-dispatcherd.sh /usr/local/bin/
COPY --chown=metrics:metrics scripts/entrypoint-scheduler.sh /usr/local/bin/
COPY --chown=metrics:metrics scripts/nginx/nginx.conf /etc/nginx/nginx.conf
RUN chmod 555 /usr/local/bin/docker-entrypoint.sh && \
    chmod 555 /usr/local/bin/generate-certs.sh && \
    chmod 555 /usr/local/bin/entrypoint-init.sh && \
    chmod 555 /usr/local/bin/entrypoint-web.sh && \
    chmod 555 /usr/local/bin/entrypoint-dispatcherd.sh && \
    chmod 555 /usr/local/bin/entrypoint-scheduler.sh && \
    chmod 644 /etc/nginx/nginx.conf

# Nginx directories need to be writable by the metrics user
RUN mkdir -p /etc/nginx/ssl /var/log/nginx /var/lib/nginx && \
    chown -R metrics:metrics /etc/nginx /var/log/nginx /var/lib/nginx && \
    chmod 755 /etc/nginx/ssl /var/log/nginx /var/lib/nginx

USER metrics

# Collect static files into METRICS_STATIC_ROOT for production serving by Nginx
RUN python3.12 manage.py collectstatic --noinput --clear

# Make app directory read-only (except logs, static, media)
USER root
RUN chmod -R a-w /var/lib/ansible-automation-platform/metrics && \
    chmod 555 /var/lib/ansible-automation-platform/metrics && \
    chmod 755 /var/lib/ansible-automation-platform/metrics/logs \
              /var/lib/ansible-automation-platform/metrics/static \
              /var/lib/ansible-automation-platform/metrics/media
USER metrics

# Expose ports (8080 for HTTP, 8443 for HTTPS, 8000 for direct backend access)
# Non-privileged ports allow running as non-root user (1001)
# In Kubernetes, use Service to map 80→8080 and 443→8443
EXPOSE 8080 8443 8000

# Default: all-in-one mode — entrypoint starts Nginx (8080/8443) then runs CMD (app on 127.0.0.1:8000).
# docker-compose can override with entrypoint: ["/usr/local/bin/entrypoint-web.sh"] etc. for split services.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
# App binds to 127.0.0.1:8000; Nginx proxies external 8080/8443 to it.
CMD ["python3.12", "manage.py", "metrics_service", "run", "--host", "127.0.0.1", "--port", "8000", "--workers", "4"]

LABEL com.redhat.component="ansible-automation-platform-tech-preview-metrics-service-rhel9" \
    name="ansible-automation-platform-tech-preview/metrics-service-rhel9" \
    version="1.0.0" \
    summary="Metrics Service" \
    description="Backend utility for Ansible Automation Platform" \
    cpe="cpe:/a:redhat:metrics_utility:1.0::rhel9" \
    org.opencontainers.image.created="${BUILD_DATE:-$(date -u +'%Y-%m-%dT%H:%M:%SZ')}"
