# Metrics Service Deployment Guide

This directory contains all deployment configurations for the Metrics Service in production environments.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Deployment Options](#deployment-options)
- [Container Images](#container-images)
- [Systemd with Podman (RHEL/Fedora)](#systemd-with-podman)
- [OpenShift Deployment](#openshift-deployment)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

The Metrics Service consists of three independent components:

```
┌─────────────────────────────────────────────────────────────┐
│                     Metrics Service                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │              │  │              │  │              │      │
│  │  Web/API     │  │  Dispatcher  │  │  Scheduler   │      │
│  │  (uWSGI)     │  │ (Dispatcherd)│  │(APScheduler) │      │
│  │              │  │              │  │              │      │
│  │  Port: 8000  │  │  Background  │  │   Cron       │      │
│  │              │  │  Task Worker │  │   Manager    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                 │                  │               │
│         └─────────────────┴──────────────────┘               │
│                          │                                   │
│              ┌───────────┴───────────┐                       │
│              │                       │                       │
│         PostgreSQL           SQLite (Metrics)                │
│       (Main Database)       (metricsStorage.sqlite)          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Components

1. **Web/API Service** (`metrics-service-web`)
   - Django application served via uWSGI
   - REST API endpoints
   - Web dashboard
   - Port: 8000

2. **Dispatcher Service** (`metrics-service-dispatcher`)
   - Background task execution using dispatcherd
   - Multi-worker task processing
   - Database-driven task queue

3. **Scheduler Service** (`metrics-service-scheduler`)
   - APScheduler for cron-based recurring tasks
   - System task initialization
   - Scheduled metrics collection

### Shared Resources

- **PostgreSQL Database**: Main application database (users, organizations, tasks)
- **SQLite Database**: Metrics storage (`metricsStorage.sqlite`) - shared via volume
- **Logs**: Separate logs per component

---

## Deployment Options

### Development (Local)

Use the all-in-one Django management command:

```bash
# Run all components in one process (development only)
python manage.py metrics_service run

# This starts:
# - Django runserver (port 8000)
# - Dispatcherd (4 workers)
# - APScheduler (cron tasks)
```

**⚠️ Not recommended for production!**

### Production Options

1. **Systemd with Podman** (Recommended for RHEL/Fedora servers)
   - Each component in its own container
   - Systemd manages container lifecycle
   - Easy integration with existing infrastructure

2. **OpenShift/Kubernetes** (Recommended for container platforms)
   - Deployed via custom operator
   - Horizontal scaling for web component
   - High availability configuration

---

## Container Images

### Building Images

Build all images:

```bash
# Using Podman (default)
./deployment/scripts/build-containers.sh

# Using Docker
CONTAINER_ENGINE=docker ./deployment/scripts/build-containers.sh

# Build with custom tag and registry
IMAGE_REGISTRY=quay.io/myorg IMAGE_TAG=v1.2.3 ./deployment/scripts/build-containers.sh
```

This creates four images:

- `metrics-service-base:latest` - Base image with dependencies and code
- `metrics-service-web:latest` - Web/API server
- `metrics-service-dispatcher:latest` - Task dispatcher
- `metrics-service-scheduler:latest` - Task scheduler

### Image Structure

**Base Image** (`Containerfile.base`):
- UBI9 Python 3.12
- All Python dependencies
- Application code
- Shared by all service images

**Service Images**:
- Built FROM base image
- Service-specific configuration
- Minimal additional layers

### Testing Locally

Run all containers locally for testing:

```bash
./deployment/scripts/run-containers-local.sh
```

Access the service:
- Web: http://localhost:8000
- API Docs: http://localhost:8000/api/docs/
- Dashboard: http://localhost:8000/dashboard/

View logs:
```bash
podman logs -f metrics-service-web
podman logs -f metrics-service-dispatcher
podman logs -f metrics-service-scheduler
```

Stop containers:
```bash
podman stop metrics-service-web metrics-service-dispatcher metrics-service-scheduler
```

---

## Systemd with Podman

Deploy on RHEL/Fedora servers using Podman containers managed by systemd.

### Prerequisites

- RHEL 8/9, Fedora, or compatible Linux distribution
- Podman installed
- PostgreSQL database (local or remote)
- Systemd (already present on RHEL/Fedora)

### Installation Steps

#### 1. Create System User

```bash
sudo useradd -r -s /bin/false -d /opt/metrics-service metrics-service
```

#### 2. Create Directories

```bash
sudo mkdir -p /opt/metrics-service
sudo mkdir -p /var/log/metrics-service
sudo mkdir -p /etc/metrics-service
sudo chown metrics-service:metrics-service /opt/metrics-service /var/log/metrics-service
```

#### 3. Build or Pull Images

```bash
# Option A: Build locally
cd /path/to/source
./deployment/scripts/build-containers.sh

# Option B: Pull from registry
sudo -u metrics-service podman pull quay.io/ansible/metrics-service-web:latest
sudo -u metrics-service podman pull quay.io/ansible/metrics-service-dispatcher:latest
sudo -u metrics-service podman pull quay.io/ansible/metrics-service-scheduler:latest
```

#### 4. Create Environment File

```bash
sudo tee /etc/metrics-service/environment <<EOF
# Django Configuration
DJANGO_SETTINGS_MODULE=metrics_service.settings
METRICS_SERVICE_MODE=production
METRICS_SERVICE_SECRET_KEY=$(openssl rand -base64 32)
METRICS_SERVICE_ALLOWED_HOSTS=your-hostname.example.com,localhost

# Database Configuration
METRICS_SERVICE_DB_HOST=localhost
METRICS_SERVICE_DB_PORT=5432
METRICS_SERVICE_DB_NAME=metrics_service
METRICS_SERVICE_DB_USER=metrics_service
METRICS_SERVICE_DB_PASSWORD=your-secure-password

# Logging
METRICS_SERVICE_LOG_LEVEL=INFO

# Feature Flags
METRICS_SERVICE_ANONYMIZED_DATA=true
METRICS_SERVICE_METRICS_COLLECTION=false
METRICS_SERVICE_DEVELOPER_MODE_ENABLED=false
EOF

sudo chmod 640 /etc/metrics-service/environment
sudo chown root:metrics-service /etc/metrics-service/environment
```

#### 5. Install Systemd Units

```bash
sudo cp deployment/systemd/container-*.service /etc/systemd/system/
sudo cp deployment/systemd/metrics-service.target /etc/systemd/system/
sudo systemctl daemon-reload
```

#### 6. Initialize Database

```bash
# Run migrations and setup (one-time)
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

# Create admin user
sudo -u metrics-service podman run --rm -it \
    --env-file=/etc/metrics-service/environment \
    --volume=/opt/metrics-service:/opt/app-root/src:Z \
    localhost/metrics-service-web:latest \
    python manage.py createsuperuser
```

#### 7. Start Services

```bash
# Enable services to start on boot
sudo systemctl enable metrics-service.target

# Start all services
sudo systemctl start metrics-service.target

# Check status
sudo systemctl status metrics-service.target
sudo systemctl status container-metrics-service-web
sudo systemctl status container-metrics-service-dispatcher
sudo systemctl status container-metrics-service-scheduler
```

### Managing Services

```bash
# Start/Stop/Restart all components
sudo systemctl start metrics-service.target
sudo systemctl stop metrics-service.target
sudo systemctl restart metrics-service.target

# Start/Stop individual components
sudo systemctl start container-metrics-service-web
sudo systemctl start container-metrics-service-dispatcher
sudo systemctl start container-metrics-service-scheduler

# View logs
sudo journalctl -u container-metrics-service-web -f
sudo journalctl -u container-metrics-service-dispatcher -f
sudo journalctl -u container-metrics-service-scheduler -f

# View all metrics-service logs
sudo journalctl -u 'container-metrics-service-*' -f
```

### Updating Containers

```bash
# Pull new images
sudo -u metrics-service podman pull localhost/metrics-service-web:latest
sudo -u metrics-service podman pull localhost/metrics-service-dispatcher:latest
sudo -u metrics-service podman pull localhost/metrics-service-scheduler:latest

# Restart services (systemd will use new images)
sudo systemctl restart metrics-service.target
```

---

## OpenShift Deployment

The Metrics Service is deployed on OpenShift using a custom operator. The operator manages:

- Pod deployments for all three components
- ConfigMaps and Secrets
- Services and Routes
- Persistent storage for SQLite database
- Auto-scaling for web component

### Prerequisites

- OpenShift 4.x cluster
- Metrics Service Operator installed
- PostgreSQL database provisioned

### Deployment via Operator

The operator handles all deployment details. Typically you'll create a Custom Resource:

```yaml
apiVersion: metrics.ansible.com/v1
kind: MetricsService
metadata:
  name: metrics-service-instance
  namespace: metrics-service
spec:
  replicas:
    web: 2
    dispatcher: 1
    scheduler: 1

  database:
    secretRef: metrics-service-db

  secretKey:
    secretRef: metrics-service-secrets

  storage:
    size: 10Gi
    storageClass: nfs-storage
```

Consult your operator documentation for specific configuration options.

---

## Environment Variables

### Required Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `METRICS_SERVICE_SECRET_KEY` | Django secret key (must be unique) | - | **Yes** (Production) |
| `METRICS_SERVICE_DB_PASSWORD` | Database password | - | **Yes** (Production) |
| `METRICS_SERVICE_ALLOWED_HOSTS` | Comma-separated hostnames | `localhost` | **Yes** (Production) |

### Database Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `METRICS_SERVICE_DB_HOST` | PostgreSQL host | `localhost` |
| `METRICS_SERVICE_DB_PORT` | PostgreSQL port | `5432` |
| `METRICS_SERVICE_DB_NAME` | Database name | `metrics_service` |
| `METRICS_SERVICE_DB_USER` | Database user | `metrics_service` |

### Optional Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `METRICS_SERVICE_MODE` | Environment mode (`development`/`production`) | `development` |
| `METRICS_SERVICE_LOG_LEVEL` | Logging level | `INFO` |
| `METRICS_SERVICE_DEBUG` | Enable debug mode | `false` |
| `METRICS_SERVICE_ANONYMIZED_DATA` | Enable anonymized data collection | `true` |
| `METRICS_SERVICE_METRICS_COLLECTION` | Enable metrics collection | `false` |
| `METRICS_SERVICE_DEVELOPER_MODE_ENABLED` | Enable developer features | `false` |

---

## Troubleshooting

### Container Won't Start

```bash
# Check container logs
podman logs metrics-service-web

# Check systemd status
systemctl status container-metrics-service-web

# Check systemd journal
journalctl -u container-metrics-service-web -n 50
```

### Database Connection Issues

```bash
# Test database connectivity from container
podman run --rm \
    --env-file=/etc/metrics-service/environment \
    localhost/metrics-service-web:latest \
    python manage.py check --database default

# Check PostgreSQL is running and accessible
psql -h localhost -U metrics_service -d metrics_service
```

### Permission Issues

```bash
# Check file ownership
ls -la /opt/metrics-service/
ls -la /var/log/metrics-service/

# Fix permissions
sudo chown -R metrics-service:metrics-service /opt/metrics-service
sudo chown -R metrics-service:metrics-service /var/log/metrics-service
```

### Container Health Checks Failing

```bash
# Check health status
podman healthcheck run metrics-service-web

# Inspect container
podman inspect metrics-service-web
```

### SQLite Database Lock Issues

The SQLite database (`metricsStorage.sqlite`) is shared between all components. Ensure:

1. All containers mount the same volume
2. Volume has proper permissions
3. SQLite WAL mode is enabled (automatic)

```bash
# Check SQLite database
sqlite3 /opt/metrics-service/metricsStorage.sqlite "PRAGMA journal_mode;"
# Should return: wal
```

---

## Security Considerations

### Secrets Management

- **Never** commit secrets to version control
- Use environment files with restricted permissions (640)
- Rotate `METRICS_SERVICE_SECRET_KEY` periodically
- Use strong database passwords

### Container Security

All containers run as non-root user (UID 1001):

```bash
# Verify user in container
podman exec metrics-service-web id
# Should show: uid=1001 gid=0(root)
```

### Network Security

- Use firewall rules to restrict access to port 8000
- Consider using a reverse proxy (nginx, HAProxy)
- Enable TLS/SSL termination at the reverse proxy
- On OpenShift, use Routes with TLS edge termination

---

## Monitoring

### Container Health

```bash
# Check all containers
podman ps --filter "name=metrics-service-"

# Check health status
podman inspect --format='{{.State.Health.Status}}' metrics-service-web
```

### Application Metrics

Access metrics endpoint:
```
http://localhost:8000/metrics/
```

### Logs

```bash
# Systemd deployment
journalctl -u 'container-metrics-service-*' -f

# Direct container logs
podman logs -f metrics-service-web
```

---

## Performance Tuning

### uWSGI Workers (Web Component)

Edit `deployment/uwsgi/metrics-service-http.ini`:

```ini
processes = 4  # Adjust based on CPU cores
threads = 2    # Adjust based on workload
```

### Dispatcher Workers

Modify systemd unit or container command:

```bash
--workers=8  # Increase for high task volume
```

### Database Connection Pooling

Configure in Django settings:

```python
DATABASES = {
    'default': {
        'CONN_MAX_AGE': 600,  # Connection lifetime in seconds
    }
}
```

---

## Backup and Recovery

### Database Backup

```bash
# PostgreSQL backup
pg_dump -h localhost -U metrics_service metrics_service > backup.sql

# SQLite backup
cp /opt/metrics-service/metricsStorage.sqlite /backup/metrics-$(date +%Y%m%d).sqlite
```

### Container Volumes

```bash
# Backup Podman volume
podman volume export metrics-service-sqlite -o metrics-sqlite-backup.tar
```

---

## Additional Resources

- [Django Deployment Checklist](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/)
- [uWSGI Documentation](https://uwsgi-docs.readthedocs.io/)
- [Podman Documentation](https://docs.podman.io/)
- [systemd Documentation](https://www.freedesktop.org/software/systemd/man/)
