# Performance Test Data Generation

Ansible playbooks for generating realistic AWX data at scale to support
`metrics-service` performance testing.

The playbooks live in this directory alongside a `creds.yml` (not committed)
and an `ansible.cfg` that points to the shared Ansible collections in
`emerging-services-test-suite/testathon/collections/`.

> **Prerequisites**:
> 1. Clone `emerging-services-test-suite` so the collections are available at:
>    `emerging-services-test-suite/testathon/collections/`
> 2. Copy `creds.yml.example` to `creds.yml` and fill in your AAP credentials.
>
> ```bash
> cd metrics-service/metrics_service/tools/performance_tests/data_generation/
> cp creds.yml.example creds.yml   # fill in your credentials
> ansible-playbook perf_data_generator.yml -e @creds.yml -e aap_validate_certs=false \
>   -e perf_host_count=<N> -e perf_job_runs=<R>
> ```
>
> If the collections path in `ansible.cfg` doesn't match your local clone,
> update it to the absolute path of your `testathon/collections/` directory.

---

## Full Workflow Example

Here is a complete end-to-end example for running a **Large scale (20,000 records)** test:

```bash
# 0. Navigate to the data_generation directory
cd metrics-service/metrics_service/tools/performance_tests/data_generation/

# 1. First time only — set up AWX inventory and job template
ansible-playbook setup_perf_resources.yml -e @creds.yml -e aap_validate_certs=false

# 2. Clean the inventory (required when changing scale or starting fresh)
ansible-playbook perf_cleanup_inventory.yml -e @creds.yml -e aap_validate_certs=false

# 3. Generate data — 1000 hosts × 20 runs = ~20,000 JobHostSummary records
ansible-playbook perf_data_generator.yml \
  -e @creds.yml \
  -e aap_validate_certs=false \
  -e perf_host_count=1000 \
  -e perf_job_runs=20

# 4. Wait for the metrics-service cron to fire (runs at :05 past each hour)
#    Then observe and capture results:
cd metrics-service/metrics_service/tools/performance_tests/
python3 benchmark_cron_observer.py

# 5. Fetch TaskExecution metrics for documentation
python3 fetch_taskexecution_metrics.py --save
```

---

## Files

### `setup_perf_resources.yml`
**Run once per AAP instance.**

Creates the AWX inventory (`integrity_tests-inventory_aws`) and job template
(`Perf Test - AWS Inventory Run`) needed by the data generator. Only required
when provisioning a fresh AAP environment.

```bash
ansible-playbook setup_perf_resources.yml -e @creds.yml -e aap_validate_certs=false
```

---

### `perf_cleanup_inventory.yml`
**Run before each test case when scaling down.**

Deletes all hosts from `integrity_tests-inventory_aws` to ensure a clean
inventory state before generating data at a new scale. Only strictly necessary
when reducing the number of hosts (e.g. going from 1,000 hosts back to 100).

```bash
ansible-playbook perf_cleanup_inventory.yml -e @creds.yml -e aap_validate_certs=false
```

---

### `perf_data_generator.yml`
**Main entry point for data generation.**

Accepts `perf_host_count` and `perf_job_runs` variables to control the scale
of the test data. Total `JobHostSummary` records produced equals
`perf_host_count × perf_job_runs`.

Hosts are created in batches of 100 with a short pause between batches to
prevent overloading the AWX controller uWSGI workers.

```bash
# Baseline  (~500 records):  100 hosts × 5 runs
ansible-playbook perf_data_generator.yml -e @creds.yml -e aap_validate_certs=false \
  -e perf_host_count=100 -e perf_job_runs=5

# Medium  (~4,000 records):  400 hosts × 10 runs
ansible-playbook perf_data_generator.yml -e @creds.yml -e aap_validate_certs=false \
  -e perf_host_count=400 -e perf_job_runs=10

# Large  (~20,000 records):  1000 hosts × 20 runs
ansible-playbook perf_data_generator.yml -e @creds.yml -e aap_validate_certs=false \
  -e perf_host_count=1000 -e perf_job_runs=20

# X-Large (~40,000 records): 1000 hosts × 40 runs
ansible-playbook perf_data_generator.yml -e @creds.yml -e aap_validate_certs=false \
  -e perf_host_count=1000 -e perf_job_runs=40
```

---

### `perf_data_generator_inventory.yml`
**Internal helper — not called directly.**

Contains the per-inventory tasks used by `perf_data_generator.yml` via
`include_tasks`. Handles batched host creation and job launching with retries
and delays to handle transient AWX API errors (HTTP 500/503).

---

### `benchmark_cron_observer.py`
**Observes the production cron schedule and captures results automatically.**

Unlike `benchmark_api.py` (which triggers collectors manually), this script
waits for the natural cron tick (default: XX:05) and captures the
`job_host_summary_service` run as it fires in production. It prints the exact
data generation window so you know when to run testathon, then polls until the
task completes and saves a timestamped JSON result file.

```bash
BASE_URL=http://localhost:8006/api \
BENCHMARK_USER=admin \
PASSWORD=<your-password> \
METRICS_URL=http://localhost:8006/metrics \
DATA_SCALE=4000_job_host_summaries \
    python benchmark_cron_observer.py

# Capture multiple consecutive cron runs:
OBSERVE_RUNS=3 python benchmark_cron_observer.py
```

Key environment variables:
- `CRON_MINUTE` — which minute to wait for (default: `5` = XX:05)
- `OBSERVE_RUNS` — number of consecutive cron runs to capture (default: `1`)
- `DATA_SCALE` — label included in the output filename
- `RESULTS_DIR` — where to write JSON results (default: `../results/`)
