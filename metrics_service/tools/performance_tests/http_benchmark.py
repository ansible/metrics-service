#!/usr/bin/env python
"""
HTTP performance benchmark for the metrics-service API.

Runs in two phases against a deployed metrics-service instance:

  Phase 1 — Sequential: 10 requests per endpoint, one at a time.
             Gives a clean baseline latency with no concurrency noise.

  Phase 2 — Concurrent load: 100 requests per endpoint across 5 workers.
             Shows how the service handles multiple simultaneous clients.

If METRICS_URL is set, the script also reads the service's Prometheus
/metrics endpoint before and after Phase 2 to report server-side
CPU, memory, and latency — independent of client-side measurement noise.

Usage:
    # Port-forward the metrics-service pod first:
    #   kubectl port-forward -n aap26-next <pod> 18002:8000 &
    # Then run:
    BASE_URL=http://localhost:18002/api \\
    BENCHMARK_USER=superadmin \\
    PASSWORD=superadmin123 \\
    METRICS_URL=http://localhost:18002/metrics \\
        python metrics_service/tools/performance_tests/http_benchmark.py

Environment variables:
    BASE_URL       Base URL of the metrics-service API (default: http://localhost:44926/api/metrics)
    BENCHMARK_USER Admin username (default: admin). Note: USERNAME is reserved in zsh
                   and cannot be overridden inline — use BENCHMARK_USER instead.
    PASSWORD       Password for the above user (default: empty)
    METRICS_URL    URL of the pod's Prometheus /metrics endpoint (optional)
                   Set up with: kubectl port-forward -n aap26-next <pod> 18002:8000
    CONCURRENCY    Number of concurrent workers for Phase 2 (default: 5)
    REQUESTS       Number of requests per endpoint in Phase 2 (default: 100)
"""

# ruff: noqa: T201
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.auth import HTTPBasicAuth

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL    = os.environ.get("BASE_URL", "http://localhost:44926/api/metrics").rstrip("/")
USERNAME    = os.environ.get("BENCHMARK_USER", os.environ.get("USERNAME", "admin"))
PASSWORD    = os.environ.get("PASSWORD", "")
METRICS_URL = os.environ.get("METRICS_URL", "")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "5"))
N_REQUESTS  = int(os.environ.get("REQUESTS", "100"))

# Endpoints to benchmark. Any that return 4xx/5xx are skipped automatically.
CANDIDATE_ENDPOINTS = [
    "/v1/",
    "/v1/organizations/",
    "/v1/teams/",
    "/v1/users/",
    "/v1/tasks/",
    "/v1/role_definitions/",
    "/v1/role_user_assignments/",
    "/v1/role_team_assignments/",
    "/v1/feature_flags/",
    "/v1/settings/",
]


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def get(path):
    """GET an endpoint with Basic auth. Returns (latency_ms, http_status_code)."""
    start = time.perf_counter()
    try:
        resp = requests.get(
            BASE_URL + path,
            auth=HTTPBasicAuth(USERNAME, PASSWORD),
            timeout=30,
        )
        return (time.perf_counter() - start) * 1000, resp.status_code
    except Exception as e:
        return (time.perf_counter() - start) * 1000, str(e)


def is_success(status):
    """Return True if the status code indicates a successful response."""
    return isinstance(status, int) and status < 400


# ---------------------------------------------------------------------------
# Prometheus helpers
# ---------------------------------------------------------------------------

def read_prometheus_metrics(url):
    """
    Fetch the Prometheus /metrics page and parse it into a plain dict.

    Prometheus exposes metrics as plain text, one metric per line:

        metric_name{optional_labels} value
        # lines starting with # are comments

    We store the full key (including any label brackets) mapped to its float
    value. Returns an empty dict if the URL is not configured or unreachable.
    """
    if not url:
        return {}
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
    except Exception:
        return {}

    result = {}
    for line in resp.text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            result[parts[0]] = float(parts[-1])
    return result


def prometheus_delta(before, after, key):
    """Return how much a Prometheus counter increased between two snapshots."""
    return after.get(key, 0) - before.get(key, 0)


# ---------------------------------------------------------------------------
# Benchmark phases
# ---------------------------------------------------------------------------

def probe_endpoints(candidates):
    """
    Send one request to each candidate endpoint and return only those that
    respond successfully.

    This filters out endpoints that don't exist (404) or that the current
    user isn't allowed to access (403), so the benchmark only runs against
    endpoints that are actually reachable.
    """
    print("\nProbing endpoints (skipping 4xx/5xx)...")
    available = []
    for path in candidates:
        ms, status = get(path)
        if is_success(status):
            print(f"  ✓ {path:<40} ({status}, {ms:.0f}ms)")
            available.append(path)
        else:
            print(f"  ✗ {path:<40} ({status}) — skipped")
    return available


def run_sequential_phase(endpoints):
    """
    Phase 1: Send 10 requests to each endpoint one at a time (no concurrency).

    Because each request waits for the previous one to finish, there is no
    queuing or thread contention. This gives a clean baseline — the closest
    we can get to the true cost of a single round-trip through the Django stack.

    Reports min, p50, p95, and max latency per endpoint.
    """
    print("\n" + "=" * 70)
    print("Phase 1: Sequential Latency (10 requests per endpoint)")
    print("=" * 70)

    all_results = {}
    for path in endpoints:
        latencies = []
        for _ in range(10):
            ms, status = get(path)
            if is_success(status):
                latencies.append(ms)

        all_results[path] = latencies
        if latencies:
            print(
                f"  {path:<40} "
                f"min={min(latencies):6.1f}ms  "
                f"p50={p50(latencies):6.1f}ms  "
                f"p95={p95(latencies):6.1f}ms  "
                f"max={max(latencies):6.1f}ms"
            )
        else:
            print(f"  {path:<40} ALL REQUESTS FAILED")

    return all_results


def run_load_phase(endpoints):
    """
    Phase 2: Send 100 requests to each endpoint across 5 concurrent workers.

    All 100 requests are submitted at once to a thread pool. Workers pick
    them up as they finish their previous request, so at any moment up to 5
    requests are in-flight simultaneously. This simulates multiple users
    hitting the service at the same time.

    Reports p50, p95, p99 latency and requests-per-second (RPS) per endpoint.

    Also snapshots the service's Prometheus /metrics before and after this
    phase. The difference (delta) isolates the resources consumed specifically
    by our benchmark — see print_server_metrics() for what gets reported.
    """
    print("\n" + "=" * 70)
    print(f"Phase 2: Concurrent Load ({N_REQUESTS} requests, {CONCURRENCY} workers)")
    print("=" * 70)

    metrics_before = read_prometheus_metrics(METRICS_URL)
    all_results = {}

    for path in endpoints:
        latencies = []
        start = time.perf_counter()

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = [pool.submit(get, path) for _ in range(N_REQUESTS)]
            for future in as_completed(futures):
                ms, status = future.result()
                if is_success(status):
                    latencies.append(ms)

        elapsed = time.perf_counter() - start
        all_results[path] = latencies

        if latencies:
            rps = len(latencies) / elapsed
            print(
                f"  {path:<40} "
                f"p50={p50(latencies):6.1f}ms  "
                f"p95={p95(latencies):6.1f}ms  "
                f"p99={p99(latencies):6.1f}ms  "
                f"rps={rps:5.1f}"
            )
        else:
            print(f"  {path:<40} ALL REQUESTS FAILED")

    metrics_after = read_prometheus_metrics(METRICS_URL)
    return all_results, metrics_before, metrics_after


def print_client_summary(sequential_results, load_results):
    """Print aggregate latency across all endpoints combined for each phase."""
    all_sequential = [ms for times in sequential_results.values() for ms in times]
    all_load       = [ms for times in load_results.values()       for ms in times]

    print("\n" + "=" * 70)
    print("Client-side Summary")
    print("=" * 70)
    if all_sequential:
        print(f"  Sequential — p50={p50(all_sequential):.1f}ms  p95={p95(all_sequential):.1f}ms  p99={p99(all_sequential):.1f}ms")
    if all_load:
        print(f"  Load       — p50={p50(all_load):.1f}ms  p95={p95(all_load):.1f}ms  p99={p99(all_load):.1f}ms")


def print_server_metrics(before, after):
    """
    Print server-side resource usage during Phase 2, derived from Prometheus.

    We subtract the 'before' snapshot from the 'after' snapshot so we only
    see activity caused by our benchmark, not anything counted before we started.

    Metrics reported:
      CPU time   — total CPU seconds consumed across all requests
      RSS memory — resident memory at end of phase (point-in-time, not a delta)
    """
    if not before or not after:
        return

    print("\n" + "=" * 70)
    print("Server-side Metrics (Prometheus delta across load phase)")
    print("=" * 70)

    cpu_seconds = prometheus_delta(before, after, "process_cpu_seconds_total")
    print(f"  CPU time used     : {cpu_seconds:>8.3f} s")

    rss_mb = after.get("process_resident_memory_bytes", 0) / 1024 / 1024
    print(f"  RSS memory (end)  : {rss_mb:>8.1f} MB")


# ---------------------------------------------------------------------------
# Percentile helpers
# ---------------------------------------------------------------------------

def p50(data): return statistics.quantiles(data, n=100)[49]
def p95(data): return statistics.quantiles(data, n=100)[94]
def p99(data): return statistics.quantiles(data, n=100)[98]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("Metrics Service HTTP Benchmark")
    print("=" * 70)
    print(f"  Target      : {BASE_URL}")
    print(f"  User        : {USERNAME}")
    print(f"  Workers     : {CONCURRENCY}")
    print(f"  Requests    : {N_REQUESTS} per endpoint (load phase)")
    print(f"  Auth        : Basic auth")
    print(f"  Prometheus  : {METRICS_URL or '(not configured — set METRICS_URL for server-side metrics)'}")

    # Verify the service is reachable before running the full benchmark.
    print("\nVerifying connectivity...")
    ms, status = get("/v1/")
    if not is_success(status):
        print(f"  ERROR: {BASE_URL}/v1/ returned {status}")
        print("  Check that aap-dev is running and PASSWORD is correct.")
        raise SystemExit(1)
    print(f"  OK ({status}, {ms:.0f}ms)")

    endpoints = probe_endpoints(CANDIDATE_ENDPOINTS)
    if not endpoints:
        print("\nNo reachable endpoints found. Exiting.")
        raise SystemExit(1)

    sequential_results = run_sequential_phase(endpoints)
    load_results, metrics_before, metrics_after = run_load_phase(endpoints)

    print_client_summary(sequential_results, load_results)
    print_server_metrics(metrics_before, metrics_after)
    print()


if __name__ == "__main__":
    main()
