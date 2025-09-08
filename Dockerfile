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

# Switch back to default user
USER 1001

# Upgrade pip
RUN pip install --upgrade pip

# Copy requirements first for better caching
COPY requirements.txt /app/
COPY pyproject.toml /app/

# Install Python dependencies directly without editable install to avoid permission issues
RUN pip install -r requirements.txt

# Copy the application code
COPY --chown=1001:1001 . /app/

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
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
