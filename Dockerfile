FROM registry.access.redhat.com/ubi9/python-311:latest

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

# Install uv for fast dependency management
RUN pip install uv

# Create app directory and set permissions
RUN mkdir -p /app && chown -R 1001:1001 /app

# Copy the application code
COPY --chown=1001:1001 . /app/

# Switch back to default user
USER 1001

# Set uv to install globally available packages in system Python
ENV UV_SYSTEM_PYTHON=1

# Install dependencies using uv
RUN uv sync --frozen --no-dev

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
CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
