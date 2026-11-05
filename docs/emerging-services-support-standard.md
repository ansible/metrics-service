# Emerging Services Support & Diagnostic Tooling Standard (v1.0)

Status: **Active** · Owner: AAP Emerging Services · Review: annually or on major platform change

The key words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are to be interpreted as described in RFC 2119.

## Scope

Every AAP Emerging Service that runs a long-lived process and/or background jobs. metrics-service is the reference implementation and the first conforming service; the requirements below are outcome-based and deliberately framework-agnostic so a non-Django service (e.g. Go) can adopt them unchanged.

## ES-SUP-1 — Health endpoint (MUST)

- The service MUST expose an unauthenticated HTTP `GET` endpoint at a stable path (recommended: `/health/`).
- It MUST return HTTP 200 when the service can serve requests and 503 when a critical dependency is unavailable.
- It MUST return JSON of the shape `{"status": "<good|degraded>", "checks": {"<dependency>": "<ok|error: ...>"}}`.
- It MUST check the primary datastore. It MAY check other critical dependencies.
- It MUST NOT include credentials, connection strings, or customer data in the response.
- It MUST be usable directly as a container/OpenShift liveness/readiness probe: no authentication, no redirects, response in under 5 seconds.
- Reference: metrics-service `GET /health/` — `apps/core/views/health.py`, `apps/core/urls.py`; status vocabulary comes from django-ansible-base (`ansible_base.lib.constants`, `good`/`degraded`).

## ES-SUP-2 — Log level via environment variable (MUST)

- The application log level MUST be controlled by one documented environment variable (recommended: `<SERVICE>_LOG_LEVEL`) accepting `DEBUG|INFO|WARNING|ERROR|CRITICAL`.
- ALL application loggers (service, framework, and third-party integration loggers) MUST honor it; no logger may be hard-coded above the configured level. This includes any background worker/runner component the service starts.
- Production output SHOULD be single-line JSON and MUST include timestamp, level, logger, and message.
- The variable MUST be documented (README or support guide) with its default.
- Reference: metrics-service `METRICS_SERVICE_LOG_LEVEL` (`metrics_service/settings.py`); dispatcherd's level is propagated from the same setting (`apps/tasks/dispatcherd_config.py`).

## ES-SUP-3 — Task/job state visibility (MUST)

- The service MUST provide a read-only command or endpoint that reports, for background jobs:
  1. jobs currently running and their elapsed time;
  2. jobs exceeding the configured timeout ("stuck");
  3. last successful completion per job type;
  4. failure count per job type over a configurable recent window (default 24 h);
  5. queue/backlog depth.
- It MUST be safe to run against a live service (no locks, no writes).
- It SHOULD offer machine-readable JSON in addition to human-readable output.
- Reference: `metrics-service tasks diagnose --format json` (AAP-79585). Other services may use different key names but must expose the five concepts above.

## ES-SUP-4 — Diagnostic bundle (SHOULD)

- The service SHOULD provide a redacted, timestamped archive of runtime state suitable for attaching to a support ticket.
- It MUST redact values whose keys contain `SECRET`, `PASSWORD`, `TOKEN`, `KEY`, `CREDENTIAL`, `AUTH`, or `PRIVATE`.
- Reference: metrics-service support bundle (AAP-79583).

## ES-SUP-5 — Documentation (MUST)

- The service MUST publish a support-engineer guide covering ES-SUP-1..3 with copy-paste commands and expected output, written for a reader with no knowledge of the codebase.
- Reference: `docs/support-tooling.md` (AAP-79586).

## Conformance

- **Required:** ES-SUP-1, ES-SUP-2, ES-SUP-3, ES-SUP-5. **Recommended:** ES-SUP-4.
- Conformance is demonstrated by running `tools/emerging-services/check_support_standard.py` against a running instance (see `tools/emerging-services/README.md`) and by recording an evidence table like the one below.
- Each service keeps its own evidence table; re-verify on major version bumps and at the annual review.

## Evidence table — metrics-service (reference implementation)

| Requirement | Implementation | Test | Demo command |
|---|---|---|---|
| ES-SUP-1 | `apps/core/views/health.py`, `apps/core/urls.py` | `tests/unit/general/test_health_metrics.py` | `curl -s http://localhost:8080/health/` |
| ES-SUP-2 | `METRICS_SERVICE_LOG_LEVEL` in `metrics_service/settings.py`; dispatcherd propagation in `apps/tasks/dispatcherd_config.py` | `tests/unit/general/test_log_level_settings.py`, `tests/unit/tasks/test_dispatcherd_config.py` | `METRICS_SERVICE_LOG_LEVEL=DEBUG metrics-service serve` (DEBUG lines from `apps.*`) |
| ES-SUP-3 | `metrics-service tasks diagnose` (AAP-79585) | tests delivered with AAP-79585 | `metrics-service tasks diagnose --format json` |
| ES-SUP-4 | support bundle (AAP-79583) | tests delivered with AAP-79583 | `metrics-service support-bundle --dry-run` |
| ES-SUP-5 | `docs/support-tooling.md` (AAP-79586) | — | open `docs/support-tooling.md` |
