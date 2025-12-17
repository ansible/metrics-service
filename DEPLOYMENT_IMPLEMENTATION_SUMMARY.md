# Production Deployment Implementation Summary

## Overview

Successfully implemented a complete production deployment strategy for Metrics Service that separates the three application components into independent containers, replacing the single `python manage.py metrics_service run` development command with a production-ready containerized architecture.

---

## What Was Implemented

### 1. Container Architecture ✅

**Separation of Concerns**: Split the monolithic development process into three independent containerized services:

1. **Web/API Service** - Django application served via uWSGI
2. **Dispatcher Service** - Background task worker (dispatcherd)
3. **Scheduler Service** - Cron-based task scheduler (APScheduler)

**Base Image Strategy**:
- Single base image with all dependencies and application code
- Three lightweight service images built from base
- Minimal layer duplication, optimal caching

### 2. Container Images ✅

**Created Files**:
- `deployment/containers/Containerfile.base` - Base image (UBI9 Python 3.12, all dependencies)
- `deployment/containers/Containerfile.web` - Web service with uWSGI
- `deployment/containers/Containerfile.dispatcher` - Task dispatcher service
- `deployment/containers/Containerfile.scheduler` - Task scheduler service

**Features**:
- Runs as non-root user (UID 1001)
- Health checks for each component
- Optimized build caching
- Production-ready security settings

### 3. Systemd Integration (Podman Containers) ✅

**Created systemd units for RHEL/Fedora deployment**:

- `deployment/systemd/container-metrics-service-web.service`
- `deployment/systemd/container-metrics-service-dispatcher.service`
- `deployment/systemd/container-metrics-service-scheduler.service`
- `deployment/systemd/metrics-service.target`

**Features**:
- Automatic container restart on failure
- Proper shutdown handling (SIGTERM/SIGQUIT)
- Environment file support (`/etc/metrics-service/environment`)
- Volume mounting for SQLite database and logs
- systemd journal integration for logs
- Auto-update labels for container image pulls

### 4. uWSGI Configuration ✅

**Created production-ready uWSGI configurations**:

- `deployment/uwsgi/metrics-service.ini` - Socket mode (for nginx reverse proxy)
- `deployment/uwsgi/metrics-service-http.ini` - HTTP mode (standalone)

**Features**:
- Master process with 4 workers, 2 threads each
- Dynamic process scaling (cheaper subsystem)
- Request limits and worker respawning
- Memory limits and harakiri timeout
- Stats server for monitoring
- Graceful reload support

### 5. Build and Deployment Scripts ✅

**Created automation scripts**:

- `deployment/scripts/build-containers.sh` - Build all container images
- `deployment/scripts/run-containers-local.sh` - Run containers locally for testing
- `deployment/scripts/install-systemd-services.sh` - Install systemd units
- `deployment/scripts/setup-production.sh` - Complete production setup

**Features**:
- Support for both Podman and Docker
- Configurable registry and tags
- Error handling and validation
- Color-coded output
- Step-by-step guidance

### 6. Documentation ✅

**Created comprehensive documentation**:

- `deployment/README.md` - Complete deployment guide (300+ lines)
  - Architecture overview with diagrams
  - Development vs production comparison
  - Container build instructions
  - Systemd deployment guide
  - OpenShift notes (operator-managed)
  - Environment variables reference
  - Troubleshooting guide
  - Security considerations
  - Monitoring and performance tuning

**Updated existing documentation**:

- `CLAUDE.md` - Added production deployment section
  - Container build commands
  - Deployment architecture patterns
  - Key differences between dev and prod

---

## Architecture Comparison

### Before (Development)

```
python manage.py metrics_service run
│
├─ Django runserver (thread)
├─ Dispatcherd subprocess
└─ APScheduler (thread)
```

**Issues**:
- Not suitable for production
- Single point of failure
- Limited resource management
- No independent scaling
- Development server (runserver) not production-ready

### After (Production)

```
systemd (or OpenShift operator)
│
├─ Container: metrics-service-web
│  └─ uWSGI (production WSGI server)
│     └─ Django application
│
├─ Container: metrics-service-dispatcher
│  └─ dispatcherd (background tasks)
│
└─ Container: metrics-service-scheduler
   └─ APScheduler (cron tasks)
```

**Benefits**:
- Production-grade WSGI server (uWSGI)
- Independent scaling per component
- Isolated failures (one component failure doesn't affect others)
- Better resource management (CPU/memory limits per container)
- Standard container deployment (works with Podman, OpenShift, Kubernetes)
- systemd supervision and automatic restarts

---

## Deployment Workflows

### Development Workflow (Unchanged)

```bash
# Developers continue using the all-in-one command
python manage.py metrics_service run
```

### Production Deployment Workflows

#### Option 1: RHEL/Fedora with Podman + systemd

```bash
# 1. Build images
./deployment/scripts/build-containers.sh

# 2. Run production setup
sudo ./deployment/scripts/setup-production.sh

# 3. Configure environment
sudo vi /etc/metrics-service/environment

# 4. Install systemd units
sudo ./deployment/scripts/install-systemd-services.sh

# 5. Initialize database
sudo -u metrics-service podman run --rm \
    --env-file=/etc/metrics-service/environment \
    --volume=/opt/metrics-service:/opt/app-root/src:Z \
    localhost/metrics-service-web:latest \
    python manage.py migrate

# 6. Start services
sudo systemctl start metrics-service.target

# 7. Check status
sudo systemctl status metrics-service.target
```

#### Option 2: OpenShift (Operator-Managed)

The OpenShift operator handles all deployment details automatically:

```yaml
apiVersion: metrics.ansible.com/v1
kind: MetricsService
metadata:
  name: metrics-service-instance
spec:
  replicas:
    web: 2
    dispatcher: 1
    scheduler: 1
```

Operator creates:
- Pods for each component
- ConfigMaps and Secrets
- Services and Routes
- PersistentVolumeClaims for SQLite
- Auto-scaling configurations

---

## File Structure

```
deployment/
├── containers/
│   ├── Containerfile.base          # Base image with all dependencies
│   ├── Containerfile.web            # Web/API service
│   ├── Containerfile.dispatcher     # Task dispatcher
│   └── Containerfile.scheduler      # Task scheduler
│
├── systemd/
│   ├── container-metrics-service-web.service
│   ├── container-metrics-service-dispatcher.service
│   ├── container-metrics-service-scheduler.service
│   └── metrics-service.target
│
├── uwsgi/
│   ├── metrics-service.ini          # uWSGI config (socket mode)
│   └── metrics-service-http.ini     # uWSGI config (HTTP mode)
│
├── scripts/
│   ├── build-containers.sh          # Build all images
│   ├── run-containers-local.sh      # Test locally
│   ├── install-systemd-services.sh  # Install systemd units
│   └── setup-production.sh          # Production setup
│
└── README.md                         # Complete deployment guide
```

---

## Key Design Decisions

### 1. Separate Containers vs Single Container

**Decision**: Three separate containers, one per service component

**Rationale**:
- Independent scaling (can scale web without scaling dispatcher)
- Isolated failures (web failure doesn't kill background tasks)
- Resource allocation per component
- Follows microservices best practices
- Easier monitoring and debugging

### 2. Base Image + Service Images

**Decision**: Single base image with lightweight service layers

**Rationale**:
- Reduces image duplication
- Faster builds (base cached)
- Consistent dependencies across services
- Smaller total storage footprint
- Easier updates (rebuild base, then services)

### 3. uWSGI vs Gunicorn

**Decision**: uWSGI for production WSGI server

**Rationale**:
- Better performance under load
- More mature and battle-tested
- Advanced features (stats server, cheaper subsystem)
- Standard in enterprise Django deployments
- Native support for unix sockets (nginx integration)

### 4. systemd + Podman vs Kubernetes YAML

**Decision**: Provide both options

**Rationale**:
- RHEL/Fedora deployments often use systemd + Podman
- OpenShift deployments use operator (no manual YAML needed)
- Systemd units are familiar to sysadmins
- Podman is rootless and daemonless (security benefit)

### 5. Shared SQLite Volume

**Decision**: All containers mount same SQLite database volume

**Rationale**:
- SQLite database (`metricsStorage.sqlite`) needs shared access
- Read-heavy workload (writes from scheduler, reads from web)
- SQLite WAL mode handles concurrent access
- Simpler than network file system
- Acceptable for metrics storage use case

---

## Environment Variables

All configuration via environment variables (12-factor app):

**Required (Production)**:
- `METRICS_SERVICE_SECRET_KEY` - Django secret key
- `METRICS_SERVICE_DB_PASSWORD` - PostgreSQL password
- `METRICS_SERVICE_ALLOWED_HOSTS` - Allowed hostnames

**Database**:
- `METRICS_SERVICE_DB_HOST`
- `METRICS_SERVICE_DB_PORT`
- `METRICS_SERVICE_DB_NAME`
- `METRICS_SERVICE_DB_USER`

**Optional**:
- `METRICS_SERVICE_MODE` - `production` or `development`
- `METRICS_SERVICE_LOG_LEVEL` - Logging verbosity
- `METRICS_SERVICE_ANONYMIZED_DATA` - Feature toggle
- `METRICS_SERVICE_METRICS_COLLECTION` - Feature toggle

Stored in `/etc/metrics-service/environment` (systemd deployment)

---

## Security Features

### Container Security

1. **Non-root User**: All containers run as UID 1001 (not root)
2. **Read-only Filesystem**: System directories mounted read-only
3. **No Privilege Escalation**: `NoNewPrivileges=true` in systemd
4. **Minimal Capabilities**: Drop all capabilities except required
5. **SELinux**: Volume mounts use `:Z` for proper labeling

### systemd Security

1. **ProtectSystem=strict** - Read-only system directories
2. **ProtectHome=true** - No access to home directories
3. **PrivateTmp=true** - Isolated /tmp directory
4. **ReadWritePaths** - Explicit writable paths only

### Secrets Management

1. Environment file with restrictive permissions (640)
2. Owned by root:metrics-service
3. Never in version control
4. Separate secrets for dev vs prod

---

## Monitoring and Observability

### Health Checks

Each container has health checks:

**Web**:
```bash
curl -f http://localhost:8000/api/health/ || exit 1
```

**Dispatcher**:
```bash
pgrep -f run_dispatcherd || exit 1
```

**Scheduler**:
```bash
pgrep -f run_task_scheduler || exit 1
```

### Logging

**systemd deployment**:
```bash
# All services
journalctl -u 'container-metrics-service-*' -f

# Individual service
journalctl -u container-metrics-service-web -f
```

**Direct container**:
```bash
podman logs -f metrics-service-web
```

### Metrics

- uWSGI stats server: `/run/metrics-service/stats.sock`
- Application metrics: `http://localhost:8000/metrics/`
- systemd status: `systemctl status metrics-service.target`

---

## Testing the Deployment

### Local Testing

```bash
# Build images
./deployment/scripts/build-containers.sh

# Run locally
./deployment/scripts/run-containers-local.sh

# Test web service
curl http://localhost:8000/api/health/

# Check logs
podman logs -f metrics-service-web

# Stop
podman stop metrics-service-web metrics-service-dispatcher metrics-service-scheduler
```

### Production Validation

```bash
# Check services running
systemctl status metrics-service.target

# Check container health
podman inspect --format='{{.State.Health.Status}}' metrics-service-web

# Test API
curl http://localhost:8000/api/health/

# Check logs
journalctl -u container-metrics-service-web -n 50
```

---

## Migration Path

### From Development to Production

1. **Build images** using build script
2. **Test locally** with run-containers-local.sh
3. **Deploy to staging** using systemd + Podman
4. **Validate** all three components working
5. **Deploy to production** using same process

### Rollback Strategy

```bash
# Stop new version
systemctl stop metrics-service.target

# Pull previous image tags
podman pull localhost/metrics-service-web:v1.0.0
podman pull localhost/metrics-service-dispatcher:v1.0.0
podman pull localhost/metrics-service-scheduler:v1.0.0

# Tag as latest
podman tag localhost/metrics-service-web:v1.0.0 localhost/metrics-service-web:latest

# Start services (systemd uses :latest)
systemctl start metrics-service.target
```

---

## Future Enhancements

### Possible Improvements

1. **Auto-scaling**: Horizontal pod autoscaling for web component in OpenShift
2. **Blue/Green Deployments**: Zero-downtime deployments
3. **Metrics Dashboard**: Grafana dashboard for monitoring
4. **Log Aggregation**: Central logging (ELK stack)
5. **CI/CD Pipeline**: Automated builds and deployments
6. **Multi-region**: Geographic distribution
7. **Backup Automation**: Scheduled database backups
8. **Secret Rotation**: Automated credential rotation

### Not Implemented (By Design)

- **OpenShift YAML manifests**: Managed by operator
- **Helm charts**: Not needed (operator-based)
- **Docker Swarm**: Not a deployment target
- **Nomad**: Not a deployment target

---

## Success Criteria

✅ **All Achieved**:

- [x] Three separate container images built successfully
- [x] Each component runs independently
- [x] Development workflow unchanged (`metrics_service run`)
- [x] Production uses uWSGI (not Django runserver)
- [x] systemd units for Podman deployment
- [x] Complete documentation
- [x] Build and deployment scripts
- [x] Environment variable configuration
- [x] Health checks for all components
- [x] Security hardening (non-root, read-only, etc.)
- [x] Logging integration (systemd journal)
- [x] Local testing capability
- [x] SQLite database sharing between containers

---

## Conclusion

The Metrics Service now has a complete, production-ready container deployment strategy that:

1. **Separates concerns** - Each component in its own container
2. **Maintains development simplicity** - `metrics_service run` still works
3. **Supports multiple platforms** - Podman+systemd and OpenShift
4. **Follows best practices** - 12-factor, security hardening, observability
5. **Is well documented** - Comprehensive guides and examples
6. **Is easily testable** - Local testing with provided scripts
7. **Is maintainable** - Clear architecture and standard tools

The implementation is ready for production deployment on RHEL/Fedora servers with Podman or OpenShift platforms with the custom operator.
