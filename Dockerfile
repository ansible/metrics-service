# Dockerfile - Konflux/AppStudio compliant build
# Builds Python dependencies; source-only for crypto/psycopg, binaries allowed for Django/pandas.
# Konflux: if using RHEL registration, configure Environment secrets for /activation-key/org and /entitlement.

FROM registry.access.redhat.com/ubi9/python-312:latest

# Set working directory
WORKDIR /app

# Set environment variables for build and runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 


# Install system dependencies required for building Python packages from source
# These include compilers and development headers for:
# - cryptography (requires Rust, OpenSSL headers)
# - psycopg/psycopg2 (requires PostgreSQL headers)
# - python-ldap (requires OpenLDAP headers)
# - cffi (requires libffi headers)
USER root
RUN dnf update -y && \
    dnf install -y \
        # C compiler and build tools
        gcc \
        gcc-c++ \
        make \
        # Python development headers
        python3.12-devel \
        # PostgreSQL development headers (for psycopg/psycopg2)
        postgresql-devel \
        libpq-devel \
        # OpenLDAP development headers (for python-ldap)
        openldap-devel \
        # OpenSSL development headers (for cryptography)
        openssl-devel \
        # libffi development headers (for cffi)
        libffi-devel \
        # Rust toolchain (required for cryptography package)
        rust \
        cargo \
        # Additional build dependencies
        redhat-rpm-config \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# Create app directory and set permissions
RUN mkdir -p /app && chown -R 1001:1001 /app

# Copy the application code
COPY --chown=1001:1001 . /app/

# Red Hat Certification Requirement: Copy licenses directory to container root
# This satisfies the HasLicense preflight check
COPY --chown=root:root licenses /licenses

# Switch to non-root user for build
USER 1001

# Set up cachi2/hermeto environment for hermetic builds (if available).
# Cachi2 provides cachi2.env; Hermeto provides deps/pip and uses PIP_FIND_LINKS + PIP_NO_INDEX.
# requirements-build.txt has no -e .; we always install deps then "pip install .".
# Hermetic path: rewrite any django-ansible-base git+https line to file:// using captured commit
# so the same Dockerfile works when requirements-build.txt is updated to a new revision.
RUN if [ -f /cachi2/cachi2.env ]; then \
        set -a && . /cachi2/cachi2.env && set +a && \
        pip install --no-cache-dir -r requirements-build.txt && pip install --no-cache-dir . ; \
    elif [ -d /cachi2/deps/pip ]; then \
        export PIP_NO_INDEX=1 PIP_FIND_LINKS=/cachi2/deps/pip && \
        pip install --no-cache-dir wheel setuptools && \
        sed -e '/^--no-binary/d' -e 's|django-ansible-base @ git+https://github.com/ansible/django-ansible-base@\([a-f0-9]\+\)|django-ansible-base @ file:///cachi2/deps/pip/django-ansible-base-gitcommit-\1.tar.gz|' requirements-build.txt > /tmp/requirements-hermetic.txt && \
        (grep -q 'django-ansible-base @ git+https' /tmp/requirements-hermetic.txt && { echo "ERROR: django-ansible-base git URL was not rewritten for hermetic build; prefetch may use a different rev than requirements-build.txt" >&2; exit 1; }) || true && \
        pip install --no-cache-dir --no-build-isolation -r /tmp/requirements-hermetic.txt && pip install --no-cache-dir --no-deps --no-build-isolation . ; \
    else \
        pip install --no-cache-dir -r requirements-build.txt && pip install --no-cache-dir . ; \
    fi

# Copy and set up entrypoint script (read+execute only, no write)
USER root
COPY --chown=1001:1001 scripts/docker-entrypoint.sh /usr/local/bin/
RUN chmod 555 /usr/local/bin/docker-entrypoint.sh

# Create necessary directories and files with proper permissions
# STATIC_ROOT in Django is staticfiles; collectstatic must write there
RUN mkdir -p /app/logs /app/staticfiles && \
    chown -R 1001:1001 /app && \
    chmod -R a-w /app && \
    chmod 555 /app && \
    chmod 755 /app/logs /app/staticfiles
USER 1001
RUN python manage.py collectstatic --noinput --clear

# Expose port
EXPOSE 8000

# Set entrypoint and default command
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "manage.py", "metrics_service", "run", "--host", "0.0.0.0", "--port", "8000"]

LABEL com.redhat.component="ansible-automation-platform-tech-preview-metrics-service-rhel9" \
    name="ansible-automation-platform-tech-preview/metrics-service-rhel9" \
    version="1.0.0" \
    summary="Metrics Service" \
    description="Backend utility for Ansible Automation Platform" \
    cpe="cpe:/a:redhat:metrics_utility:1.0::rhel9" \
    org.opencontainers.image.created="${BUILD_DATE:-$(date -u +'%Y-%m-%dT%H:%M:%SZ')}"
