#!/usr/bin/env python3
"""Emerging Services support & diagnostic tooling conformance checker.

Checks a service against the requirements in
docs/emerging-services-support-standard.md (ES-SUP-1..5).

Stdlib only on purpose: any Python 3 service can vendor this script
without adding dependencies. It must not import anything from the
service under test.

Usage:
    python check_support_standard.py \
        --base-url http://localhost:8080 \
        --health-path /health/ \
        --diagnostics-command "metrics-service tasks diagnose --format json" \
        --log-level-env METRICS_SERVICE_LOG_LEVEL \
        --log-level-observed DEBUG \
        --docs-path docs/support-tooling.md

Exit-code contract (frozen, see README.md):
    0  PASS        every required requirement is fully verified
    1  FAIL        at least one check failed
    2  USAGE       bad arguments (argparse)
    3  INCOMPLETE  nothing failed, but a required requirement lacks
                   machine-checkable evidence (SKIP/MANUAL)

A required requirement is only PASS when *every* row for it PASSes, so
omitting an input can never produce a green result. The checker never
reads the caller's environment to decide a conformance result.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import NamedTuple

CHECKER_VERSION = 1

VALID_STATUSES = {"good", "degraded"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

PROBE_TIMEOUT_SECONDS = 5.0
HTTP_TIMEOUT_SECONDS = 10.0
DIAGNOSTICS_TIMEOUT_SECONDS = 120
BUNDLE_TIMEOUT_SECONDS = 300
MAX_SCAN_BYTES = 2_000_000

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_INCOMPLETE = 3

REQUIRED_REQUIREMENTS = ("ES-SUP-1", "ES-SUP-2", "ES-SUP-3", "ES-SUP-5")
RECOMMENDED_REQUIREMENTS = ("ES-SUP-4",)

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIP = "SKIP"
STATUS_MANUAL = "MANUAL"
STATUS_INCOMPLETE = "INCOMPLETE"

# ES-SUP-3: the five mandated concepts and the key names each one may use.
# A service may override any entry with --diagnostics-map (JSON object of
# concept -> list of key names, dotted paths allowed). A candidate ending in
# ``*`` matches any sibling key with that prefix, so a service can version a
# section name (``failures_in_window``, ``failures_in_window_seconds``, ...)
# without losing coverage.
DIAGNOSTICS_CONCEPTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "running": (
        "jobs currently running and their elapsed time",
        (
            "running",
            "running_jobs",
            "running_tasks",
            "in_progress_jobs",
            "active_jobs",
            "current_jobs",
            # Falling back to evidence that carries the same information:
            # a stuck-task scan lists *running* tasks with duration_seconds,
            # and live dispatcherd worker state reports per-worker running jobs.
            "stuck_tasks",
            "queue_depth.dispatcherd_workers",
        ),
    ),
    "stuck": (
        "jobs exceeding the configured timeout",
        ("stuck", "stuck_tasks", "stuck_jobs", "timed_out_jobs"),
    ),
    "last_success": (
        "last successful completion per job type",
        ("last_success", "last_successful", "last_success_at", "last_ok"),
    ),
    "failures": (
        "failure count per job type over the recent window",
        (
            "failures_in_window",
            "failures_last_{window}h",
            "failures_last_24h",
            "failures",
            "recent_failures",
            "failure_counts",
            "failures*",
        ),
    ),
    "queue_depth": (
        "queue/backlog depth",
        ("queue_depth", "backlog", "queue_length", "pending_jobs"),
    ),
}

SENSITIVE_KEY_TOKENS = ("SECRET", "PASSWORD", "PASSWD", "TOKEN", "KEY", "CREDENTIAL", "AUTH", "PRIVATE")

#: Suffixes of keys that carry counters, budgets and metadata rather than
#: credentials. Mirrors ``apps/core/support_bundle/redaction.py`` (AAP-79583) so
#: the checker and the reference bundle agree on what a secret key is:
#: ``redacted_key_count``, ``key_count``, ``token_budget``, ``api_key_count``,
#: ``secret_scan_duration_ms`` and ``password_policy`` are diagnostic data, not
#: secrets, and a bundle that keeps them must not be reported as leaking.
SAFE_KEY_SUFFIXES = (
    "_count",
    "_counts",
    "_budget",
    "_ms",
    "_seconds",
    "_bytes",
    "_policy",
)

#: Values that never constitute credential material even under a suspicious key.
NON_CREDENTIAL_VALUES = {
    "true",
    "false",
    "yes",
    "no",
    "on",
    "off",
    "null",
    "none",
    "nil",
    "empty",
    "enabled",
    "disabled",
    "required",
    "optional",
    "default",
}

#: Values shorter than this are only reported when they also match a known
#: token pattern; a 1-3 character value cannot be a usable credential.
MIN_CREDENTIAL_LENGTH = 4

REDACTION_MARKERS = {
    "",
    "none",
    "null",
    "nil",
    "redacted",
    "hidden",
    "masked",
    "empty",
    "unset",
    "notset",
}
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe-key", re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{10,}\b")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("url-userinfo", re.compile(r"\b[a-z][a-z0-9+.-]*://[^:/\s@]+:[^@\s/]+@", re.IGNORECASE)),
    # ``Authorization: Bearer <token>`` / ``Basic <token>``. The reference
    # redactor (AAP-79583) rewrites the credential to ``Bearer **REDACTED**``,
    # which does not match the token character class below, so redacted headers
    # stay clean while a real one is reported.
    (
        "authorization-header",
        re.compile(
            r"\bauthorization\b[\"']?\s*[:=]\s*[\"']?(?:bearer|basic|token)?\s*[A-Za-z0-9._~+/=-]{8,}",
            re.IGNORECASE,
        ),
    ),
)
KEY_VALUE_RE = re.compile(
    r"(?P<key>\"[A-Za-z][A-Za-z0-9_.\-]{0,64}\"|[A-Za-z][A-Za-z0-9_.\-]{0,64})"
    r"\s*[:=]\s*(?P<value>\"[^\"\n]*\"|'[^'\n]*'|[^\s,;}\]]+)"
)

_MISSING = object()


class Result(NamedTuple):
    """One conformance finding. Requirement ids are stable, check text is not."""

    requirement: str
    check: str
    result: str
    detail: str

    @property
    def required(self) -> bool:
        return self.requirement in REQUIRED_REQUIREMENTS


# ---------------------------------------------------------------------------
# ES-SUP-1 — health endpoint
# ---------------------------------------------------------------------------
def _evaluate_health_payload(payload) -> list[Result]:
    """ES-SUP-1: validate a decoded health response body."""
    if not isinstance(payload, dict) or "status" not in payload or "checks" not in payload:
        return [Result("ES-SUP-1", "JSON contract", STATUS_FAIL, f"missing status/checks keys: {payload!r}")]
    if payload["status"] not in VALID_STATUSES:
        allowed = sorted(VALID_STATUSES)
        return [Result("ES-SUP-1", "JSON contract", STATUS_FAIL, f"status {payload['status']!r} not in {allowed}")]
    if not isinstance(payload["checks"], dict) or not payload["checks"]:
        return [Result("ES-SUP-1", "JSON contract", STATUS_FAIL, "'checks' must be a non-empty object")]
    return [
        Result(
            "ES-SUP-1", "JSON contract", STATUS_PASS, f"status={payload['status']}, checks={list(payload['checks'])}"
        )
    ]


def check_health_endpoint(base_url: str, health_path: str) -> list[Result]:
    """ES-SUP-1: unauthenticated health endpoint returning the documented JSON contract."""
    results: list[Result] = []
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
        results.append(Result("ES-SUP-1", "endpoint reachable", STATUS_FAIL, f"{url} could not be reached: {exc}"))
        return results
    elapsed = time.monotonic() - started

    if status_code not in (200, 503):
        results.append(
            Result("ES-SUP-1", "endpoint reachable", STATUS_FAIL, f"expected HTTP 200 or 503, got {status_code}")
        )
    else:
        results.append(
            Result("ES-SUP-1", "endpoint reachable", STATUS_PASS, f"HTTP {status_code} without authentication")
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        results.append(Result("ES-SUP-1", "JSON contract", STATUS_FAIL, f"response is not JSON: {body[:200]!r}"))
    else:
        results += _evaluate_health_payload(payload)

    hits = scan_text_for_secrets(body)
    if hits:
        results.append(Result("ES-SUP-1", "no credential material", STATUS_FAIL, "; ".join(hits[:3])))
    else:
        results.append(Result("ES-SUP-1", "no credential material", STATUS_PASS, "no tokens or URL userinfo found"))

    if elapsed < PROBE_TIMEOUT_SECONDS:
        results.append(Result("ES-SUP-1", "probe safety", STATUS_PASS, f"responded in {elapsed:.2f}s (< 5s)"))
    else:
        results.append(Result("ES-SUP-1", "probe safety", STATUS_FAIL, f"responded in {elapsed:.2f}s (>= 5s)"))
    return results


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject redirects so the health endpoint can be a k8s probe target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


# ---------------------------------------------------------------------------
# ES-SUP-2 — log level via environment variable
# ---------------------------------------------------------------------------
def check_log_level_contract(log_level_env: str, observed_level: str, docs_path: str) -> list[Result]:
    """ES-SUP-2: the variable is documented and its effect was observed.

    This never inspects the caller's environment: a variable exported in the
    shell running this script says nothing about the service under test.
    """
    if not log_level_env:
        return [
            Result("ES-SUP-2", "log level env var documented", STATUS_SKIP, "no --log-level-env supplied"),
            Result("ES-SUP-2", "log level effect observed", STATUS_SKIP, "no --log-level-env supplied"),
        ]

    results: list[Result] = []
    if not docs_path:
        results.append(
            Result(
                "ES-SUP-2",
                "log level env var documented",
                STATUS_SKIP,
                f"pass --docs-path to verify {log_level_env} is documented with its default",
            )
        )
    else:
        guide = Path(docs_path)
        if not guide.is_file():
            results.append(Result("ES-SUP-2", "log level env var documented", STATUS_FAIL, f"{guide} not found"))
        elif log_level_env in guide.read_text(encoding="utf-8", errors="replace"):
            results.append(
                Result("ES-SUP-2", "log level env var documented", STATUS_PASS, f"{log_level_env} in {guide}")
            )
        else:
            results.append(
                Result("ES-SUP-2", "log level env var documented", STATUS_FAIL, f"{log_level_env} not in {guide}")
            )

    if not observed_level:
        results.append(
            Result(
                "ES-SUP-2",
                "log level effect observed",
                STATUS_MANUAL,
                f"set {log_level_env}=DEBUG, capture one emitted log line, re-run with --log-level-observed DEBUG",
            )
        )
    elif str(observed_level).upper() in VALID_LOG_LEVELS:
        results.append(
            Result(
                "ES-SUP-2",
                "log level effect observed",
                STATUS_PASS,
                f"operator supplied log line level {str(observed_level).upper()}",
            )
        )
    else:
        results.append(
            Result(
                "ES-SUP-2",
                "log level effect observed",
                STATUS_FAIL,
                f"{observed_level!r} not in {sorted(VALID_LOG_LEVELS)}",
            )
        )
    return results


# ---------------------------------------------------------------------------
# ES-SUP-3 — task/job state visibility
# ---------------------------------------------------------------------------
def _resolve(payload, path: str):
    """Resolve a dotted key path against nested dicts, or return _MISSING.

    A trailing ``*`` matches any sibling key with that prefix, so a section that
    is versioned (``failures_in_window``) still satisfies a ``failures*``
    candidate.
    """
    if path.endswith("*"):
        parent_path, _, prefix = path[:-1].rpartition(".")
        parent = payload if not parent_path else _resolve(payload, parent_path)
        if not isinstance(parent, dict):
            return _MISSING
        for key in parent:
            if str(key).startswith(prefix):
                return parent[key]
        return _MISSING
    current = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _match_path(payload, path: str) -> str | None:
    """Return the concrete key path that satisfies *path*, or None.

    Handles the ``prefix*`` candidates in :data:`DIAGNOSTICS_CONCEPTS` by
    returning the sibling key that actually matched.
    """
    if not path.endswith("*"):
        return path if _resolve(payload, path) is not _MISSING else None
    parent_path, _, prefix = path[:-1].rpartition(".")
    parent = payload if not parent_path else _resolve(payload, parent_path)
    if not isinstance(parent, dict):
        return None
    for key in parent:
        if str(key).startswith(prefix):
            return f"{parent_path}.{key}" if parent_path else str(key)
    return None


def diagnostics_key_map(overrides: dict[str, object] | None = None) -> dict[str, tuple[str, ...]]:
    """Default concept -> key candidates, with per-concept overrides applied."""
    mapping = {concept: keys for concept, (_, keys) in DIAGNOSTICS_CONCEPTS.items()}
    for concept, value in (overrides or {}).items():
        if concept not in mapping:
            raise ValueError(f"unknown diagnostics concept {concept!r}; expected one of {sorted(mapping)}")
        keys = [value] if isinstance(value, str) else list(value)  # type: ignore[arg-type]
        if not keys or not all(isinstance(k, str) and k for k in keys):
            raise ValueError(f"diagnostics map for {concept!r} must be a non-empty list of key names")
        mapping[concept] = tuple(keys)
    return mapping


def _evaluate_diagnostics_payload(
    payload, key_map: dict[str, tuple[str, ...]] | None = None, window_hours: int = 24
) -> list[Result]:
    """ES-SUP-3: verify all five mandated concepts are present."""
    mapping = key_map or diagnostics_key_map()
    results: list[Result] = []
    for concept, (label, _) in DIAGNOSTICS_CONCEPTS.items():
        candidates = [key.format(window=window_hours) for key in mapping[concept]]
        found = next((match for path in candidates if (match := _match_path(payload, path))), None)
        if found:
            results.append(Result("ES-SUP-3", concept, STATUS_PASS, f"{label}: {found}"))
        else:
            results.append(Result("ES-SUP-3", concept, STATUS_FAIL, f"{label}: none of {candidates} present"))
    return results


def check_diagnostics_command(
    command: str, key_map: dict[str, tuple[str, ...]] | None = None, window_hours: int = 24
) -> list[Result]:
    """ES-SUP-3: the diagnostics command runs and returns the documented JSON."""
    if not command:
        return [Result("ES-SUP-3", "diagnostics command", STATUS_SKIP, "no --diagnostics-command supplied")]
    try:
        completed = subprocess.run(
            command,
            shell=True,  # noqa: S602 - operator-supplied command line
            capture_output=True,
            text=True,
            timeout=DIAGNOSTICS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [
            Result("ES-SUP-3", "diagnostics command", STATUS_FAIL, f"timed out after {DIAGNOSTICS_TIMEOUT_SECONDS}s")
        ]

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()[:200]
        return [Result("ES-SUP-3", "diagnostics command", STATUS_FAIL, f"exit code {completed.returncode}: {stderr}")]
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return [Result("ES-SUP-3", "diagnostics command", STATUS_FAIL, "stdout is not JSON")]

    results = [Result("ES-SUP-3", "diagnostics command", STATUS_PASS, "command exited 0 with JSON output")]
    results += _evaluate_diagnostics_payload(payload, key_map, window_hours)
    return results


# ---------------------------------------------------------------------------
# ES-SUP-4 — diagnostic bundle + redaction
# ---------------------------------------------------------------------------
def _is_sensitive_key(key: str) -> bool:
    """Return True when *key* names a credential rather than a counter or policy.

    Key segments (split on ``_``, ``-``, ``.`` and camelCase) are compared to
    :data:`SENSITIVE_KEY_TOKENS`, which avoids flagging ``monkey``/``author``.
    Counter and metadata suffixes in :data:`SAFE_KEY_SUFFIXES` win, mirroring the
    reference bundle's allow-list so that ``redacted_key_count``, ``key_count``
    and ``token_budget`` are not reported as leaks (AAP-79583).
    """
    cleaned = key.strip("\"'")
    if cleaned.lower().endswith(SAFE_KEY_SUFFIXES):
        return False
    segments = re.split(r"[._\-]|(?<=[a-z0-9])(?=[A-Z])", cleaned)
    return any(segment.upper() in SENSITIVE_KEY_TOKENS for segment in segments if segment)


def _is_redacted(value: str) -> bool:
    cleaned = value.strip().strip("\"'").strip().lower()
    if cleaned.startswith(("$", "{{", "<%", "vault:")):
        return True
    compact = re.sub(r"[^a-z0-9]", "", cleaned)
    return compact in REDACTION_MARKERS or (bool(compact) and set(compact) <= {"x"})


def _looks_like_credential(value: str) -> bool:
    """Return True when *value* could plausibly be a usable credential.

    A suspicious key name alone is not enough: a redacted, empty, boolean,
    numeric or configuration-shaped value (a dotted Python path, a URL without
    userinfo, an ENV-VAR-style name) carries no secret. This keeps the scan from
    flagging diagnostic metadata while still reporting real leaks.
    """
    cleaned = value.strip().strip("\"'").strip()
    if not cleaned or _is_redacted(cleaned):
        return False
    if cleaned.lower() in NON_CREDENTIAL_VALUES:
        return False
    # Numeric values are counters, budgets, ports, TTLs -- unless they are long
    # enough to be a key (``api_key = 1234567890`` stays reportable).
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
        return len(cleaned) >= 8
    # Configuration shapes that carry no secret: a dotted Python path / logger
    # name, a URL without userinfo (userinfo URLs are caught by SECRET_PATTERNS),
    # or an ENV-VAR-style *reference* (``${DB_PASSWORD}`` is caught above;
    # ``METRICS_SERVICE_DB_PASSWORD`` keeps its underscores). A bare uppercase
    # run such as ``ABCD1234`` or ``HUNTER2`` is NOT exempt -- that is a plausible
    # credential, so requiring an underscore keeps the exemption narrow.
    config_shaped = (
        bool(re.fullmatch(r"[A-Za-z_][\w.]*", cleaned) and "." in cleaned)
        or bool(re.match(r"^[a-z][a-z0-9+.\-]*://", cleaned, re.IGNORECASE))
        or bool(re.fullmatch(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+", cleaned))
    )
    if config_shaped:
        return False
    return len(cleaned) >= MIN_CREDENTIAL_LENGTH


def scan_text_for_secrets(text: str) -> list[str]:
    """ES-SUP-4: heuristic redaction scan.

    Returns human-readable hit descriptions that never contain the secret
    itself. Deliberately conservative: it reports key names and pattern
    names only, so failures are safe to paste into a ticket.
    """
    if not text:
        return []
    hits: list[str] = []
    for match in KEY_VALUE_RE.finditer(text[:MAX_SCAN_BYTES]):
        key = match.group("key").strip("\"'")
        if _is_sensitive_key(key) and _looks_like_credential(match.group("value")):
            hits.append(f"unredacted value for key {key!r}")
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text[:MAX_SCAN_BYTES]):
            hits.append(f"credential pattern {name!r}")
    return hits


def _read_bundle_text(bundle_path: str) -> tuple[str, str]:
    """Return (text, note) for a bundle file, archive, or directory."""
    path = Path(bundle_path)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")
    if path.is_dir():
        chunks = []
        for member in sorted(path.rglob("*")):
            if member.is_file() and member.stat().st_size <= MAX_SCAN_BYTES:
                chunks.append(member.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(chunks), f"scanned {len(chunks)} file(s) in {path}"
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            chunks = [
                archive.read(name).decode("utf-8", errors="replace")
                for name in archive.namelist()
                if archive.getinfo(name).file_size <= MAX_SCAN_BYTES
            ]
        return "\n".join(chunks), f"scanned {len(chunks)} member(s) in {path.name}"
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            chunks = []
            for info in archive.getmembers():
                handle = archive.extractfile(info) if info.isfile() else None
                if handle is not None and info.size <= MAX_SCAN_BYTES:
                    chunks.append(handle.read().decode("utf-8", errors="replace"))
        return "\n".join(chunks), f"scanned {len(chunks)} member(s) in {path.name}"
    return path.read_text(encoding="utf-8", errors="replace")[:MAX_SCAN_BYTES], f"scanned {path.name}"


def check_bundle_command(command: str, bundle_path: str = "") -> list[Result]:
    """ES-SUP-4 (recommended): the bundle command runs and its output is redacted."""
    if not command:
        return [Result("ES-SUP-4", "diagnostic bundle", STATUS_SKIP, "no --bundle-command supplied")]
    try:
        completed = subprocess.run(
            command,
            shell=True,  # noqa: S602 - operator-supplied command line
            capture_output=True,
            text=True,
            timeout=BUNDLE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [Result("ES-SUP-4", "diagnostic bundle", STATUS_FAIL, f"timed out after {BUNDLE_TIMEOUT_SECONDS}s")]
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()[:200]
        return [Result("ES-SUP-4", "diagnostic bundle", STATUS_FAIL, f"exit code {completed.returncode}: {stderr}")]

    results = [Result("ES-SUP-4", "diagnostic bundle", STATUS_PASS, "command exited 0")]

    if not bundle_path:
        results.append(
            Result(
                "ES-SUP-4",
                "bundle redaction",
                STATUS_MANUAL,
                "pass --bundle-path (file, archive, or directory) to scan the produced bundle for secrets",
            )
        )
        return results

    try:
        text, note = _read_bundle_text(bundle_path)
    except (OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
        results.append(Result("ES-SUP-4", "bundle redaction", STATUS_FAIL, f"could not read {bundle_path}: {exc}"))
        return results

    hits = scan_text_for_secrets(text)
    if hits:
        detail = f"{note}; " + "; ".join(hits[:5])
        results.append(Result("ES-SUP-4", "bundle redaction", STATUS_FAIL, detail))
    else:
        results.append(Result("ES-SUP-4", "bundle redaction", STATUS_PASS, f"{note}; no secret material found"))
    return results


# ---------------------------------------------------------------------------
# ES-SUP-5 — support documentation
# ---------------------------------------------------------------------------
STANDARD_DOC_NAME = "emerging-services-support-standard.md"
CONFORMANCE_HEADING = "emerging services conformance"


def check_docs(docs_path: str) -> list[Result]:
    """ES-SUP-5: a support guide exists and covers ES-SUP-1..3.

    Coverage is accepted in either of two forms, because the standard describes
    outcomes rather than a citation style:

    1. the rule ids ``ES-SUP-1``/``ES-SUP-2``/``ES-SUP-3`` appear in the guide; or
    2. the guide links to ``emerging-services-support-standard.md`` **and** has an
       "Emerging Services conformance" section naming the rules the documented
       tools satisfy.

    Form 2 exists because the reference guide (``docs/support-tooling.md``,
    AAP-79586 / PR #535) maps its tools to the standard by name and links it
    without repeating the ``ES-SUP-n`` identifiers inline.
    """
    if not docs_path:
        return [Result("ES-SUP-5", "support guide", STATUS_SKIP, "no --docs-path supplied")]
    guide = Path(docs_path)
    if not guide.is_file():
        return [Result("ES-SUP-5", "support guide", STATUS_FAIL, f"{guide} not found")]
    text = guide.read_text(encoding="utf-8", errors="replace").lower()
    results = [Result("ES-SUP-5", "support guide", STATUS_PASS, f"{guide} exists")]

    missing = [rule for rule in ("es-sup-1", "es-sup-2", "es-sup-3") if rule not in text]
    if not missing:
        results.append(Result("ES-SUP-5", "guide coverage", STATUS_PASS, "cites ES-SUP-1..3"))
        return results

    links_standard = STANDARD_DOC_NAME in text
    has_section = CONFORMANCE_HEADING in text
    if links_standard and has_section:
        results.append(
            Result(
                "ES-SUP-5",
                "guide coverage",
                STATUS_PASS,
                f"'{CONFORMANCE_HEADING}' section links {STANDARD_DOC_NAME}",
            )
        )
        return results

    reason = []
    if not links_standard:
        reason.append(f"no link to {STANDARD_DOC_NAME}")
    if not has_section:
        reason.append(f"no '{CONFORMANCE_HEADING}' section")
    results.append(
        Result(
            "ES-SUP-5",
            "guide coverage",
            STATUS_FAIL,
            f"guide covers none of {missing} and {' / '.join(reason)}",
        )
    )
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def requirement_verdicts(results: list[Result]) -> dict[str, str]:
    """Collapse rows into one verdict per requirement."""
    verdicts: dict[str, str] = {}
    for result in results:
        verdict = verdicts.get(result.requirement)
        if STATUS_FAIL in {result.result, verdict}:
            verdicts[result.requirement] = STATUS_FAIL
        elif {result.result, verdict} & {STATUS_SKIP, STATUS_MANUAL}:
            verdicts[result.requirement] = STATUS_INCOMPLETE
        else:
            verdicts[result.requirement] = STATUS_PASS
    return verdicts


def exit_code(results: list[Result]) -> int:
    """Apply the documented exit-code contract."""
    if any(result.result == STATUS_FAIL for result in results):
        return EXIT_FAIL
    verdicts = requirement_verdicts(results)
    for requirement in REQUIRED_REQUIREMENTS:
        if verdicts.get(requirement) != STATUS_PASS:
            return EXIT_INCOMPLETE
    return EXIT_PASS


def overall_verdict(code: int) -> str:
    return {EXIT_PASS: "pass", EXIT_FAIL: "fail", EXIT_INCOMPLETE: "incomplete"}.get(code, "fail")


def format_results(results: list[Result]) -> str:
    width = max((len(f"{r.requirement} {r.check}") for r in results), default=0)
    lines = [f"{'CHECK':<{width}}  RESULT  DETAIL", "-" * (width + 30)]
    for result in results:
        label = f"{result.requirement} {result.check}"
        lines.append(f"{label:<{width}}  {result.result:<6}  {result.detail}")
    return "\n".join(lines)


def evidence_snippet(results: list[Result], base_url: str) -> str:
    verdicts = requirement_verdicts(results)
    lines = [f"### Conformance evidence ({base_url})", "", "| Requirement | Result |", "|---|---|"]
    for requirement in sorted(verdicts):
        lines.append(f"| {requirement} | {verdicts[requirement]} |")
    lines += ["", "| Check | Result |", "|---|---|"]
    for result in results:
        lines.append(f"| {result.requirement} {result.check} | {result.result} |")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True, help="Base URL of the running service")
    parser.add_argument("--health-path", default="/health/", help="Health endpoint path (default /health/)")
    parser.add_argument("--diagnostics-command", default="", help="Diagnostics command (ES-SUP-3), JSON output")
    parser.add_argument("--bundle-command", default="", help="Diagnostic bundle command (ES-SUP-4, recommended)")
    parser.add_argument(
        "--bundle-path",
        default="",
        help="File, archive, or directory produced by --bundle-command, scanned for unredacted secrets",
    )
    parser.add_argument("--log-level-env", default="", help="Documented log level variable name (ES-SUP-2)")
    parser.add_argument(
        "--log-level-observed",
        default="",
        help="Level seen in a real log line after setting --log-level-env (ES-SUP-2 evidence)",
    )
    parser.add_argument("--docs-path", default="", help="Support guide to check (ES-SUP-2, ES-SUP-5)")
    parser.add_argument(
        "--diagnostics-map",
        default="",
        help="JSON file mapping ES-SUP-3 concept -> list of key names for services with custom output",
    )
    parser.add_argument(
        "--failure-window",
        type=int,
        default=24,
        help="Recent failure window in hours, substituted into {window} keys (default 24)",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of a table")
    return parser


def load_diagnostics_map(path: str) -> dict[str, tuple[str, ...]]:
    if not path:
        return diagnostics_key_map()
    try:
        overrides = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read --diagnostics-map {path}: {exc}") from exc
    if not isinstance(overrides, dict):
        raise ValueError("--diagnostics-map must contain a JSON object of concept -> key names")
    return diagnostics_key_map(overrides)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.failure_window < 1:
        parser.error("--failure-window must be a positive number of hours")
    try:
        key_map = load_diagnostics_map(args.diagnostics_map)
    except ValueError as exc:
        parser.error(str(exc))

    results: list[Result] = []
    results += check_health_endpoint(args.base_url, args.health_path)
    results += check_log_level_contract(args.log_level_env, args.log_level_observed, args.docs_path)
    results += check_diagnostics_command(args.diagnostics_command, key_map, args.failure_window)
    results += check_bundle_command(args.bundle_command, args.bundle_path)
    results += check_docs(args.docs_path)

    code = exit_code(results)

    if args.json:
        payload = {
            "version": CHECKER_VERSION,
            "overall": overall_verdict(code),
            "exit_code": code,
            "results": [
                {
                    "requirement": r.requirement,
                    "check": r.check,
                    "result": r.result,
                    "detail": r.detail,
                    "required": r.required,
                }
                for r in results
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_results(results))
        print()
        print(evidence_snippet(results, args.base_url))

    if code == EXIT_FAIL:
        failed = sum(1 for r in results if r.result == STATUS_FAIL)
        summary = f"\n{failed} check(s) FAILED"
    elif code == EXIT_INCOMPLETE:
        incomplete = [r for r in REQUIRED_REQUIREMENTS if requirement_verdicts(results).get(r) != STATUS_PASS]
        summary = f"\nINCOMPLETE: no failure, but required requirement(s) {incomplete} are not verified"
    else:
        summary = "\nAll required checks passed."

    # Keep stdout pure JSON for machine consumers; the human summary goes to stderr.
    print(summary, file=sys.stderr if args.json or code != EXIT_PASS else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
