# Emerging Services Trace Propagation Standard

> Story [AAP-79596](https://redhat.atlassian.net/browse/AAP-79596) · Parent epic
> [AAP-79579](https://redhat.atlassian.net/browse/AAP-79579) — Metrics Service:
> Cross-Service Trace Propagation.
>
> The normative reference implementation is metrics-service itself (see the
> [evidence table](#evidence-metrics-service-reference-implementation) below).
> Rules the reference implementation does not yet satisfy are listed in
> [Known gaps](#known-gaps) rather than silently implied.

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
| S1.5 | Accept `traceparent` (W3C Trace Context) when its shape is valid: `version`-`32-hex trace-id`-`16-hex span-id`-`2-hex flags`, lowercase hex, non-zero trace-id and span-id. Receivers MUST reject malformed values and the reserved version `ff`, and MUST accept unknown higher versions by parsing the first 55 characters (W3C Trace Context §3.2.2.2). Invalid values MUST be ignored silently — dropped, not repaired, and never forwarded. † |

† The metrics-service reference implementation conforms on this point:
`validate_traceparent()` (PR #532) accepts any version except the reserved
`ff`, normalises case and whitespace, rejects malformed values and all-zero
trace/span IDs, and forwards version-specific trailing fields rather than
dropping them. `RequestIdMiddleware` binds the validated value for the rest of
the request. The forward-compatibility behaviour is positively tested
(`test_accepts_future_versions_and_trailing_fields`).

S1.1 is deliberately strict because the reference implementation is
UUID-only: a non-UUID inbound value is replaced, never propagated. Adopters
that already emit non-UUID correlation IDs (for example `awx-…`) SHOULD send
a UUID in `X-Request-ID` and may carry the legacy ID in a separate header.

## S2 — Context rules

| Rule | Requirement |
|------|-------------|
| S2.1 | The effective ID MUST live in a request-scoped context (`contextvars.ContextVar` in Python, `AsyncLocalStorage` in Node, goroutine-local equivalents in Go) — not in a process global. |
| S2.2 | A helper (e.g. `current_request_id()`) MUST be the only way application code reads the ID. |
| S2.3 | Context MUST be re-established at every async boundary and reset in a `finally`/`defer` block so it cannot leak between requests, tasks or threads. |
| S2.4 | A consumer entry point MUST prefer the ID carried by the work item (payload, message attribute or persisted row) over any ambient ID, and MUST NOT clear an existing context ID when the work item carries none. † |

† The reference implementation violates the second clause:
`request_context()` sets `request_id_var` unconditionally (PR #532; #528
inherits the same file unchanged), so `request_context(None)` inside an
existing context clears it and a different ID replaces it. The only
"do not overwrite" guard is caller-local in `apps/tasks/tasks_system.py`
("if `current_request_id()` is `None`"), and no test covers the
"payload carries no ID ⇒ keep the ambient one" clause. See
[Known gaps](#known-gaps).

## S3 — Async work rules

| Rule | Requirement |
|------|-------------|
| S3.1 | Any work queued as a result of a request MUST carry the ID explicitly in the queue payload/arguments (or in a durable record the dispatcher reads). In-memory globals MUST NOT be relied on. |
| S3.2 | If the queue is mediated by a database row, the ID MUST be persisted on that row (nullable, indexed) rather than hidden in free-form payload JSON. |
| S3.3 | The consumer MUST read the ID from the payload first, fall back to the persisted record, and set context **before** the first log line. |
| S3.4 | Work with no request origin (cron, startup) MUST log an empty/absent ID rather than inventing one — unless the platform's tracing layer (OpenTelemetry, per the metrics-service ADR on PR #529, which is not merged) supplies a trace ID, in which case that ID is used. |
| S3.5 | Chained work (a task enqueuing another task) MUST inherit the current context. |
| S3.6 | Retries MUST keep the originating ID. |

## S4 — Log field contract

| Rule | Requirement |
|------|-------------|
| S4.1 | Every log record MUST carry `request_id` (empty string when absent — never omitted in structured output, never `null`). |
| S4.2 | Text formatters MUST render the field (e.g. `[{request_id}]`). A service that emits JSON logs MUST include `request_id` as a top-level key. ‡ |
| S4.3 | The field MUST be attached by a logging filter/handler that applies to all application loggers, not by each call site. |
| S4.4 | Log messages MUST NOT interpolate the ID manually — the structured field is the contract. |
| S4.5 | Once OpenTelemetry is adopted, `trace_id`/`span_id` are added **alongside** `request_id`; `request_id` is not removed. |

‡ metrics-service satisfies both clauses. Text: the `verbose` formatter renders
`[{request_id}]`. JSON: `apps/core/logging_config.JsonFormatter` already exists
on `devel` and adds `request_id` as a top-level key; the
`setup_json_logging_for_production` post-hook installs it whenever
`METRICS_SERVICE_MODE=production` or `METRICS_SERVICE_LOG_FORMAT=json`, so
production logs are JSON by default. One caveat bears on S4.1 rather than the
formatter's capability: it emits the key only when the effective ID is non-empty,
so a record whose ID is `""` loses the key in JSON output instead of rendering
it as an empty string — see [Known gaps](#known-gaps).

## S5 — Outbound rules

| Rule | Requirement |
|------|-------------|
| S5.1 | Every outbound HTTP call MUST send `X-Request-ID` with the current effective ID when one exists. |
| S5.2 | If the inbound request carried a valid `traceparent`, outbound calls MUST forward it unchanged. Services MUST NOT synthesise a `traceparent` without a real span. Version acceptance follows S1.5. † |
| S5.3 | All outbound clients MUST go through one shared helper (e.g. `outbound_headers()`), not ad-hoc header dicts. |
| S5.4 | No ID in context ⇒ no header (never send an empty header value). |
| S5.5 | Headers MUST be added without logging or otherwise exposing authentication material. |

† See the footnote under S1.5: the reference implementation accepts any
`traceparent` version except `ff`, forwards version-specific trailing fields,
and passes a validated inbound value through `outbound_headers()` unchanged
(case-normalised). It never synthesises one.

## S6 — Verification rules

| Rule | Requirement |
|------|-------------|
| S6.1 | Each service MUST have an automated test proving that API log records and async-worker log records share one ID (see [conformance test shape](#conformance-test-shape)). Where the async hop crosses a process boundary, at least one test MUST execute that boundary — a mocked queue is not sufficient. † |
| S6.2 | Each service MUST document a manual log-search procedure by `request_id`. |
| S6.3 | The [conformance checklist](#conformance-checklist) MUST be referenced in the service's PR template or contribution guide. |

† PR #536 supplies in-process Tier 1 and Tier 2 tests that run on every PR,
but its cross-process Tier 3 test requires `TRACE_E2E=1`, which no CI workflow
sets — so the process boundary is never executed in CI today. See
[Known gaps](#known-gaps).

## Evidence: metrics-service reference implementation

The reference implementation is being delivered on three open pull requests,
plus an OpenTelemetry ADR PR that is not merged. Until the code PRs merge, the
modules and tests referenced below exist **only on those branches**, not on
`devel`; the ADR file does not exist on `devel` at all:

| PR | Branch | Scope | Example symbol |
|----|--------|-------|----------------|
| [#532](https://github.com/ansible/metrics-service/pull/532) | `feat/aap-79587-request-id-task-payload` | UUID validation/generation, request middleware (`X-Request-ID` + inbound `traceparent`), context vars, `Task.request_id`, dispatcher payload, logging filter, canonical `request_context.py` | `request_id_var`, `traceparent_var`, `validate_traceparent`, `outbound_headers` |
| [#528](https://github.com/ansible/metrics-service/pull/528) | `feat/aap-79588-outbound-trace-headers` | Outbound wiring only: Gateway client subclass, Segment sender, resource-sync call site; outbound sections of the operator doc | `create_traced_api_client`, `outbound_headers` |
| [#529](https://github.com/ansible/metrics-service/pull/529) | `docs/aap-79589-opentelemetry-spike` | OpenTelemetry feasibility ADR (**not merged**; `docs/adr/` is absent from `devel`) | `docs/adr/0002-opentelemetry-trace-export.md` (branch only) |
| [#536](https://github.com/ansible/metrics-service/pull/536) | `feat/aap-79590-trace-continuity` | Conformance suite: Tier 1/2 CI tests, opt-in Tier 3, manual runbook | `tests/unit/tasks/test_trace_continuity.py` |

Status values below describe the code on the branch, not `devel`. Rules marked
*after #NNN merges* are implemented but only land when that PR lands.

| Rule(s) | Reference (branch / PR) | Status | Verified by |
|---------|--------------------------|--------|-------------|
| S1.1–S1.4 | `apps/core/middleware/request_id.py` — `RequestIdMiddleware` (validates UUID, generates UUIDv4, echoes on response) — PR #532 | Satisfied after #532 merges | `tests/unit/core/test_request_id_middleware.py`; Tier 1 on #536 |
| S1.5, S5.2 | `apps/core/request_context.py` — `validate_traceparent()` accepts any version except the reserved `ff`, normalises case/whitespace, rejects malformed values and all-zero trace/span IDs, and forwards version-specific trailing fields (W3C Trace Context §3.2.2.2). `RequestIdMiddleware` binds a valid inbound value (PR #532) and `outbound_headers()` forwards it unchanged (PR #528) | Satisfied after #532 and #528 merge | `tests/unit/core/test_request_context.py` — `TestValidateTraceparent::test_accepts_future_versions_and_trailing_fields` and `TestOutboundHeaders::test_future_version_traceparent_reaches_outbound_headers` (#528); `test_request_id_middleware.py::test_binds_valid_traceparent` (#532) |
| S2.1–S2.3 | `apps/core/request_context.py` — `ContextVar`-backed `request_context()` contextmanager that resets every variable in `finally`; worker-side restore in `apps/tasks/tasks_system.py` (`execute_db_task`) on PR #532 | Satisfied after #532 merges | `tests/unit/core/test_request_context.py`; `test_request_id_middleware.py`; Tier 1 on #536 |
| S2.2 | `apps/core/request_context.py` — `current_request_id()` and `current_traceparent()` are the read helpers (PR #532) | Satisfied after #532 merges (no test enforces the accessor; review-only) | none — review-only |
| S2.4 | Worker prefers the payload ID via a caller-local guard in `execute_db_task()` (PR #532); `request_context()` itself always overwrites, so an empty payload ID clears an ambient context | **Not satisfied** | none — see [Known gaps](#known-gaps) |
| S3.1, S3.3 | `apps/tasks/tasks_system.py` — `submit_task_to_dispatcher()` includes `request_id` in the dispatcherd payload; `execute_db_task()` enters the context before the first log line — PR #532 | Satisfied after #532 merges | Tier 1 on #536 |
| S3.2 | `apps/tasks/models.py` — nullable, indexed `Task.request_id` + migration `0005_task_request_id` — PR #532; consumer fallback to the persisted row is also implemented in `execute_db_task()` | Satisfied after #532 merges | `tests/unit/tasks/test_models.py` |
| S3.4 | Worker enters an empty context when no ID is present (cron-originated work) rather than minting one — PR #532 | Satisfied after #532 merges | Tier 1 `test_no_request_context_yields_empty_id` on #536 |
| S3.5 | Chained/child tasks inherit context because the ID is read from `current_request_id()` at submission time — PR #532 | Satisfied after #532 merges | Tier 1 `test_chained_task_inherits_request_id` on #536 |
| S3.6 | Retries re-dispatch through `submit_task_to_dispatcher()` with the same persisted `Task.request_id` — PR #532 | Satisfied after #532 merges | Tier 1 `test_retry_keeps_original_request_id` on #536 |
| S4.1, S4.3 | `apps/core/logging_filters.py` — project `RequestIdFilter` (extends DAB's filter, prefers the contextvar so worker processes are tagged) — PR #532 | Satisfied after #532 merges; see the JSON empty-ID caveat under S4.2 | `tests/unit/core/test_request_id_logging_config.py` (asserts resolved settings, not source text); Tier 1 on #536 |
| S4.2 | Text: `LOGGING["formatters"]["verbose"]` renders `[{request_id}]`. JSON: `apps/core/logging_config.JsonFormatter` (pre-existing on `devel`) emits `request_id` as a top-level key; the `setup_json_logging_for_production` post-hook installs it when `METRICS_SERVICE_MODE=production` or `METRICS_SERVICE_LOG_FORMAT=json` | Satisfied — text on #532, JSON already on `devel` | `test_request_id_logging_config.py` (formatter wiring); `tests/unit/test_settings_post_hooks.py` (enablement); `tests/coverage/general/test_misc_coverage.py::test_json_formatter_with_request_id` (rendered output) |
| S4.4 | No mechanism prevents manual interpolation | **Not verified** | none |
| S4.5 | OpenTelemetry deferred with rationale — ADR `docs/adr/0002-opentelemetry-trace-export.md` exists only on branch `docs/aap-79589-opentelemetry-spike` (PR #529, not merged) | **Unevidenced** — `docs/adr/` does not exist on `devel`, so S4.5 cannot be verified | ADR text in PR #529 (not on `devel`) |
| S5.1, S5.3–S5.5 | `apps/core/request_context.py` — `outbound_headers()` (empty dict when no context; single shared helper); wired into the two outbound seams: DAB `ResourceAPIClient` via `apps/core/gateway_client.py` and metrics-utility `StorageSegment` in `apps/tasks/collectors/send_anonymized_to_segment.py` — PR #528 | Satisfied after #528 merges for S5.1/S5.3/S5.4; S5.5 **partial** (no leak-specific assertion) | `tests/unit/core/test_request_context.py::TestOutboundHeaders`; `test_gateway_client.py`; `test_send_anonymized_to_segment_headers.py` |
| S6.1 | Conformance suite — PR #536: 8 Tier 1 tests (`tests/unit/tasks/test_trace_continuity.py`), 2 Tier 2 scheduler tests (`test_trace_continuity_scheduler.py`), opt-in Tier 3 (`tests/integration/test_trace_continuity_process.py`). PR #532's `tests/unit/tasks/test_request_id_propagation.py` is an earlier, in-process-only proof. | Partially satisfied after #536 merges (Tier 3 never runs in CI) | see [Known gaps](#known-gaps) |
| S6.2 | Manual log-search runbook added in `docs/trace-propagation.md` §"Manual (deployed instance)" — PR #536 | Satisfied after #536 merges | runbook on #536 |
| S6.3 | Checklist referenced from contribution guide | Satisfied in this PR (`CONTRIBUTING.md` links this document) | `CONTRIBUTING.md` |

Implementation detail notes for adopters reading the reference code:

- There is **one** `apps/core/request_context.py`. PR #532's commit
  `ed634f1` widened it to the canonical trace-aware API — `request_id_var`,
  `traceparent_var`, `origin_var`, `normalize_request_id`,
  `validate_traceparent()`, `current_request_id()`, `current_traceparent()`,
  `outbound_headers()` and `request_context()`. PR #528 was then rebuilt on
  #532's tip (`9780bf1`) and its former duplicate copy of the module is gone:
  #528's own diff is 9 files and touches neither `request_context.py`, the
  middleware, nor the logging filter. It adds only the outbound wiring.
- The stack is therefore linear: #532 is an ancestor of #528, and #536 is
  built on the same #532 tip. Merging #532 → #528 → #536 is a clean
  fast-forward chain (verified with `git merge-tree`); no add/add
  reconciliation of `request_context.py` is needed. Do **not** vendor an
  older branch-local copy of the file — take #532's version, which already
  carries every symbol both sides need, so `origin_var` and the
  `traceparent_var` reset are preserved automatically (both asserted in
  `tests/unit/core/test_request_context.py`).
- `docs/trace-propagation.md` is revised independently by #532, #528 and
  #536. #528's revision is stacked on #532's and #536 appends the
  verification sections, so the operator-facing document after the three
  merge is the union — not any single branch copy.

## Adoption guide

How another Emerging Service adopts this standard:

1. **Copy the reference modules** (vendor, do not import — the shared-package
   extraction is deliberately deferred until a second adopter exists):
   - `apps/core/request_context.py` — stdlib-only context helpers
     (`ContextVar`s, `normalize_request_id`, `validate_traceparent`,
     `current_request_id`, `outbound_headers`, `request_context`). Copy
     verbatim from #532, which already carries the canonical trace-aware API
     (#528 does not modify it); it has no Django dependency. Use the merged
     `devel` version once the stack lands.
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
   application loggers, plus the field in the text formatter (and the JSON
   formatter if you emit JSON).
5. **Run the conformance checklist** below in your first adoption PR and paste
   the result into the Jira ticket. Record deviations from the standard in the
   PR description and feed them back into this document.

### Conformance test shape

Derived from the PR #536 verification pattern (Tier 1
`tests/unit/tasks/test_trace_continuity.py`, Tier 2
`test_trace_continuity_scheduler.py`, Tier 3
`tests/integration/test_trace_continuity_process.py`). PR #532's
`tests/unit/tasks/test_request_id_propagation.py` is the same idea but
in-process only. Each service implements an equivalent test, asserting
*properties* (not metrics-service imports):

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
   includes it. Assert rendered output, not the configuration source text.
5. **Outbound (S5)** — call `outbound_headers()` (or the equivalent seam)
   inside a restored context; assert the header dict contains the ID, that an
   absent context yields no headers, and that `traceparent` is only present
   when a valid one was inbound.
6. **Process boundary (S6.1)** — if the queue crosses a process boundary,
   run at least one test that starts the real consumer and asserts the ID in
   its own output. Do not require an environment variable that CI never sets.

An executable, vendorable conformance suite
(`tests/unit/core/test_trace_standard.py`) is a follow-up item — it is being
deferred until PRs #532/#528 merge so it can be written against the merged
`apps/core/request_context.py` rather than a branch-local version.

## Conformance checklist

Reviewers walk this table against an adoption PR; the filled-in result is
pasted into the Jira ticket. "Reference status" describes metrics-service
today (on the PR branches); "Verification" names the test that proves it, or
`none` when the rule is review-only or unverified.

| Rule | Check | Reference status | Verification | Pass |
|------|-------|------------------|--------------|------|
| S1.1 | Inbound UUID `X-Request-ID` accepted | Satisfied after #532 merges | `test_request_id_middleware.py` | |
| S1.2 | Missing/invalid ID generates UUIDv4; request never rejected | Satisfied after #532 merges | `test_request_id_middleware.py` | |
| S1.3 | ID not used for auth/tenant/routing | Satisfied (by construction) | none — review-only | |
| S1.4 | Effective ID echoed on response | Satisfied after #532 merges | `test_request_id_middleware.py`; Tier 1 | |
| S1.5 | `traceparent` accepted when valid; invalid dropped silently | Satisfied after #532 merges (any version except `ff`) | `test_request_context.py` (`TestValidateTraceparent`); `test_request_id_middleware.py` | |
| S2.1 | ID in request-scoped context, not a global | Satisfied after #532 merges | `test_request_context.py` | |
| S2.2 | Single accessor helper | Satisfied after #532 merges | none — review-only | |
| S2.3 | Context set/reset (finally) at every async boundary | Satisfied after #532 merges | Tier 1; cross-process reset only in opt-in Tier 3 | |
| S2.4 | Existing context ID never overwritten | **Not satisfied** | none | |
| S3.1 | Queued work carries the ID explicitly | Satisfied after #532 merges | Tier 1 payload assertion | |
| S3.2 | DB-mediated queues persist the ID on the row | Satisfied after #532 merges | `test_models.py` | |
| S3.3 | Consumer sets context before first log line | Satisfied after #532 merges | Tier 1 | |
| S3.4 | No invented IDs for cron/startup work | Satisfied after #532 merges | Tier 1 `test_no_request_context_yields_empty_id` | |
| S3.5 | Chained work inherits context | Satisfied after #532 merges | Tier 1 `test_chained_task_inherits_request_id` | |
| S3.6 | Retries keep the originating ID | Satisfied after #532 merges | Tier 1 `test_retry_keeps_original_request_id` | |
| S4.1 | Every record carries `request_id` (empty string, not null) | Satisfied after #532 merges (text); JSON omits an empty ID — gap 2 | Tier 1 `test_no_request_context_yields_empty_id` | |
| S4.2 | Field rendered in text and JSON formatters | Satisfied — text on #532; JSON formatter already on `devel` | `test_request_id_logging_config.py`; `test_json_formatter_with_request_id` | |
| S4.3 | Field attached by a filter on all app loggers | Satisfied after #532 merges | `test_request_id_logging_config.py` (resolved settings) | |
| S4.4 | No manual interpolation of the ID in messages | **Not verified** | none | |
| S4.5 | OTel `trace_id`/`span_id` alongside, not replacing | **Unevidenced** — ADR not merged | ADR text in PR #529 (not on `devel`) | |
| S5.1 | Outbound calls send `X-Request-ID` | Satisfied after #528 merges | `test_request_context.py` (`TestOutboundHeaders`); `test_gateway_client.py`; `test_send_anonymized_to_segment_headers.py` | |
| S5.2 | Valid inbound `traceparent` forwarded unchanged; never synthesised | Satisfied after #528 merges | `test_request_context.py` (`test_future_version_traceparent_reaches_outbound_headers`) | |
| S5.3 | One shared outbound header helper | Satisfied after #528 merges | grep + 3 test files | |
| S5.4 | No empty header when context is empty | Satisfied after #528 merges | `TestOutboundHeaders::test_empty_without_context` | |
| S5.5 | No auth material exposed | Partial — no leak-specific assertion | `test_gateway_client.py` (header merge) | |
| S6.1 | Automated API↔worker continuity test exists | Partial — cross-process Tier 3 never runs in CI | Tier 1/2 on #536 | |
| S6.2 | Manual log-search procedure documented | Satisfied after #536 merges | runbook on #536 | |
| S6.3 | Checklist referenced in PR template / contribution guide | Satisfied in this PR | `CONTRIBUTING.md` | |

## Known gaps

These are open deviations of the metrics-service reference implementation from
this standard, plus verification gaps. They are follow-ups, not exemptions:
new code MUST still satisfy the rule.

| # | Rule | Gap | Follow-up |
|---|------|-----|-----------|
| 1 | S2.4 | `request_context()` sets `request_id_var` unconditionally (PR #532; #528 inherits the same file), so `request_context(None)` inside an existing context clears it, and a different ID replaces it — `TestRequestContext::test_context_nests_and_restores` asserts that replacement as intended. The only "do not overwrite" guard is caller-local in `execute_db_task()`'s error path, and no test covers the "payload carries no ID ⇒ keep the ambient one" clause. | Add the "do not overwrite with empty" guard in `request_context()`, plus a unit test; or narrow the rule to the consumer-entry-point preference only. |
| 2 | S4.1 (JSON output) | `apps/core/logging_config.JsonFormatter` emits a top-level `request_id` only when it is truthy (`if getattr(record, "request_id", None)`), so a record whose effective ID is empty loses the key in JSON output. S4.1 requires the field as an empty string, never omitted, in structured output. | Emit the key unconditionally in the formatter (default `""`) and add a rendered-output test for the empty-ID case. |
| 3 | S6.1 | The only cross-process test (`tests/integration/test_trace_continuity_process.py`) is gated on `TRACE_E2E=1`, which no CI workflow sets. S6.1 is therefore backed in CI by in-process tests with a mocked broker. | In #536, add a `TRACE_E2E=1` step to `.github/workflows/pytest.yml` (per-PR, or devel + schedule), or delete Tier 3 and say so. |
| 4 | S1.3, S2.2, S4.4 | No executing test proves the negative (no auth/tenant/routing use, no direct `request_id_var.get()` in app code, no manual interpolation in log messages). | Add a lint rule (banned-API check for `request_id_var.get(` outside the helper; banned f-string pattern) or document these as review-only in the PR checklist. |
| 5 | S5.5 | No explicit assertion that auth material is absent from propagated headers or logs; `test_gateway_client.py` only checks that the auth header survives the merge. | Add an assertion that the outbound header dict and log records contain no `Authorization`/token material. |
| 6 | All | There is no executable conformance suite that adopters can vendor; the "conformance test shape" is prose plus branch-local tests. | Write `tests/unit/core/test_trace_standard.py` after #532/#528 merge, against the merged helpers. |

## Open items

- **S6.2 (manual log-search procedure)** — the runbook (grep/CLM query by
  `request_id` across API, worker and scheduler processes) is written in
  `docs/trace-propagation.md` on PR #536; satisfied once #536 merges.
- **S4.5 (OpenTelemetry ADR)** — no ADR is on `devel`: PR #529 is not merged,
  so `docs/adr/` does not exist there and S4.5 is unevidenced (see
  [Known gaps](#known-gaps)).
- **Executable conformance suite** — deferred until PRs #532/#528 merge (see
  [conformance test shape](#conformance-test-shape)).
- **Shared package extraction** — deliberately deferred (Option B in the
  AAP-79596 plan) until a second service adopts; vendoring the three reference
  modules is the sanctioned adoption path today.
- **Pilot Emerging Service** — not yet identified; see the story's open
  questions.

## Relationship to OpenTelemetry

`request_id` is the stable, always-present correlation key. OpenTelemetry
adoption for metrics-service is currently **deferred** — the ADR is drafted on
branch `docs/aap-79589-opentelemetry-spike`
(`docs/adr/0002-opentelemetry-trace-export.md`) in
[PR #529](https://github.com/ansible/metrics-service/pull/529), which is **not
merged**; `docs/adr/` does not exist on `devel`. S4.5 is therefore
unevidenced until an ADR lands. If the ADR is withdrawn, S4.5 remains a
forward-looking rule for adopters that do enable OTel. When OTel is adopted,
its `trace_id`/`span_id` are added alongside `request_id` (S4.5); the two
standards do not diverge.
