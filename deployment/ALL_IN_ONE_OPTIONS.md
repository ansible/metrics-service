# All-in-One Container Options

You now have **2 options** for running all 3 services in a single container:

## Option 1: Supervisor-based (More Robust) ✅

**File**: `Containerfile.all-in-one`

**Uses**: Python `supervisor` package (installed via pip)

**Pros**:
- ✅ Automatic process restarts if a service crashes
- ✅ Better process management
- ✅ Individual log files per service
- ✅ Can control processes via `supervisorctl`
- ✅ Industry standard for multi-process containers

**Cons**:
- Additional dependency (supervisor Python package)
- Slightly more complex configuration

**Build**:
```bash
podman build -f deployment/containers/Containerfile.all-in-one \
    -t localhost/metrics-service-all-in-one:latest .
```

**Configuration**: `deployment/supervisor/supervisord.conf`

---

## Option 2: Shell Script-based (Simpler) ✅

**File**: `Containerfile.all-in-one-simple`

**Uses**: Bash entrypoint script

**Pros**:
- ✅ No additional dependencies
- ✅ Very simple to understand
- ✅ Minimal overhead
- ✅ Good for basic use cases

**Cons**:
- ❌ No automatic restarts (if one service crashes, container exits)
- ❌ Less control over individual processes
- ❌ All logs go to stdout (harder to separate)

**Build**:
```bash
podman build -f deployment/containers/Containerfile.all-in-one-simple \
    -t localhost/metrics-service-all-in-one-simple:latest .
```

**Configuration**: `deployment/scripts/container-entrypoint.sh`

---

## Comparison Table

| Feature | Supervisor-based | Shell Script-based |
|---------|------------------|-------------------|
| Dependencies | supervisor (pip) | None (bash only) |
| Process Restart | ✅ Automatic | ❌ Container exits |
| Process Control | ✅ supervisorctl | ❌ Limited |
| Logs | Separate files | Combined stdout |
| Complexity | Medium | Low |
| Reliability | High | Medium |
| Best For | Production all-in-one | Dev/testing |

---

## Quick Start Examples

### Supervisor-based

```bash
# Build
podman build -f deployment/containers/Containerfile.all-in-one \
    -t localhost/metrics-service-all-in-one:latest .

# Run
podman run -d \
    --name metrics-service \
    -p 8000:8000 \
    -e METRICS_SERVICE_MODE=production \
    -e METRICS_SERVICE_SECRET_KEY=dev-key \
    -e METRICS_SERVICE_ALLOWED_HOSTS=localhost \
    localhost/metrics-service-all-in-one:latest

# Check process status inside container
podman exec metrics-service supervisorctl status

# View logs
podman exec metrics-service tail -f /opt/app-root/src/logs/web.log
podman exec metrics-service tail -f /opt/app-root/src/logs/dispatcher.log
podman exec metrics-service tail -f /opt/app-root/src/logs/scheduler.log
```

### Shell Script-based

```bash
# Build
podman build -f deployment/containers/Containerfile.all-in-one-simple \
    -t localhost/metrics-service-all-in-one-simple:latest .

# Run
podman run -d \
    --name metrics-service \
    -p 8000:8000 \
    -e METRICS_SERVICE_MODE=production \
    -e METRICS_SERVICE_SECRET_KEY=dev-key \
    -e METRICS_SERVICE_ALLOWED_HOSTS=localhost \
    localhost/metrics-service-all-in-one-simple:latest

# Check processes
podman exec metrics-service ps aux

# View combined logs
podman logs -f metrics-service
```

---

## Recommendation

**For all-in-one deployment**: Use **Supervisor-based** (`Containerfile.all-in-one`)

**Reasons**:
1. More robust - services restart on failure
2. Better process management
3. Separate logs for debugging
4. Can control individual services

**When to use Simple version**:
- Quick local testing
- Extreme simplicity needed
- Learning/understanding the architecture

---

## Systemd Unit for All-in-One (Podman)

If you want to deploy the all-in-one container with systemd:

```bash
# Create systemd unit
sudo tee /etc/systemd/system/container-metrics-service-all-in-one.service <<EOF
[Unit]
Description=Metrics Service All-in-One Container
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=notify
NotifyAccess=all
User=metrics-service
Group=metrics-service

Environment=PODMAN_SYSTEMD_UNIT=%n
EnvironmentFile=-/etc/metrics-service/environment

ExecStartPre=/usr/bin/podman pull localhost/metrics-service-all-in-one:latest || /bin/true
ExecStart=/usr/bin/podman run \\
    --name=metrics-service-all-in-one \\
    --rm \\
    --network=host \\
    --env-file=/etc/metrics-service/environment \\
    --volume=/opt/metrics-service:/opt/app-root/src:Z \\
    --volume=/var/log/metrics-service:/opt/app-root/src/logs:Z \\
    --label=io.containers.autoupdate=registry \\
    localhost/metrics-service-all-in-one:latest

ExecStop=/usr/bin/podman stop -t 60 metrics-service-all-in-one
ExecStopPost=/usr/bin/podman rm -f metrics-service-all-in-one || /bin/true

Restart=always
RestartSec=10
TimeoutStartSec=300
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable container-metrics-service-all-in-one
sudo systemctl start container-metrics-service-all-in-one
```

---

## Still Recommend 3 Separate Containers for Production

While these all-in-one options work, **3 separate containers** is still the better choice for production because:

1. Independent scaling (web can scale, dispatcher stays at 1)
2. Fault isolation (web crash doesn't kill dispatcher)
3. Zero-downtime updates (update web without restarting dispatcher)
4. Cloud-native best practices

Use all-in-one for:
- Local development/testing
- Very small deployments
- Edge devices with limited resources
- Simplified local testing before deploying to OpenShift
