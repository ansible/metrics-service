# Single Container vs Multi-Container Deployment

## Question: Should we use one container or three separate containers?

Both approaches are **valid** and **possible**. Here's a detailed comparison:

---

## Architecture Comparison

### Current: 3 Separate Containers

```
┌─────────────────────────────────────────┐
│ Pod: metrics-service-web                │
│  Container: web                         │
│   └─ uWSGI → Django (port 8000)        │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Pod: metrics-service-dispatcher         │
│  Container: dispatcher                  │
│   └─ dispatcherd (background tasks)    │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ Pod: metrics-service-scheduler          │
│  Container: scheduler                   │
│   └─ APScheduler (cron tasks)          │
└─────────────────────────────────────────┘
```

**Result**: 3 Pods (in OpenShift/Kubernetes)

### Alternative: 1 Container with 3 Processes

```
┌─────────────────────────────────────────┐
│ Pod: metrics-service                    │
│  Container: all-in-one                  │
│   └─ supervisord                        │
│       ├─ uWSGI → Django (port 8000)    │
│       ├─ dispatcherd                   │
│       └─ APScheduler                   │
└─────────────────────────────────────────┘
```

**Result**: 1 Pod (in OpenShift/Kubernetes)

---

## Pros and Cons

### 3 Separate Containers ✅ (Current Implementation)

#### Advantages ✅

1. **Independent Scaling**
   - Scale web to 5 replicas, keep dispatcher/scheduler at 1
   - Different resource limits per component
   - Example: `web: 2 replicas, dispatcher: 1 replica, scheduler: 1 replica`

2. **Isolated Failures**
   - Web crashes? Dispatcher keeps running tasks
   - Dispatcher OOM? Web still serves API requests
   - Better fault tolerance

3. **Resource Management**
   - Different CPU/memory limits per service
   - Web: 500m CPU, 1Gi memory
   - Dispatcher: 2000m CPU, 4Gi memory
   - Scheduler: 100m CPU, 256Mi memory

4. **Rolling Updates**
   - Update web without restarting dispatcher
   - Update dispatcher without affecting web
   - Zero-downtime for web service

5. **Monitoring & Debugging**
   - Clear separation of logs
   - Easy to identify which component has issues
   - Better metrics per component

6. **Container Best Practices**
   - "One process per container" principle
   - Simpler health checks
   - Follows Kubernetes/OpenShift patterns

7. **Development Parity**
   - Mirrors the logical separation in code
   - Each component has its own management command

#### Disadvantages ❌

1. **More Resources** (minimal impact)
   - 3 pods instead of 1
   - Slight overhead for container runtime
   - More image pulls (but they share base layers)

2. **Slightly More Complex**
   - Need to manage 3 deployments
   - 3 sets of health checks
   - (But operators handle this automatically)

3. **Shared Volume**
   - SQLite database needs ReadWriteMany volume
   - Requires NFS or similar for multi-node

---

### 1 All-in-One Container (Alternative)

#### Advantages ✅

1. **Simpler Deployment**
   - Single pod to manage
   - One deployment YAML
   - Fewer moving parts

2. **Lower Resource Overhead**
   - One container runtime instead of three
   - One set of sidecar containers (if any)
   - Slightly lower memory footprint

3. **Easier Local Development**
   - Single container to run/test
   - Closer to `metrics_service run` command

4. **No Shared Volume Complexity**
   - All processes in same filesystem
   - SQLite access straightforward

#### Disadvantages ❌

1. **No Independent Scaling**
   - Can't scale web without scaling dispatcher
   - Wastes resources (dispatcher doesn't need 5 replicas)
   - Less efficient resource usage

2. **Coupled Failures**
   - One process crashes, might affect others
   - OOM in dispatcher kills entire pod (including web)
   - Lower availability

3. **No Independent Updates**
   - Must restart all services to update one
   - Downtime for web when updating dispatcher
   - Rolling updates affect all components

4. **Process Management Required**
   - Need supervisord or similar
   - More complex Containerfile
   - Additional dependency

5. **Against Container Best Practices**
   - Multiple processes per container
   - Harder to debug issues
   - Less cloud-native

6. **Health Checks More Complex**
   - Need to check all 3 processes
   - Harder to identify which is failing

---

## OpenShift/Kubernetes Pod Count

### Current (3 Containers) = 3 Pods

```yaml
# Deployment 1: Web (can scale to N replicas)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: metrics-service-web
spec:
  replicas: 2  # <-- Can scale independently
  template:
    spec:
      containers:
      - name: web
        image: metrics-service-web:latest

# Deployment 2: Dispatcher (typically 1 replica)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: metrics-service-dispatcher
spec:
  replicas: 1  # <-- Usually just 1
  template:
    spec:
      containers:
      - name: dispatcher
        image: metrics-service-dispatcher:latest

# Deployment 3: Scheduler (always 1 replica)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: metrics-service-scheduler
spec:
  replicas: 1  # <-- Always 1
  template:
    spec:
      containers:
      - name: scheduler
        image: metrics-service-scheduler:latest
```

**Total Pods**: 2 (web) + 1 (dispatcher) + 1 (scheduler) = **4 pods**

### Alternative (1 Container) = 1 Pod

```yaml
# Single Deployment: All-in-One
apiVersion: apps/v1
kind: Deployment
metadata:
  name: metrics-service
spec:
  replicas: 1  # <-- Can't scale beyond 1 (scheduler must be singleton)
  template:
    spec:
      containers:
      - name: all-in-one
        image: metrics-service-all-in-one:latest
```

**Total Pods**: **1 pod**

---

## Recommendations by Use Case

### Use 3 Separate Containers When:

✅ **Deploying to OpenShift/Kubernetes** (Recommended)
- Operator can manage complexity
- Need independent scaling
- Want high availability
- Following cloud-native practices

✅ **Production Environments**
- Fault tolerance is important
- Need to scale web independently
- Want fine-grained resource control
- Need rolling updates without downtime

✅ **High Traffic / High Load**
- Web needs to scale to 5+ replicas
- Dispatcher processes many tasks
- Need different resource limits per component

### Use 1 All-in-One Container When:

✅ **Development/Testing** (Local)
- Simpler to run locally
- Closer to development command
- Don't need scaling

✅ **Small Deployments** (Low traffic)
- Single small VM/server
- Limited resources
- Don't need high availability
- Simplicity over scalability

✅ **Edge Deployments**
- Running on limited hardware
- Need minimal overhead
- Can tolerate coupled failures

---

## Resource Usage Comparison

### Scenario: Moderate Traffic

**3 Containers**:
```
Web (2 replicas):        2 × 500m CPU, 1Gi RAM    = 1 CPU, 2Gi RAM
Dispatcher (1 replica):  1 × 2 CPU, 4Gi RAM       = 2 CPU, 4Gi RAM
Scheduler (1 replica):   1 × 100m CPU, 256Mi RAM  = 100m CPU, 256Mi RAM
-------------------------------------------------------------------
Total:                   3.1 CPU, 6.25Gi RAM (4 pods)
```

**1 All-in-One**:
```
All-in-One (1 replica):  1 × 2.6 CPU, 5Gi RAM     = 2.6 CPU, 5Gi RAM (1 pod)
```

**Difference**:
- 3-container uses ~20% more resources
- But provides independent scaling and fault tolerance
- Worth it for production workloads

---

## Implementation Details

### Building All-in-One Container

```bash
# Build base image first
podman build -f deployment/containers/Containerfile.base \
    -t localhost/metrics-service-base:latest .

# Build all-in-one image
podman build -f deployment/containers/Containerfile.all-in-one \
    -t localhost/metrics-service-all-in-one:latest .

# Run locally
podman run -d \
    --name metrics-service \
    -p 8000:8000 \
    -e METRICS_SERVICE_MODE=production \
    localhost/metrics-service-all-in-one:latest
```

### Process Management (All-in-One)

**Option A: supervisord** (Recommended)
- Robust process manager
- Automatic restarts
- Good logging
- Industry standard
- File: `deployment/supervisor/supervisord.conf`

**Option B: Shell script** (Simpler)
- Background processes with `&`
- Less robust
- No automatic restarts
- File: `deployment/scripts/start-all-services.sh`

---

## Migration Path

### From 3 Containers → 1 All-in-One

```bash
# 1. Build all-in-one image
podman build -f deployment/containers/Containerfile.all-in-one \
    -t metrics-service-all-in-one:latest .

# 2. Stop 3-container deployment
systemctl stop metrics-service.target
# OR
kubectl delete deployment metrics-service-web metrics-service-dispatcher metrics-service-scheduler

# 3. Deploy all-in-one
systemctl start container-metrics-service-all-in-one
# OR
kubectl apply -f deployment-all-in-one.yaml
```

### From 1 All-in-One → 3 Containers

```bash
# 1. Build 3 separate images
./deployment/scripts/build-containers.sh

# 2. Stop all-in-one
systemctl stop container-metrics-service-all-in-one
# OR
kubectl delete deployment metrics-service

# 3. Deploy 3 containers
systemctl start metrics-service.target
# OR (OpenShift operator handles this)
```

---

## Final Recommendation

### For Your Case (OpenShift with Operator): Use 3 Separate Containers ✅

**Reasons**:

1. **Operator Handles Complexity**: The operator manages 3 deployments easily
2. **Independent Scaling**: Can scale web to handle traffic spikes
3. **High Availability**: Fault isolation between components
4. **Cloud-Native**: Follows Kubernetes/OpenShift best practices
5. **Future-Proof**: Easier to add features like HPA (auto-scaling)

### When to Consider All-in-One

- **Very small deployments** (1-2 users, low traffic)
- **Development/testing** environments only
- **Extreme resource constraints** (edge devices, IoT)

---

## Summary Table

| Feature | 3 Containers | 1 All-in-One |
|---------|--------------|--------------|
| Pod Count | 3-4 pods | 1 pod |
| Scaling | Independent | Coupled |
| Fault Tolerance | High | Low |
| Resource Efficiency | -20% | Baseline |
| Complexity | Medium (operator handles) | Low |
| Production Ready | ✅ Yes | ⚠️ For small deployments |
| Cloud-Native | ✅ Yes | ❌ No |
| Rolling Updates | ✅ Zero-downtime | ❌ Requires restart |
| Recommended For | **Production, OpenShift** | Development, Edge |

---

## Conclusion

**Your current 3-container approach is the right choice for production OpenShift deployment.**

The all-in-one container is **possible** and **simpler** but sacrifices the key benefits of containerized microservices: independent scaling, fault isolation, and zero-downtime updates.

**Recommendation**: Keep the 3-container approach. The operator will handle the complexity, and you'll get production-grade reliability and scalability.
