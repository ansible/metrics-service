# Performance Benchmarks — Containerized AAP (AWS)

This document covers running performance benchmarks against a real containerized
AAP deployment on AWS, using the testathon repo for data generation and two
complementary benchmark scripts for measurement.

> For the local `aap-dev` setup see `BENCHMARK_AAP_DEV.md`.

## Two measurement approaches

| Script | Approach | When to use |
|---|---|---|
| `benchmark_api.py` | **Manual trigger** — calls the API to trigger collectors at a specific `hour_timestamp`. Gives full control over which hour window is measured. | Isolated, on-demand testing where you want to control timing exactly. |
| `benchmark_cron_observer.py` | **Cron observer** — waits for the production cron to fire at `:05` each hour, then captures the `TaskExecution` timing. | Realistic production measurement, as recommended by Milan. |

Milan's guidance is that **cron-based measurement is the correct approach for
production realism**: collectors run every hour, each reading only the previous
hour's 1-hour window, which is how the service is designed to avoid loading
unbounded data into memory at once.

---

## Architecture

```
Local machine
  └── SSH tunnel ──► automationmetrics VM (AWS)
                          ├── automation-metrics-service container (:8006)
                          ├── prometheus container (:9090)
                          └── grafana container (:3001)
```

---

## Prerequisites

- SSH access to the `automationmetrics` VM
- Monitoring stack deployed (`cd grafana-dashboard && ./setup.sh <HOST_IP>`)
- Custom Prometheus patches applied to `automation-metrics-service` (see below)
- Python 3 with `requests` installed locally
- SSH tunnel open to the VM

---

## Step 1 — Apply patches to metrics-service container

After each reprovision, copy the instrumented files into the running container:

```bash
HOST=<METRICS_HOST_IP>

scp metrics-service/apps/tasks/utils.py \
    metrics-service/apps/tasks/metrics.py \
    ansible@$HOST:/tmp/

scp metrics-service/metrics_service/cli.py \
    ansible@$HOST:/tmp/cli.py

ssh ansible@$HOST "
  podman cp /tmp/utils.py   automation-metrics-service:/tmp/ && \
  podman cp /tmp/metrics.py automation-metrics-service:/tmp/ && \
  podman cp /tmp/cli.py     automation-metrics-service:/tmp/ && \
  podman exec --user root automation-metrics-service \
    cp /tmp/utils.py /tmp/metrics.py /usr/lib/python3.12/site-packages/apps/tasks/ && \
  podman exec --user root automation-metrics-service \
    cp /tmp/cli.py /usr/lib/python3.12/site-packages/metrics_service/cli.py && \
  podman exec --user root automation-metrics-service \
    mkdir -p /tmp/prometheus_multiproc && \
  podman restart automation-metrics-service
"
```

Verify custom metrics are exposed:
```bash
ssh ansible@$HOST "curl -s http://localhost:8006/metrics | grep collector_"
# Should show: collector_execution_time_seconds, collector_runs_total, job_host_summaries_processed_total
```

---

## Step 2 — Open SSH tunnel

```bash
ssh -L 8006:localhost:8006 \
    -L 3001:localhost:3001 \
    -L 9090:localhost:9090 \
    -o ServerAliveInterval=60 \
    ansible@<METRICS_HOST_IP> -N &
```

| Service | URL |
|---|---|
| metrics-service API | http://localhost:8006/api/v1/ |
| metrics-service /metrics | http://localhost:8006/metrics |
| Grafana | http://localhost:3001 (admin / admin) |
| Prometheus | http://localhost:9090 |

---

## Step 3 — Generate test data (testathon)

### Understanding the collection time window

This is the most important timing concept for correct benchmarking:

The cron job fires at **XX:05** and collects the window **[XX-1:00, XX:00)** —
the previous complete hour. For example:
- Cron fires at **14:05** → collects jobs that finished between **13:00–14:00**

**You must generate AWX test data such that jobs finish within the target hour window.**

The easiest approach is:

1. Start `benchmark_cron_observer.py` — it will print the exact window for the
   next cron run and count down to it.
2. Run testathon **immediately**. Jobs will finish within the current running hour.
3. The observer script will automatically capture the `:05` cron run timing.

```
Example timeline:
  13:01  →  You start benchmark_cron_observer.py
             Script prints: "Target window: 13:00–14:00, cron fires at 14:05"
  13:05  →  You run testathon (jobs run and finish ~13:10)
  14:05  →  Cron fires, collects 13:00–14:00 window → script records result
```

If you miss the window (testathon finishes after the hour boundary), simply
wait for the observer to count down to the next `:05` and let it catch the
following cron run instead.

### Running testathon

```bash
cd /home/lrios/Documents/redhat_projects/ansible-projects/emerging-services-test-suite/testathon

# Baseline (Test Case 1): 500 records = 100 hosts × 5 job runs
ansible-playbook perf_data_generator.yml \
  -e @creds.yml \
  -e perf_host_count=100 \
  -e perf_job_runs=5 \
  -e aap_validate_certs=false \
  -e '{"perf_targets": [{"inventory": "integrity_tests-inventory_aws", "job_template": "Perf Test - AWS Inventory Run", "add_hosts": true}]}'
```

Adjust `perf_host_count` and `perf_job_runs` for other scales (see test cases below).

After generation, verify the record count in AWX:
```bash
ssh ansible@<HOST> "
  podman exec automation-controller-task \
    awx-manage shell_plus --plain -c \
    'from awx.main.models import JobHostSummary; print(JobHostSummary.objects.count())'
"
```

---

## Step 4 — Run the benchmark

### Option A: Cron observer (recommended — production realistic)

The `benchmark_cron_observer.py` script waits for the production cron to fire
and captures its actual execution time. This is the approach Milan recommended.

```bash
cd /home/lrios/Documents/redhat_projects/ansible-projects/metrics-service

BASE_URL=http://localhost:8006/api \
BENCHMARK_USER=admin \
PASSWORD=Admin!Password!Metrics \
METRICS_URL=http://localhost:8006/metrics \
DATA_SCALE=500_job_host_summaries \
python metrics_service/tools/performance_tests/benchmark_cron_observer.py
```

The script will:
1. Print the exact hour window the next cron will collect
2. Show a live countdown to the `:05` cron fire time
3. Detect when the cron task appears in TaskExecution
4. Wait for it to complete and record `started_at → completed_at`
5. Save a JSON result file to `results/cron_YYYY-MM-DD_HHMMSS_<DATA_SCALE>.json`

To observe multiple consecutive cron runs (e.g. idempotency test across 5 hours):
```bash
OBSERVE_RUNS=5 \
DATA_SCALE=3400_repeated_cron \
BASE_URL=http://localhost:8006/api \
BENCHMARK_USER=admin \
PASSWORD=Admin!Password!Metrics \
python metrics_service/tools/performance_tests/benchmark_cron_observer.py
```

### Option B: Manual trigger (on-demand, full control)

If you need to test a specific date/time window or run all 3 phases
(snapshot + 24h hourly + daily rollup) in one shot, use `benchmark_api.py`.

```bash
cd /home/lrios/Documents/redhat_projects/ansible-projects/metrics-service

BASE_URL=http://localhost:8006/api \
BENCHMARK_USER=admin \
PASSWORD=Admin!Password!Metrics \
METRICS_URL=http://localhost:8006/metrics \
TEST_DATE=<YYYY-MM-DD> \
DATA_SCALE=<scale_label> \
python metrics_service/tools/performance_tests/benchmark_api.py
```

Results are saved automatically to:
```
metrics_service/tools/performance_tests/results/YYYY-MM-DD_HHMMSS_<DATA_SCALE>.json   # manual
metrics_service/tools/performance_tests/results/cron_YYYY-MM-DD_HHMMSS_<DATA_SCALE>.json  # cron observer
```

---

## Test Cases

### Test Case 1 — Baseline (small data)

**Goal:** Establish a baseline with minimal data as a reference point.

| Parameter | Value |
|---|---|
| JobHostSummary records | ~500 |
| `DATA_SCALE` | `500_job_host_summaries` |
| Expected execution time | < 1s |

```bash
BASE_URL=http://localhost:8006/api \
BENCHMARK_USER=admin \
PASSWORD=<PASSWORD> \
METRICS_URL=http://localhost:8006/metrics \
TEST_DATE=<YYYY-MM-DD> \
DATA_SCALE=500_job_host_summaries \
python metrics_service/tools/performance_tests/benchmark_api.py
```

---

### Test Case 2 — Medium scale (current state)

**Goal:** Measure with realistic small customer data.

| Parameter | Value |
|---|---|
| JobHostSummary records | ~3,400 |
| `DATA_SCALE` | `3400_job_host_summaries` |
| Expected execution time | ~1.8s |

```bash
BASE_URL=http://localhost:8006/api \
BENCHMARK_USER=admin \
PASSWORD=<PASSWORD> \
METRICS_URL=http://localhost:8006/metrics \
TEST_DATE=<YYYY-MM-DD> \
DATA_SCALE=3400_job_host_summaries \
python metrics_service/tools/performance_tests/benchmark_api.py
```

---

### Test Case 3 — Large scale

**Goal:** Simulate a mid-size customer (hundreds of hosts, running jobs daily for months).

| Parameter | Value |
|---|---|
| JobHostSummary records | ~50,000 |
| `DATA_SCALE` | `50000_job_host_summaries` |
| Key question | Does it scale linearly or does it degrade? |

```bash
BASE_URL=http://localhost:8006/api \
BENCHMARK_USER=admin \
PASSWORD=<PASSWORD> \
METRICS_URL=http://localhost:8006/metrics \
TEST_DATE=<YYYY-MM-DD> \
DATA_SCALE=50000_job_host_summaries \
python metrics_service/tools/performance_tests/benchmark_api.py
```

---

### Test Case 4 — Repeated hourly runs (idempotency)

**Goal:** Measure what happens on subsequent runs when no new data exists.

| Parameter | Value |
|---|---|
| Dataset | Same as Test Case 2 (~3,400 records) |
| Runs | 5x back-to-back against the same `TEST_DATE` |
| Expected | Near-zero after first run (~25ms) since nothing new to process |
| Key question | Is there any memory or DB leak across repeated runs? |

Run the benchmark 5 times in sequence without regenerating data:

```bash
for i in 1 2 3 4 5; do
  BASE_URL=http://localhost:8006/api \
  BENCHMARK_USER=admin \
  PASSWORD=<PASSWORD> \
  METRICS_URL=http://localhost:8006/metrics \
  TEST_DATE=<YYYY-MM-DD> \
  DATA_SCALE=3400_repeated_run_${i} \
  python metrics_service/tools/performance_tests/benchmark_api.py
  echo "--- Run $i complete ---"
done
```

Compare the 5 JSON result files — execution time should drop sharply after run 1.

---

### Test Case 5 — All collectors simultaneously

**Goal:** Measure contention when all hourly collectors run at the same time.

| Parameter | Value |
|---|---|
| Dataset | Same as Test Case 2 (~3,400 records) |
| Key question | Does running in parallel slow each collector down vs. running alone? |

Trigger all 3 collectors at the same time via the API (no waiting between calls):

```bash
HOST=localhost
DATE=<YYYY-MM-DD>T12:00:00Z

curl -s -X POST http://$HOST:8006/api/v1/tasks/schedule_immediate/ \
  -H "Content-Type: application/json" \
  -u admin:<PASSWORD> \
  -d '{"function_name":"collect_hourly_metrics","task_data":{"collector_type":"job_host_summary_service","hour_timestamp":"'$DATE'"},"name":"parallel-test-jhs"}' &

curl -s -X POST http://$HOST:8006/api/v1/tasks/schedule_immediate/ \
  -H "Content-Type: application/json" \
  -u admin:<PASSWORD> \
  -d '{"function_name":"collect_hourly_metrics","task_data":{"collector_type":"unified_jobs","hour_timestamp":"'$DATE'"},"name":"parallel-test-uj"}' &

curl -s -X POST http://$HOST:8006/api/v1/tasks/schedule_immediate/ \
  -H "Content-Type: application/json" \
  -u admin:<PASSWORD> \
  -d '{"function_name":"collect_hourly_metrics","task_data":{"collector_type":"credentials_service","hour_timestamp":"'$DATE'"},"name":"parallel-test-cs"}' &

wait
```

Monitor execution times in Grafana (`collector_execution_time_seconds`) and
compare against the individual timings from Test Case 2.

---

## Capturing Results

After each test case run:

1. **Commit the JSON result file:**
   ```bash
   cd <path-to-metrics-service>
   git add metrics_service/tools/performance_tests/results/
   git commit -m "perf: add benchmark result for <DATA_SCALE>"
   ```

2. **Take a Grafana screenshot** of the Collector Performance panels covering
   the test run window (`http://localhost:3001`)

3. **Update `RESULTS_API.md`** with a summary of findings for that test case

---

## Findings Template

Add an entry to `RESULTS_API.md` for each completed test case:

```
## <Date> — Test Case <N>: <Title>

**Environment:** AAP <version>, AWS <instance_type>
**Data scale:** <N> JobHostSummary records
**Result file:** results/YYYY-MM-DD_HHMMSS_<DATA_SCALE>.json

| Phase | Duration |
|---|---|
| Snapshot collectors | Xs |
| Hourly collection (24h × 4 collectors) | Xs |
| Daily rollup | Xs |
| Total | Xs |

**Observations:**
- ...

**Key question answered:**
- ...
```
