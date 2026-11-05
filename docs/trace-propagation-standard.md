# Emerging Services Trace Propagation Standard

> Story [AAP-79596](https://redhat.atlassian.net/browse/AAP-79596) · Parent epic
> [AAP-79579](https://redhat.atlassian.net/browse/AAP-79579) — Metrics Service:
> Cross-Service Trace Propagation.
>
> The normative reference implementation is metrics-service itself (see the
> [evidence table](#evidence-metrics-service-reference-implementation) below).

## Purpose

A support engineer investigating a failure must be able to follow one request
across service boundaries, async workers and outbound HTTP calls without
reading each service's source code. This standard defines the minimum
contract every AAP Emerging Service implements so that is true.

The contract is deliberately small and framework-neutral: it is about
**headers, request-scoped context, and one log field** — not about Django,
Celery, or any particular runtime. metrics-service (a Django service with a
PostgreSQL/dispatcherd task system) is the normative example, but a FastAPI,
Flask, Go or TypeScript service can conform by satisfying the same rules.

Key words MUST/SHOULD/MUST NOT are used per RFC 2119.

## S1 — Inbound header contract

| Rule | Requirement |
|------|-------------|
| S1.1 | Accept `X-Request-ID`. Value MUST be a UUID (any version). Header name matching is case-insensitive per HTTP semantics. |
| S1.2 | If absent or invalid, generate a UUIDv4. A request MUST NOT be rejected because the header is missing or malformed. |
| S1.3 | Never trust the value beyond validation: it MUST NOT be used for authorization, tenant resolution or routing. |
| S1.4 | Echo the effective ID on the response as `X-Request-ID`. |
| S1.5 | Accept `traceparent` (W3C Trace Context) if present and valid (version `00`, 32-hex trace-id, 16-hex span-id, 2-hex flags). Invalid values MUST be ignored silently (dropped, not repaired, and never forwarded). |

## S2 — Context rules

| Rule | Requirement |
|------|-------------|
| S2.1 | The effective ID MUST live in a request-scoped context (`contextvars.ContextVar` in Python, `AsyncLocalStorage` in Node, goroutine-local equivalents in Go) — not in a process global. |
| S2.2 | A helper (e.g. `current_request_id()`) MUST be the only way application code reads the ID. |
| S2.3 | Context MUST be re-established at every async boundary and reset in a `finally`/`defer` block so it cannot leak between requests, tasks or threads. |
| S2.4 | Services MUST NOT overwrite an ID that is already set in context. |

## S3 — Async work rules

| Rule | Requirement |
|------|-------------|
| S3.1 | Any work queued as a result of a request MUST carry the ID explicitly in the queue payload/arguments (or in a durable record the dispatcher reads). In-memory globals MUST NOT be relied on. |
| S3.2 | If the queue is mediated by a database row, the ID MUST be persisted on that row (nullable, indexed) rather than hidden in free-form payload JSON. |
| S3.3 | The consumer MUST read the ID from the payload first, fall back to the persisted record, and set context **before** the first log line. |
| S3.4 | Work with no request origin (cron, startup) MUST log an empty/absent ID rather than inventing one — unless the platform's tracing layer (OpenTelemetry, per the metrics-service ADR) supplies a trace ID, in which case that ID is used. |
| S3.5 | Chained work (a task enqueuing another task) MUST inherit the current context. |
| S3.6 | Retries MUST keep the originating ID. |

## S4 — Log field contract

| Rule | Requirement |
|------|-------------|
| S4.1 | Every log record MUST carry `request_id` (empty string when absent — never omitted in structured output, never `null`). |
| S4.2 | Text formatters MUST render the field (e.g. `[{request_id}]`); JSON formatters MUST emit it as a top-level `"request_id"` key. |
| S4.3 | The field MUST be attached by a logging filter/handler that applies to all application loggers, not by each call site. |
| S4.4 | Log messages MUST NOT interpolate the ID manually — the structured field is the contract. |
| S4.5 | Once OpenTelemetry is adopted, `trace_id`/`span_id` are added **alongside** `request_id`; `request_id` is not removed. |

## S5 — Outbound rules

| Rule | Requirement |
|------|-------------|
| S5.1 | Every outbound HTTP call MUST send `X-Request-ID` with the current effective ID when one exists. |
| S5.2 | If the inbound request carried a valid `traceparent`, outbound calls MUST forward it unchanged. Services MUST NOT synthesise a `traceparent` without a real span. |
| S5.3 | All outbound clients MUST go through one shared helper (e.g. `outbound_headers()`), not ad-hoc header dicts. |
| S5.4 | No ID in context ⇒ no header (never send an empty header value). |
| S5.5 | Headers MUST be added without logging or otherwise exposing authentication material. |

## S6 — Verification rules

| Rule | Requirement |
|------|-------------|
| S6.1 | Each service MUST have an automated test proving that API log records and async-worker log records share one ID (see [conformance test shape](#conformance-test-shape)). |
| S6.2 | Each service MUST document a manual log-search procedure by `request_id`. |
| S6.3 | The [conformance checklist](#conformance-checklist) MUST be referenced in the service's PR template or contribution guide. |

## Evidence: metrics-service reference implementation

The reference implementation is being delivered on three open pull requests.
Until they merge, the modules referenced below exist **only on those
branches**, not on `devel`. Rules marked *post-merge* are satisfied in the
code but only land on `devel` when the corresponding PR merges.

| Rule(s) | Reference (branch / PR) | Status |
|---------|--------------------------|--------|
| S1.1–S1.4 | `apps/core/middleware/request_id.py` — `RequestIdMiddleware` (validates UUID, generates UUIDv4, echoes on response) — branch `feat/aap-79587-request-id-task-payload` (PR #532) | Satisfied post-merge |
| S1.5, S5.2 | `apps/core/request_context.py` — `validate_traceparent()` (W3C v00 regex, rejects zero trace/span IDs, drops invalid values) — branch `feat/aap-79588-outbound-trace-headers` (PR #528) | Satisfied post-merge |
| S2.1–S2.3 | `apps/core/request_context.py` — `ContextVar`-backed `request_id_var`/`traceparent_var`, `request_context()` contextmanager that resets in `finally` — both branches; worker-side restore in `apps/tasks/tasks_system.py` (`execute_db_task`) on PR #532 | Satisfied post-merge |
| S2.2 | `apps/core/request_context.py` — `current_request_id()` / `current_traceparent()` — both branches | Satisfied post-merge |
| S3.1, S3.3 | `apps/tasks/tasks_system.py` — `submit_task_to_dispatcher()` includes `request_id` in the dispatcherd payload; `execute_db_task()` enters the context before the first log line — branch `feat/aap-79587-request-id-task-payload` (PR #532) | Satisfied post-merge |
| S3.2 | `apps/tasks/models.py` — nullable, indexed `Task.request_id` + migration `0005_task_request_id` — PR #532; consumer fallback to the persisted row is also implemented in `execute_db_task()` | Satisfied post-merge |
| S3.4 | Worker enters an empty context when no ID is present (cron-originated work) rather than minting one — PR #532 | Satisfied post-merge |
| S3.5 | Chained/child tasks inherit context because the ID is read from `current_request_id()` at submission time — PR #532 | Satisfied post-merge |
| S3.6 | Retries re-dispatch through `submit_task_to_dispatcher()` with the same persisted `Task.request_id` — PR #532 | Satisfied post-merge |
| S4.1–S4.4 | `apps/core/logging_filters.py` — project `RequestIdFilter` (extends DAB's filter, prefers the contextvar so worker processes are tagged) applied to all application loggers — PR #532 | Satisfied post-merge |
| S4.5 | OpenTelemetry deferred with rationale — ADR `docs/adr/0002-opentelemetry-trace-export.md` on branch `docs/aap-79589-opentelemetry-spike` (PR #529) | Documented post-merge |
| S5.1, S5.3, S5.4, S5.5 | `apps/core/request_context.py` — `outbound_headers()` (empty dict when no context; single shared helper); wired into the two outbound seams: DAB `ResourceAPIClient` via `apps/core/gateway_client.py` and metrics-utility `StorageSegment` in `apps/tasks/collectors/send_anonymized_to_segment.py` — branch `feat/aap-79588-outbound-trace-headers` (PR #528) | Satisfied post-merge |
| S6.1 | Regression tests: `tests/unit/tasks/test_request_id_propagation.py` (AAP-79590 shape, PR #532), `tests/unit/core/test_outbound_headers.py` (PR #528) | Satisfied post-merge |
| S6.2 | Manual log-search procedure | **Not yet satisfied** — follow-up; see [open items](#open-items) |
| S6.3 | Checklist referenced from contribution guide | Satisfied in this PR (`CONTRIBUTING.md` links this document) |

Implementation detail notes for adopters reading the reference code:

- The two implementation PRs (#532, #528) each carry a version of
  `apps/core/request_context.py`; they will be reconciled at merge time. The
  superset is the PR #528 version (adds `traceparent` validation and
  `outbound_headers()`); PR #532 additionally tags the context with an
  `origin` (`"http"`/`"worker"`) for diagnostics.
- The header contract and propagation behaviour is also described from the
  operator's point of view in `docs/trace-propagation.md` (created on both PR
  branches).

## Adoption guide

How another Emerging Service adopts this standard:

1. **Copy the reference modules** (vendor, do not import — the shared-package
   extraction is deliberately deferred until a second adopter exists):
   - `apps/core/request_context.py` — stdlib-only context helpers
     (`ContextVar`s, `normalize_request_id`, `validate_traceparent`,
     `current_request_id`, `outbound_headers`, `request_context`). Copy
     verbatim; it has no Django dependency.
   - `apps/core/middleware/request_id.py` (S1) — ~30 lines, Django-specific;
     FastAPI/Flask equivalents are trivial wrappers around the same helpers.
   - `apps/core/logging_filters.py` (S4) — `logging`-only; if you do not use
     django-ansible-base, drop the DAB parent class and set
     `record.request_id = current_request_id() or ""`.
2. **Wire it into the async boundary you actually have** (S3): add the ID to
   the queue payload/message attributes and restore it in the consumer before
   the first log line. If your queue is a DB row, add a nullable indexed
   `request_id` column like `Task.request_id`.
3. **Route outbound calls through `outbound_headers()`** (S5): one helper,
   used by every HTTP client seam. For third-party clients, attach it at the
   supported extension point (request hook / custom transport), not with a
   monkeypatch.
4. **Log the field once, centrally** (S4): a filter attached to all
   application loggers, plus the field in the text/JSON formatter.
5. **Run the conformance checklist** below in your first adoption PR and paste
   the result into the Jira ticket. Record deviations from the standard in the
   PR description and feed them back into this document.

### Conformance test shape

Derived from the AAP-79590 verification pattern (see
`tests/unit/tasks/test_request_id_propagation.py` on PR #532). Each service
implements an equivalent test, asserting *properties* (not metrics-service
imports):

1. **Inbound (S1)** — send a request with and without `X-Request-ID`; assert
   the response echoes a UUID (the sent one when valid, a generated one when
   absent/malformed); assert an invalid header never fails the request.
2. **Continuity (S3)** — trigger a request that queues async work; capture
   log records (or the log-context) from both the API handler and the worker;
   assert both carry the same `request_id`.
3. **Isolation (S2)** — run two interleaved requests; assert each context
   sees only its own ID and that context is empty after the request returns.
4. **Logs (S4)** — assert some handler on each application logger runs a
   filter that sets `request_id`, and that the rendered/structured output
   includes it.
5. **Outbound (S5)** — call `outbound_headers()` (or the equivalent seam)
   inside a restored context; assert the header dict contains the ID, that an
   absent context yields no headers, and that `traceparent` is only present
   when a valid one was inbound.

An executable, vendorable conformance suite
(`tests/unit/core/test_trace_standard.py`) is a follow-up item — it is being
deferred until PRs #532/#528 merge so it can be written against the
reconciled `apps/core/request_context.py` rather than a branch-local version.

## Conformance checklist

Reviewers walk this table against an adoption PR; the filled-in result is
pasted into the Jira ticket.

| # | Rule | Check | Pass |
|---|------|-------|------|
| S1.1 | Inbound UUID `X-Request-ID` accepted | | |
| S1.2 | Missing/invalid ID generates UUIDv4; request never rejected | | |
| S1.3 | ID not used for auth/tenant/routing | | |
| S1.4 | Effective ID echoed on response | | |
| S1.5 | Valid `traceparent` accepted; invalid dropped silently | | |
| S2.1 | ID in request-scoped context, not a global | | |
| S2.2 | Single accessor helper | | |
| S2.3 | Context set/reset (finally) at every async boundary | | |
| S2.4 | Existing context ID never overwritten | | |
| S3.1 | Queued work carries the ID explicitly | | |
| S3.2 | DB-mediated queues persist the ID on the row | | |
| S3.3 | Consumer sets context before first log line | | |
| S3.4 | No invented IDs for cron/startup work | | |
| S3.5 | Chained work inherits context | | |
| S3.6 | Retries keep the originating ID | | |
| S4.1 | Every record carries `request_id` (empty string, not null) | | |
| S4.2 | Field rendered in text and JSON formatters | | |
| S4.3 | Field attached by a filter on all app loggers | | |
| S4.4 | No manual interpolation of the ID in messages | | |
| S4.5 | OTel `trace_id`/`span_id` alongside, not replacing | | |
| S5.1 | Outbound calls send `X-Request-ID` | | |
| S5.2 | Valid inbound `traceparent` forwarded unchanged; never synthesised | | |
| S5.3 | One shared outbound header helper | | |
| S5.4 | No empty header when context is empty | | |
| S5.5 | No auth material exposed | | |
| S6.1 | Automated API↔worker continuity test exists | | |
| S6.2 | Manual log-search procedure documented | | |
| S6.3 | Checklist referenced in PR template / contribution guide | | |

## Open items

- **S6.2 (manual log-search procedure)** — a short runbook section (grep/CLM
  query by `request_id` across API, worker and scheduler processes) is not yet
  written for metrics-service; follow-up story.
- **Executable conformance suite** — deferred until PRs #532/#528 merge (see
  [conformance test shape](#conformance-test-shape)).
- **Shared package extraction** — deliberately deferred (Option B in the
  AAP-79596 plan) until a second service adopts; vendoring the four reference
  files is the sanctioned adoption path today.
- **Pilot Emerging Service** — not yet identified; see the story's open
  questions.

## Relationship to OpenTelemetry

`request_id` is the stable, always-present correlation key. OpenTelemetry
adoption for metrics-service is currently **deferred** — see the ADR on branch
`docs/aap-79589-opentelemetry-spike` (PR #529,
`docs/adr/0002-opentelemetry-trace-export.md`). When OTel is adopted, its
`trace_id`/`span_id` are added alongside `request_id` (S4.5); the two
standards do not diverge.
