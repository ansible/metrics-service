FROM registry.access.redhat.com/ubi9/python-312:latest

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
USER root
RUN dnf update -y && \
    dnf install -y gcc postgresql-devel openldap-devel && \
    dnf clean all

# Create app directory and set permissions
RUN mkdir -p /app && chown -R 1001:1001 /app

# Copy the application code
COPY --chown=1001:1001 . /app/

# Switch back to default user
USER 1001

# Install dependencies
RUN pip install --no-cache-dir -r requirements-build.txt

# Copy and set up entrypoint script
USER root
COPY --chown=1001:1001 scripts/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create necessary directories and files with proper permissions
RUN mkdir -p /app/logs /app/static && \
    chown -R 1001:1001 /app
USER 1001

# Expose port
EXPOSE 8000
# Set entrypoint and default command
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "manage.py", "metrics_service", "run", "--host", "0.0.0.0", "--port", "8000"]

LABEL com.redhat.component="metrics-utility" \
      name="metrics-utility" \
      version="1.0.0" \
      summary="Metrics Utility" \
      description="Backend utility for Ansible Automation Platform" \
      cpe="cpe:/a:redhat:metrics_utility:1.0::rhel9" \
      org.opencontainers.image.created="${BUILD_DATE:-$(date -u +'%Y-%m-%dT%H:%M:%SZ')}"
