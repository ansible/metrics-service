# Metrics Service Deployment - Quick Start

Quick reference for common deployment tasks.

---

## Development (Local)

```bash
# Run all components together (development only)
python manage.py metrics_service run
```

**Access**:
- Web: http://localhost:8000
- API Docs: http://localhost:8000/api/docs/
- Dashboard: http://localhost:8000/dashboard/

---

## Build Container Images

```bash
# Build all images with Podman (default)
./deployment/scripts/build-containers.sh

# Build with Docker
CONTAINER_ENGINE=docker ./deployment/scripts/build-containers.sh

# Build with custom registry/tag
IMAGE_REGISTRY=quay.io/myorg IMAGE_TAG=v1.0.0 ./deployment/scripts/build-containers.sh
```

**Creates**:
- `metrics-service-base:latest`
- `metrics-service-web:latest`
- `metrics-service-dispatcher:latest`
- `metrics-service-scheduler:latest`

---

## Test Locally with Containers

```bash
# Run all three containers locally
./deployment/scripts/run-containers-local.sh

# Check status
podman ps --filter "name=metrics-service-"

# View logs
podman logs -f metrics-service-web
podman logs -f metrics-service-dispatcher
podman logs -f metrics-service-scheduler

# Stop containers
podman stop metrics-service-web metrics-service-dispatcher metrics-service-scheduler
```

---

## Production Deployment (RHEL/Fedora + Podman)

### Initial Setup

```bash
# 1. Run setup script
sudo ./deployment/scripts/setup-production.sh

# 2. Configure environment
sudo vi /etc/metrics-service/environment
# Set: SECRET_KEY, DB_PASSWORD, ALLOWED_HOSTS

# 3. Build or pull images
./deployment/scripts/build-containers.sh
# OR
sudo -u metrics-service podman pull quay.io/ansible/metrics-service-web:latest
sudo -u metrics-service podman pull quay.io/ansible/metrics-service-dispatcher:latest
sudo -u metrics-service podman pull quay.io/ansible/metrics-service-scheduler:latest

# 4. Install systemd units
sudo ./deployment/scripts/install-systemd-services.sh

# 5. Initialize database
sudo -u metrics-service podman run --rm \
    --env-file=/etc/metrics-service/environment \
    --volume=/opt/metrics-service:/opt/app-root/src:Z \
    localhost/metrics-service-web:latest \
    python manage.py migrate

sudo -u metrics-service podman run --rm \
    --env-file=/etc/metrics-service/environment \
    --volume=/opt/metrics-service:/opt/app-root/src:Z \
    localhost/metrics-service-web:latest \
    python manage.py metrics_service init-service-id

sudo -u metrics-service podman run --rm \
    --env-file=/etc/metrics-service/environment \
    --volume=/opt/metrics-service:/opt/app-root/src:Z \
    localhost/metrics-service-web:latest \
    python manage.py metrics_service init-system-tasks

# 6. Start services
sudo systemctl enable metrics-service.target
sudo systemctl start metrics-service.target
```

### Daily Operations

```bash
# Check status
sudo systemctl status metrics-service.target

# View logs
sudo journalctl -u 'container-metrics-service-*' -f

# Restart services
sudo systemctl restart metrics-service.target

# Restart individual component
sudo systemctl restart container-metrics-service-web

# Stop services
sudo systemctl stop metrics-service.target

# Update to new version
sudo -u metrics-service podman pull localhost/metrics-service-web:latest
sudo systemctl restart container-metrics-service-web
```

---

## Environment Variables

### Minimum Required (Production)

```bash
METRICS_SERVICE_SECRET_KEY=<random-secret-key>
METRICS_SERVICE_DB_PASSWORD=<database-password>
METRICS_SERVICE_ALLOWED_HOSTS=your-hostname.com,localhost
```

### Generate Secret Key

```bash
openssl rand -base64 32
```

### Full Configuration Template

```bash
# Django
DJANGO_SETTINGS_MODULE=metrics_service.settings
METRICS_SERVICE_MODE=production
METRICS_SERVICE_SECRET_KEY=<generated-key>
METRICS_SERVICE_ALLOWED_HOSTS=hostname.example.com,localhost
METRICS_SERVICE_DEBUG=false

# Database
METRICS_SERVICE_DB_HOST=localhost
METRICS_SERVICE_DB_PORT=5432
METRICS_SERVICE_DB_NAME=metrics_service
METRICS_SERVICE_DB_USER=metrics_service
METRICS_SERVICE_DB_PASSWORD=<secure-password>

# Logging
METRICS_SERVICE_LOG_LEVEL=INFO

# Features
METRICS_SERVICE_ANONYMIZED_DATA=true
METRICS_SERVICE_METRICS_COLLECTION=false
METRICS_SERVICE_DEVELOPER_MODE_ENABLED=false
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
sudo journalctl -u container-metrics-service-web -n 50

# Check container directly
podman logs metrics-service-web

# Test container manually
sudo -u metrics-service podman run --rm -it \
    --env-file=/etc/metrics-service/environment \
    localhost/metrics-service-web:latest \
    /bin/bash
```

### Database Connection Failed

```bash
# Test database connection
sudo -u metrics-service podman run --rm \
    --env-file=/etc/metrics-service/environment \
    localhost/metrics-service-web:latest \
    python manage.py check --database default

# Check PostgreSQL is running
sudo systemctl status postgresql
```

### Permission Errors

```bash
# Fix ownership
sudo chown -R metrics-service:metrics-service /opt/metrics-service
sudo chown -R metrics-service:metrics-service /var/log/metrics-service

# Fix SELinux labels
sudo restorecon -R /opt/metrics-service
```

### View Health Status

```bash
# Check health (systemd)
systemctl status container-metrics-service-web

# Check health (Podman)
podman inspect --format='{{.State.Health.Status}}' metrics-service-web

# Manual health check
curl http://localhost:8000/api/health/
```

---

## Common Tasks

### Update Application Code

```bash
# 1. Build new images
./deployment/scripts/build-containers.sh

# 2. Restart services
sudo systemctl restart metrics-service.target
```

### Run Management Commands

```bash
# General pattern
sudo -u metrics-service podman run --rm \
    --env-file=/etc/metrics-service/environment \
    --volume=/opt/metrics-service:/opt/app-root/src:Z \
    localhost/metrics-service-web:latest \
    python manage.py <command>

# Examples
# Create superuser
sudo -u metrics-service podman run --rm -it \
    --env-file=/etc/metrics-service/environment \
    --volume=/opt/metrics-service:/opt/app-root/src:Z \
    localhost/metrics-service-web:latest \
    python manage.py createsuperuser

# Django shell
sudo -u metrics-service podman run --rm -it \
    --env-file=/etc/metrics-service/environment \
    --volume=/opt/metrics-service:/opt/app-root/src:Z \
    localhost/metrics-service-web:latest \
    python manage.py shell
```

### Database Migrations

```bash
# Create migrations (if schema changed)
sudo -u metrics-service podman run --rm \
    --env-file=/etc/metrics-service/environment \
    --volume=/opt/metrics-service:/opt/app-root/src:Z \
    localhost/metrics-service-web:latest \
    python manage.py makemigrations

# Apply migrations
sudo -u metrics-service podman run --rm \
    --env-file=/etc/metrics-service/environment \
    --volume=/opt/metrics-service:/opt/app-root/src:Z \
    localhost/metrics-service-web:latest \
    python manage.py migrate
```

### Backup SQLite Database

```bash
# Stop services
sudo systemctl stop metrics-service.target

# Backup
sudo cp /opt/metrics-service/metricsStorage.sqlite \
        /backup/metricsStorage-$(date +%Y%m%d).sqlite

# Restart services
sudo systemctl start metrics-service.target
```

### View Container Resource Usage

```bash
# All containers
podman stats

# Specific container
podman stats metrics-service-web
```

---

## File Locations

### Configuration

- Environment: `/etc/metrics-service/environment`
- systemd units: `/etc/systemd/system/container-metrics-service-*.service`
- uWSGI config: `/opt/app-root/etc/uwsgi.ini` (inside container)

### Data

- SQLite database: `/opt/metrics-service/metricsStorage.sqlite`
- Static files: `/opt/metrics-service/staticfiles/`
- Logs: `/var/log/metrics-service/`

### Runtime

- Container sockets: `/run/metrics-service/`
- PID files: `/run/metrics-service/*.pid`

---

## Port and Network

- **Web service**: Port 8000 (HTTP)
- **PostgreSQL**: Port 5432 (default)
- **Network mode**: `host` (containers use host network)

---

## Getting Help

- Full documentation: `deployment/README.md`
- Implementation details: `DEPLOYMENT_IMPLEMENTATION_SUMMARY.md`
- Development guide: `CLAUDE.md`
