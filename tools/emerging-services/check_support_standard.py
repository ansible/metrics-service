#!/usr/bin/env python3
"""Emerging Services support & diagnostic tooling conformance checker.

Checks a running service against the requirements in
docs/emerging-services-support-standard.md (ES-SUP-1..4).

Stdlib only on purpose: any Python 3 service can vendor this script
without adding dependencies. It must not import anything from the
service under test.

Usage:
    python check_support_standard.py \
        --base-url http://localhost:8080 \
        --health-path /health/ \
        --diagnostics-command "metrics-service tasks diagnose --format json" \
        --log-level-env METRICS_SERVICE_LOG_LEVEL

Exit code: 0 if all required checks PASS (SKIP allowed), 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

VALID_STATUSES = {"good", "degraded"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
DIAGNOSTICS_KEYS = {"stuck_tasks", "last_success", "failures_last_24h", "queue_depth"}
PROBE_TIMEOUT_SECONDS = 5.0
HTTP_TIMEOUT_SECONDS = 10.0


def _evaluate_health_payload(payload) -> list[tuple[str, str, str]]:
    """ES-SUP-1: validate a decoded health response body."""
    if not isinstance(payload, dict) or "status" not in payload or "checks" not in payload:
        return [("ES-SUP-1 JSON contract", "FAIL", f"missing status/checks keys: {payload}")]
    if payload["status"] not in VALID_STATUSES:
        return [
            ("ES-SUP-1 JSON contract", "FAIL", f"status {payload['status']!r} not in {sorted(VALID_STATUSES)}")
        ]
    if not isinstance(payload["checks"], dict) or not payload["checks"]:
        return [("ES-SUP-1 JSON contract", "FAIL", "'checks' must be a non-empty object")]
    return [
        ("ES-SUP-1 JSON contract", "PASS", f"status={payload['status']}, checks={list(payload['checks'])}")
    ]


def _evaluate_diagnostics_payload(payload) -> list[tuple[str, str, str]]:
    """ES-SUP-3: validate a decoded diagnostics JSON document."""
    if isinstance(payload, dict) and DIAGNOSTICS_KEYS.issubset(payload):
        return [("ES-SUP-3 diagnostics JSON", "PASS", f"JSON keys present: {sorted(DIAGNOSTICS_KEYS)}")]
    missing = DIAGNOSTICS_KEYS - set(payload if isinstance(payload, dict) else ())
    return [("ES-SUP-3 diagnostics JSON", "FAIL", f"JSON missing required concept keys: {sorted(missing)}")]


def check_health_endpoint(base_url: str, health_path: str) -> list[tuple[str, str, str]]:
    """ES-SUP-1: unauthenticated health endpoint returning the documented JSON contract."""
    results: list[tuple[str, str, str]] = []
    url = base_url.rstrip("/") + "/" + health_path.lstrip("/")
    started = time.monotonic()
    try:
        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
            status_code = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # unreachable, timeout, DNS failure, ...
        results.append(("ES-SUP-1 endpoint reachable", "FAIL", f"{url} could not be reached: {exc}"))
        return results
    elapsed = time.monotonic() - started

    if status_code not in (200, 503):
        results.append(("ES-SUP-1 endpoint reachable", "FAIL", f"expected HTTP 200 or 503, got {status_code}"))
    else:
        results.append(("ES-SUP-1 endpoint reachable", "PASS", f"HTTP {status_code} without authentication"))

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        results.append(("ES-SUP-1 JSON contract", "FAIL", f"response is not JSON: {body[:200]!r}"))
        return results
    results += _evaluate_health_payload(payload)

    if elapsed < PROBE_TIMEOUT_SECONDS:
        results.append(("ES-SUP-1 probe safety", "PASS", f"responded in {elapsed:.2f}s (< {PROBE_TIMEOUT_SECONDS}s)"))
    else:
        results.append(("ES-SUP-1 probe safety", "FAIL", f"responded in {elapsed:.2f}s (>= {PROBE_TIMEOUT_SECONDS}s)"))
    return results


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject redirects so the health endpoint can be a k8s probe target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


def check_log_level_env(log_level_env: str) -> list[tuple[str, str, str]]:
    """ES-SUP-2: the documented log-level env var holds an allowed value."""
    value = os.environ.get(log_level_env)
    if value is None:
        return [
            (
                "ES-SUP-2 log level env var",
                "SKIP",
                f"{log_level_env} is not set (informational; verify the documented default)",
            )
        ]
    if value.upper() in VALID_LOG_LEVELS:
        return [("ES-SUP-2 log level env var", "PASS", f"{log_level_env}={value}")]
    return [
        (
            "ES-SUP-2 log level env var",
            "FAIL",
            f"{log_level_env}={value!r} not in {sorted(VALID_LOG_LEVELS)}",
        )
    ]


def check_diagnostics_command(command: str) -> list[tuple[str, str, str]]:
    """ES-SUP-3: the diagnostics command runs and returns the documented JSON."""
    if not command:
        return [("ES-SUP-3 diagnostics command", "SKIP", "no --diagnostics-command supplied")]
    executable = command.split()[0]
    if shutil.which(executable) is None:
        return [("ES-SUP-3 diagnostics command", "FAIL", f"executable {executable!r} not found on PATH")]
    try:
        completed = subprocess.run(
            command,
            shell=True,  # noqa: S602 - operator-supplied command line
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [("ES-SUP-3 diagnostics command", "FAIL", "command timed out after 120s")]

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()[:200]
        return [("ES-SUP-3 diagnostics command", "FAIL", f"exit code {completed.returncode}: {stderr}")]
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return [("ES-SUP-3 diagnostics command", "FAIL", "stdout is not JSON")]

    results = [("ES-SUP-3 diagnostics command", "PASS", "command exited 0 with JSON output")]
    results += _evaluate_diagnostics_payload(payload)
    return results


def check_bundle_command(command: str) -> list[tuple[str, str, str]]:
    """ES-SUP-4 (optional): the diagnostic bundle command runs."""
    if not command:
        return [("ES-SUP-4 diagnostic bundle", "SKIP", "no --bundle-command supplied")]
    try:
        completed = subprocess.run(
            command,
            shell=True,  # noqa: S602 - operator-supplied command line
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [("ES-SUP-4 diagnostic bundle", "FAIL", "command timed out after 300s")]
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()[:200]
        return [("ES-SUP-4 diagnostic bundle", "FAIL", f"exit code {completed.returncode}: {stderr}")]
    return [("ES-SUP-4 diagnostic bundle", "PASS", "command exited 0")]


def format_results(results: list[tuple[str, str, str]]) -> str:
    width = max(len(name) for name, _, _ in results)
    lines = [f"{'CHECK':<{width}}  RESULT  DETAIL", "-" * (width + 30)]
    lines += [f"{name:<{width}}  {result:<6}  {detail}" for name, result, detail in results]
    return "\n".join(lines)


def evidence_snippet(results: list[tuple[str, str, str]], base_url: str) -> str:
    lines = [
        f"### Conformance evidence ({base_url})",
        "",
        "| Requirement | Result |",
        "|---|---|",
    ]
    for name, result, _ in results:
        lines.append(f"| {name} | {result} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True, help="Base URL of the running service")
    parser.add_argument("--health-path", default="/health/", help="Health endpoint path (default /health/)")
    parser.add_argument("--diagnostics-command", default="", help="Diagnostics command (ES-SUP-3), JSON output")
    parser.add_argument("--bundle-command", default="", help="Diagnostic bundle command (ES-SUP-4, optional)")
    parser.add_argument("--log-level-env", default="", help="Log level environment variable name (ES-SUP-2)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of a table")
    args = parser.parse_args(argv)

    results: list[tuple[str, str, str]] = []
    results += check_health_endpoint(args.base_url, args.health_path)
    if args.log_level_env:
        results += check_log_level_env(args.log_level_env)
    else:
        results.append(("ES-SUP-2 log level env var", "SKIP", "no --log-level-env supplied"))
    results += check_diagnostics_command(args.diagnostics_command)
    results += check_bundle_command(args.bundle_command)

    if args.json:
        print(json.dumps([{"check": n, "result": r, "detail": d} for n, r, d in results], indent=2))
    else:
        print(format_results(results))
        print()
        print(evidence_snippet(results, args.base_url))

    failed = [r for _, r, _ in results if r == "FAIL"]
    if failed:
        print(f"\n{len(failed)} check(s) FAILED", file=sys.stderr)
        return 1
    print("\nAll required checks passed (skipped optional checks are allowed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
