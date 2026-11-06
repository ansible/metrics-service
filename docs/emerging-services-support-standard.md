# Emerging Services Support & Diagnostic Tooling Standard (v1.0)

Status: **Active** · Owner: AAP Emerging Services · Review: annually or on major platform change

The key words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are to be interpreted as described in RFC 2119.

## Scope

Every AAP Emerging Service that runs a long-lived process and/or background jobs. metrics-service is the reference implementation and the first service adopting the standard; the requirements below are outcome-based and deliberately framework-agnostic so a non-Django service (e.g. Go) can adopt them unchanged.

Each requirement states how it is verified. `check_support_standard.py` automates the **Automatic** rows; **Manual** rows need human evidence recorded in the service's evidence table.

## ES-SUP-1 — Health endpoint (MUST)

- The service MUST expose an unauthenticated HTTP `GET` endpoint at a stable path (recommended: `/health/`).
- It MUST return HTTP 200 when the service can serve requests and 503 when a critical dependency is unavailable.
- It MUST return JSON of the shape `{"status": "<good|degraded>", "checks": {"<dependency>": "<ok|error: ...>"}}`.
- It MUST check the primary datastore. It MAY check other critical dependencies.
- It MUST NOT include credentials, connection strings, or customer data in the response. A failing dependency is reported with a stable reason token (e.g. `error: database_unavailable`); the driver message is logged server-side only.
- It MUST be usable directly as a container/OpenShift liveness/readiness probe: no authentication, no redirects, response in under 5 seconds.
- Reference: metrics-service `GET /health/` — `apps/core/views/health.py`, `apps/core/urls.py`; status vocabulary comes from django-ansible-base (`ansible_base.lib.constants`, `good`/`degraded`).
- **Verification: Automatic** (HTTP code, JSON shape, response time, redirect/authentication behaviour, and a heuristic scan of the response for credential material).

## ES-SUP-2 — Log level via environment variable (MUST)

- The application log level MUST be controlled by one documented environment variable (recommended: `<SERVICE>_LOG_LEVEL`) accepting `DEBUG|INFO|WARNING|ERROR|CRITICAL`.
- ALL application loggers (service, framework, and third-party integration loggers) MUST honor it; no logger may be hard-coded above the configured level. This includes any background worker/runner component the service starts.
- Production output SHOULD be single-line JSON and MUST include timestamp, level, logger, and message.
- The variable MUST be documented (support guide) with its default.
- Reference: metrics-service `METRICS_SERVICE_LOG_LEVEL` (`metrics_service/settings.py`) — every logger in the framework `LOGGING` dict resolves to it, and the framework-owned `apps` logger is raised to it by the `apps_logger_follows_log_level` post-hook in `apps/settings/defaults.py` (the framework file hard-codes `INFO`, so the override cannot live there). The development overlay pins `apps.*` to `DEBUG` for local work, matching the other first-party loggers there. Background workers started by `manage.py run_dispatcherd` share the process and inherit the same logger configuration.
- **Verification: Mixed.** The presence of the variable in the support guide is **Automatic** (`--docs-path`). "Every logger honours it" is **Manual**: set the variable to `DEBUG`, capture one emitted log line, and record it as evidence (`--log-level-observed DEBUG`). The checker never reads the environment it runs in — that says nothing about the service under test.

## ES-SUP-3 — Task/job state visibility (MUST)

- The service MUST provide a read-only command or endpoint that reports, for background jobs:
  1. jobs currently running and their elapsed time;
  2. jobs exceeding the configured timeout ("stuck");
  3. last successful completion per job type;
  4. failure count per job type over a configurable recent window (default 24 h);
  5. queue/backlog depth.
- It MUST be safe to run against a live service (no locks, no writes).
- It SHOULD offer machine-readable JSON in addition to human-readable output.
- Key names are service-specific. A service that does not use the reference names supplies a mapping with `--diagnostics-map` (JSON: concept → list of key names, dotted paths allowed; `{window}` is substituted from `--failure-window`).
- Reference: `metrics-service tasks diagnose --format json` (AAP-79585).
- **Verification: Automatic** — all five concepts, against the mapped key names.

## ES-SUP-4 — Diagnostic bundle (SHOULD)

- The service SHOULD provide a redacted, timestamped archive of runtime state suitable for attaching to a support ticket.
- It MUST redact values whose key name contains `SECRET`, `PASSWORD`, `PASSWD`, `TOKEN`, `KEY`, `CREDENTIAL`, `AUTH`, or `PRIVATE` as a whole word (split on `_`, `-`, `.`, or camelCase), and MUST NOT include credential material in any other form (tokens, URL userinfo, private keys).
- Reference: metrics-service support bundle (AAP-79583).
- **Verification: Automatic** — the command must exit 0 and the produced bundle is scanned (key/value heuristic plus known token patterns). Pass `--bundle-path` alongside `--bundle-command`; without it the redaction row is reported `MANUAL`, never `PASS`.

## ES-SUP-5 — Documentation (MUST)

- The service MUST publish a support-engineer guide covering ES-SUP-1..3 with copy-paste commands and expected output, written for a reader with no knowledge of the codebase.
- Reference: `docs/support-tooling.md` (AAP-79586, PR #535).
- **Verification: Mixed.** File existence and coverage of ES-SUP-1..3 are **Automatic** (`--docs-path`). Coverage is accepted either as the literal rule ids `ES-SUP-1`/`ES-SUP-2`/`ES-SUP-3`, or as an "Emerging Services conformance" section that links this document — a guide may map its tools to the standard by name without repeating the ids. "Copy-paste commands with expected output, readable by a non-expert" is **Manual** review.

## Conformance

- **Required:** ES-SUP-1, ES-SUP-2, ES-SUP-3, ES-SUP-5. **Recommended:** ES-SUP-4.
- Conformance is demonstrated by running `tools/emerging-services/check_support_standard.py` against a running instance (see `tools/emerging-services/README.md`), recording an evidence table like the one below, and attaching the manual evidence for the `MANUAL` rows.
- A required requirement counts as verified only when every check for it passes. Omitted inputs are never treated as success: the checker exits `3` (`INCOMPLETE`) when a required requirement is unverified, distinct from `1` (`FAIL`).
- Each service keeps its own evidence table; re-verify on major version bumps and at the annual review.

## Evidence table — metrics-service (reference implementation)

On `devel` today only ES-SUP-1 and ES-SUP-2 are delivered: run the checker there and it exits `3`
(`INCOMPLETE`) because ES-SUP-3/4/5 arrive with the unmerged PRs below. Verified against the stacked
branches (`#530` `8183cf9`, `#531` `0aa25fc`, `#535` `44b2653`, with a live instance) every required
requirement passes and the checker exits `0`; the status column tracks merge state, not the checker's
verdict.

| Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| ES-SUP-1 | `apps/core/views/health.py`, `apps/core/urls.py` | `tests/unit/general/test_health_metrics.py`, `tests/coverage/core/test_core_views.py`; `curl -s http://localhost:8080/health/` | Delivered |
| ES-SUP-2 | `METRICS_SERVICE_LOG_LEVEL` (`metrics_service/settings.py`); `apps` logger raised by `apps_logger_follows_log_level` (`apps/settings/defaults.py`); dispatcherd worker inherits the same config (`apps/tasks/management/commands/run_dispatcherd.py`) | `tests/unit/general/test_log_level_settings.py`, `tests/unit/tasks/test_dispatcherd_config.py`, `tests/unit/tasks/test_run_dispatcherd_command.py`; `METRICS_SERVICE_LOG_LEVEL=DEBUG metrics-service serve` emits DEBUG lines from `apps.*` (manual) | Delivered |
| ES-SUP-3 | `metrics-service tasks diagnose --format json` (AAP-79585) | [PR #531](https://github.com/ansible/metrics-service/pull/531) | Pending merge |
| ES-SUP-4 | support bundle (AAP-79583) | [PR #530](https://github.com/ansible/metrics-service/pull/530) | Pending merge |
| ES-SUP-5 | `docs/support-tooling.md` (AAP-79586) | [PR #535](https://github.com/ansible/metrics-service/pull/535) | Pending merge |

### Schema change note — metrics-service (v1.0)

The OpenAPI enum for `GET /health/` was corrected from `healthy|unhealthy` to `good|degraded`
(`tools/openapi-schema/metrics-service.{yaml,json}`). This is a **breaking API-schema change** for
consumers that generated clients from the published spec: the previous enum never matched runtime
behaviour, which has emitted `good`/`degraded` since AAP-73682, so no live response changed. Regenerate
generated clients against the updated spec.
