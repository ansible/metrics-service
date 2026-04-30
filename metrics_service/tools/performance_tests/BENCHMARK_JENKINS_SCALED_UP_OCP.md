# Running Scaled-Up Performance Benchmarks Against Jenkins OCP Deployments

**Jenkins pipeline:** AAPQA/AAPQA Provisioner/AAPQA-ATF-Test-Suite-Yolo

OCP deployments differ significantly from containerized Jenkins. There is no SSH access and
no `podman` — everything runs via `oc exec` directly inside the metrics-tasks pod over the
cluster network.

## Prerequisites

- `oc` CLI installed and working locally
- A Hive cluster claim kubeconfig per scale (downloaded from Jenkins build artifacts)
- `metrics-utility` checked out locally (for `fill_perf_db_data.py` and `mock_awx/`)
- `metrics-service` checked out locally (for `benchmark_manage.py`)

---

## Step 1 — Get credentials from OCP secrets

```bash
# Find the AAP namespace (e.g. aap-externally-griffon)
KUBECONFIG=~/Downloads/<kubeconfig>.yml oc get namespaces | grep aap-

# Get the automationcontroller DB password
KUBECONFIG=~/Downloads/<kubeconfig>.yml oc get secret -n <namespace> \
  -o yaml | grep -A5 "controller-postgres-configuration"

# Get the ms_awx_readonly password
KUBECONFIG=~/Downloads/<kubeconfig>.yml oc get secret -n <namespace> \
  -o yaml | grep -A5 "metrics-read-token"
```

Record:
- `<namespace>` — the aap-* namespace (e.g. `aap-externally-griffon`)
- `<metrics-tasks-pod>` — find with `oc get pods -n <namespace> | grep metrics-tasks`
- `<postgres-host>` — short hostname from controller-postgres-configuration (e.g. `aap-d8b56cc1-postgres-15`)
- `<controller-db-password>` — from controller-postgres-configuration
- `<read-token-password>` — from metrics-read-token secret

---

## Step 2 — Fix DB provisioning (ms_awx_readonly user)

OCP 2.6 deployments have a bug where the `ms_awx_readonly` read-token user is not created
during initial DB setup. Run this fix script **before** running any benchmarks.

```bash
KUBECONFIG=~/Downloads/<kubeconfig>.yml bash fix-metrics-db-provisioning.sh <namespace>
```

Then trigger a reconciliation so the operator re-runs DB provisioning:

```bash
KUBECONFIG=~/Downloads/<kubeconfig>.yml oc annotate aap <aap-cr-name> \
  -n <namespace> reconcile="$(date)" --overwrite
```

Wait ~2 minutes, then verify `ms_awx_readonly` can connect:

```bash
KUBECONFIG=~/Downloads/<kubeconfig>.yml oc exec -n <namespace> <metrics-tasks-pod> -- \
  python3.12 -c "
import psycopg2
conn = psycopg2.connect(host='<postgres-host>', user='ms_awx_readonly',
                        password='<read-token-password>', dbname='automationcontroller')
print('ok')
"
```

---

## Step 3 — Copy fill script dependencies into the pod

OCP containers have no `tar` binary, so `oc cp` does not work. Use base64 piping instead.

```bash
# Copy the three fill script files
for f in fill_perf_db_data.py helpers.py modules.py; do
  cat tools/anonymized_db_perf_data/$f | base64 | \
    KUBECONFIG=~/Downloads/<kubeconfig>.yml oc exec -i -n <namespace> <metrics-tasks-pod> -- \
    python3.12 -c "import base64,sys; open('/tmp/$f','wb').write(base64.b64decode(sys.stdin.buffer.read()))"
done

# Build and copy mock_awx (needed because pip-installed metrics_utility doesn't include it)
cd <path-to-metrics-utility>
tar -czf /tmp/mock_awx.tar.gz mock_awx/

cat /tmp/mock_awx.tar.gz | base64 | \
  KUBECONFIG=~/Downloads/<kubeconfig>.yml oc exec -i -n <namespace> <metrics-tasks-pod> -- \
  python3.12 -c "
import base64, sys, tarfile, io
data = base64.b64decode(sys.stdin.buffer.read())
target = '/var/lib/ansible-automation-platform/metrics/.local/lib/python3.12/site-packages'
with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
    tar.extractall(target)
print('extracted ok')
"
```

The `PYTHONPATH` must include both `/tmp` (for `helpers.py`) and the `mock_awx` site-packages
path. The container's `DJANGO_SETTINGS_MODULE=metrics_service.settings` must be overridden with
`DJANGO_SETTINGS_MODULE=settings` so mock_awx's settings (which read `METRICS_UTILITY_DB_*` env
vars) are used instead of the container's own metrics-service settings.

---

## Step 4 — Install psutil in the pod

`benchmark_manage.py` requires `psutil` for memory sampling, which is not installed by default:

```bash
KUBECONFIG=~/Downloads/<kubeconfig>.yml oc exec -n <namespace> <metrics-tasks-pod> -- \
  python3.12 -m pip install psutil
```

---

## Step 5 — Copy benchmark_manage.py into the pod

`benchmark_manage.py` needs `django.setup()` called before its model imports. The version in
this repo already includes it. Copy it the same way as the fill scripts:

```bash
cat metrics_service/tools/performance_tests/benchmark_manage.py | base64 | \
  KUBECONFIG=~/Downloads/<kubeconfig>.yml oc exec -i -n <namespace> <metrics-tasks-pod> -- \
  python3.12 -c "import base64,sys; open('/tmp/benchmark_manage.py','wb').write(base64.b64decode(sys.stdin.buffer.read()))"
```

---

## Step 6 — Generate fill data (run inside the pod)

Run the fill script **inside the pod** via `oc exec`. Do **not** use port-forwarding — it drops
under sustained load. The pod connects directly to postgres over the cluster network.

Run **four times per scale**, matching the containerized approach: once without `--date` (spreads
jobs across the whole month), then once each for 2024-01-24, 2024-01-25, and 2024-01-26.

```bash
# Convenience alias — set once per shell session
OC_EXEC="KUBECONFIG=~/Downloads/<kubeconfig>.yml oc exec -n <namespace> <metrics-tasks-pod> --"
FILL_ENV="env DJANGO_SETTINGS_MODULE=settings \
  PYTHONPATH=/tmp:/var/lib/ansible-automation-platform/metrics/.local/lib/python3.12/site-packages/mock_awx \
  METRICS_UTILITY_DB_HOST=<postgres-host> \
  METRICS_UTILITY_DB_USER=automationcontroller \
  METRICS_UTILITY_DB_PASSWORD=<controller-db-password> \
  METRICS_UTILITY_DB_NAME=automationcontroller"

# Run 1: whole month (no --date)
$OC_EXEC $FILL_ENV python3.12 -u /tmp/fill_perf_db_data.py \
  --job-count=<N> --host-count=<H> --no-events

# Run 2: 2024-01-24
$OC_EXEC $FILL_ENV python3.12 -u /tmp/fill_perf_db_data.py \
  --date=2024-01-24 --job-count=<N> --host-count=<H> --no-events

# Run 3: 2024-01-25
$OC_EXEC $FILL_ENV python3.12 -u /tmp/fill_perf_db_data.py \
  --date=2024-01-25 --job-count=<N> --host-count=<H> --no-events

# Run 4: 2024-01-26
$OC_EXEC $FILL_ENV python3.12 -u /tmp/fill_perf_db_data.py \
  --date=2024-01-26 --job-count=<N> --host-count=<H> --no-events
```

Scale parameters:

| Scale | `--job-count` | `--host-count` |
| ----- | ------------- | -------------- |
| Scale 1 | 2,500 | 5 |
| Scale 2 | 25,000 | 5 |
| Scale 3 | 250,000 | 5 |
| Scale 4 | 25,000 | 50 |

> **Note:** Files in `/tmp` are wiped on pod restart. If the pod restarts mid-fill, re-copy
> all files (Steps 3–5) before re-running.

---

## Step 7 — Run the benchmark

```bash
set -o pipefail
KUBECONFIG=~/Downloads/<kubeconfig>.yml oc exec -n <namespace> <metrics-tasks-pod> -- \
  python3.12 -u /tmp/benchmark_manage.py 2>&1 | tee results_scale<N>_ocp.txt
```

The benchmark connects to the metricsservice DB (via the container's default settings) and to
the automationcontroller DB (via the `awx` Django database alias, using `ms_awx_readonly`).
Both must be reachable from the pod.

---

## Results

Record timing and memory from the benchmark Summary section into `RESULTS_JENKINS_SCALED_UP_OCP.md`.

| Scale | Jobs | Hosts | Snapshot | Hourly | Daily rollup | Total | Baseline MB | Peak MB | Delta MB |
| ----- | ---- | ----- | -------- | ------ | ------------ | ----- | ----------- | ------- | -------- |
| Scale 1 | 2,500 | 5 | | | | | | | |
| Scale 2 | 25,000 | 5 | | | | | | | |
| Scale 3 | 250,000 | 5 | | | | | | | |
| Scale 4 | 25,000 | 50 | | | | | | | |

---

## Troubleshooting

**`AppRegistryNotReady` on benchmark run**
The script must call `django.setup()` before importing models. The version in this repo
includes it. If you see this error, re-copy `benchmark_manage.py` from the repo.

**`password authentication failed for user "ms_awx_readonly"`**
The DB user wasn't provisioned. Re-run Step 2 and trigger a reconciliation, then wait
~2 minutes before retrying.

**Fill script exits silently with no output**
`helpers.py` is missing from `/tmp`. The module-level `from helpers import ...` fails before
any error output is printed. Re-copy all three files (Step 3).

**`DJANGO_SETTINGS_MODULE` conflict**
The container sets `DJANGO_SETTINGS_MODULE=metrics_service.settings` by default, which makes
the fill script connect to the metricsservice DB instead of automationcontroller. Always
override with `DJANGO_SETTINGS_MODULE=settings` and set `PYTHONPATH` to include mock_awx.

**Pod `/tmp` wiped after restart**
All files must be re-copied after any pod restart. Re-run Steps 3–5 before continuing.

**`oc cp` fails**
The metrics-tasks container has no `tar` binary. Use the base64 pipe approach in Step 3.
