# ADR 0002 — OpenTelemetry trace export for metrics-service

| Field | Value |
|---|---|
| **Status** | Proposed — recommended decision: **Defer adoption** |
| **Date** | 2026-11-05 |
| **Story** | [AAP-79589](https://redhat.atlassian.net/browse/AAP-79589) — OpenTelemetry feasibility spike |
| **Parent epic** | [AAP-79579](https://redhat.atlassian.net/browse/AAP-79579) — Cross-service trace propagation |
| **Spike timebox** | 3 working days (no code merged in this change) |
| **Decision owner** | AAP Emerging Services |

## Context

metrics-service has correlation IDs but no distributed tracing. `request_id`
comes from django-ansible-base (DAB) `LogRequestMiddleware` /
`RequestIdFilter` and is emitted by the JSON log formatter
(`apps/core/logging_config.py:33`). It does not cross the asynchronous
boundary: once the web process writes a `Task` row and the scheduler submits it
to dispatcherd, the worker has no link to the originating request. Outbound
HTTP calls made through DAB or metrics-utility carry no request or trace
context.

The service runs as three cooperating processes (`docs/task-system.md`):

- **Web** — Gunicorn/Django/DRF, with `django-prometheus` middleware wrapped
  around the stack in `apps/settings/defaults.py:215-224`.
- **Scheduler** — a dedicated process running APScheduler 3.x
  `BackgroundScheduler` (`apps/tasks/cron_scheduler.py:70`), started by
  `run_task_scheduler` (`apps/tasks/management/commands/run_task_scheduler.py:51`).
- **Workers** — dispatcherd processes (`apps/tasks/management/commands/run_dispatcherd.py:67`),
  defaulting to dispatcherd's `ForkServerManager`; every task funnels through
  `execute_db_task` (`apps/tasks/tasks_system.py:205`).

The queue is PostgreSQL-backed (`pg_notify`); the durable hand-off between web
and worker is a `Task` database row, not a message with headers. That shape is
the central constraint on trace propagation.

This ADR answers the spike questions in the AAP-79589 plan and records a
recommendation. It does not add runtime code.

## Decision

**Defer OpenTelemetry adoption to a future release.** Do not add the OTel SDK
or the DAB observability app to metrics-service now.

The technical path is credible and much cheaper than expected — DAB already
ships a first-class OpenTelemetry integration (see
[Key finding](#key-finding-dab-already-ships-opentelemetry)) — but two
must-pass criteria from the spike are unmet in the target product:

1. **No export target exists for metrics-service.** Neither
   `automation-metrics-service-container`, `automation-metrics-operator`, nor
   `automation-metrics-operator-container` contains any `OTEL_*` environment
   variable, collector sidecar, Tempo/Jaeger integration, or network policy.
   AAP does not ship a trace backend for this service today.
2. **No owner or on-call story exists for a collector/backend.** DAB's
   exporters default to `localhost:4317`; adding the app without an endpoint
   produces silent retry noise rather than telemetry.

The async propagation work planned in AAP-79587/AAP-79588 is the correct
prerequisite and is **not wasted**: the W3C `traceparent` header and the
dispatcherd kwargs extension point are exactly what OTel's propagator and
consumer spans need.

### Triggers that reopen this decision

Adopt when **any two** of the following hold, and all must-pass criteria can
be met:

- AAP ships or supports an OTLP endpoint (OpenTelemetry Collector, Tempo, or a
  vendor backend) for metrics-service deployments, including operator/installer
  configuration and a named owner.
- Support asks for span-level latency or a cross-service request waterfall, not
  just log search by `request_id`.
- AAP-79587 and AAP-79588 have landed, so `traceparent` is available on task
  payloads and outbound calls.
- dispatcherd gains native context propagation, or the team accepts the
  kwargs-based bridge described in [Follow-on work](#follow-on-work-if-adopted).
- The team has capacity to own collector configuration, sampling policy, and
  export failures on call.

If support never needs span-level data, **do not adopt**: the ID-only approach
(AAP-79587/79588/79590/79596) satisfies the documented support workflow, and
the operational surface of a collector is not justified.

## Key finding: DAB already ships OpenTelemetry

The resolved django-ansible-base package (2026.10.23.0.dev3, tracked to the
`2026.10.26` requirement in `pyproject.toml:29`) includes
`ansible_base.observability`, a Django app labelled `dao_opentelemetry`.
It is **not** enabled in metrics-service and its optional dependencies are not
installed.

What it provides (`ansible_base/observability/instrument.py`):

- `TracerProvider` + `BatchSpanProcessor` with `OTLPSpanExporter` (gRPC).
- `LoggerProvider` + `BatchLogRecordProcessor` with `OTLPLogExporter` (gRPC),
  attached to the root logger and to loggers with `propagate=False`.
- Auto-instrumentation for Django, psycopg/psycopg2, `requests`, gRPC server,
  and `logging`.
- Header capture/forwarding driven by `ANSIBLE_OBSERVABILITY_CAPTURE_HEADERS`
  (`ansible_base/observability/propagation.py`).

Settings exposed by the app:

| Setting | Default | Notes |
|---|---|---|
| `ANSIBLE_OBSERVABILITY_SERVICE_NAME` | `"aap-generic"` | Set to `metrics-service` |
| `ANSIBLE_OBSERVABILITY_OTLP_ENDPOINT` | `None` | gRPC endpoint; falls back to `OTEL_EXPORTER_OTLP_ENDPOINT` |
| `ANSIBLE_OBSERVABILITY_BATCH_DELAY_MS` | `5000` | Batch export delay for spans and logs |
| `ANSIBLE_OBSERVABILITY_CAPTURE_HEADERS` | `[]` | Regex list; empty means no headers captured |

Enablement would be: add the `observability` extra to the DAB dependency in
`pyproject.toml:29` and add `ansible_base.observability` to `dab_applications`
in `apps/settings/defaults.py:21-28`. That is a small change, which is why the
decision hinges on deployment and ownership rather than code.

Caveat: `ObservabilityConfig.ready()` calls `setup_observability()`
unconditionally and DAB's exporters are OTLP/**gRPC** only. There is no
OTLP/HTTP option and no disable switch, so the app must be conditionally added
to `INSTALLED_APPS` (or given a no-op exporter) when no endpoint is configured.

## Spike findings

| # | Question | Finding | Evidence |
|---|---|---|---|
| Q1 | Does auto-instrumentation work with Django 5.2 + DRF + DAB, and does it break `request_id`? | **Yes.** Django auto-instrumentation produced one `SERVER` span per request on Django 5.2.17. It does not touch `request_id`, which remains a separate log field. `request_id` and `trace_id` can coexist. | Isolated probe (Python 3.12.0, Django 5.2.17, `opentelemetry-instrumentation-django` 0.66b2): `GET api/v1/tasks/` → one SERVER span. |
| Q2 | Can trace context cross web → `Task` row → scheduler → dispatcherd worker without modifying dispatcherd? | **Yes.** W3C `traceparent` survives a JSON-serialized `Task` row and a dispatcherd kwargs dict. Extract/inject produced one trace with correct parent/child links across three simulated processes. dispatcherd needs no source change because `execute_db_task(**kwargs)` already accepts arbitrary kwargs. | Isolated probe: 3 spans, one trace ID, scheduler parent = web span, worker parent = scheduler span. |
| Q3 | Can context reach APScheduler jobs? | **Partially.** There is no first-party or published `opentelemetry-instrumentation-apscheduler` package. Manual wrapping of the job function works: each execution produced its own root span with no context bleed. | Probe with APScheduler 3.11.0: 4 executions → 4 distinct root traces. `pip index versions opentelemetry-instrumentation-apscheduler` → no distribution. |
| Q4 | Can third-party outbound calls be traced? | **Yes.** `requests` instrumentation patches `requests.Session`/`requests.request`, so DAB's `BaseServiceClient` (`ansible_base/resource_registry/service_client.py:146`) and metrics-utility's module-level `requests.post` (`metrics_utility/library/storage/segment.py:310`) are both covered. | Probe: outbound GET span captured as a child of the parent span. |
| Q5 | Which export target fits AAP? | **OTLP/gRPC to a collector** is the only path DAB supports. Jaeger and OpenShift Tempo both accept OTLP; OTLP/HTTP would require replacing DAB's exporter. No collector exists in the metrics-service deployment today. | DAB `instrument.py` hard-codes `OTLPSpanExporter`/`OTLPLogExporter` (gRPC). Deployment repos contain no OTel wiring. |
| Q6 | Runtime cost? | **Indicative pass, not load-tested.** Per-span CPU cost is tens of microseconds; exporter work is batched. A realistic p99 budget was not measured in this spike. | Probe: ~2.4 µs no-op span, ~12–16 µs with an exporter at 100% sampling. See [Performance](#performance). |
| Q7 | Data safety? | **Controllable, but not implemented.** DAB captures no headers by default, but psycopg instrumentation exports SQL statement text and DAB exports all log records over OTLP. An allow-list and redaction filter are required before production. | `capture_headers=[]` default; psycopg instrumentation defaults; see [Data safety](#data-safety-and-attribute-allow-list). |
| Q8 | How do spans and logs correlate? | **Yes, with one caveat.** `LoggingInstrumentor` can inject `otelTraceID`/`otelSpanID` into records; `JsonFormatter` can then emit `trace_id`/`span_id` alongside `request_id`. DAB calls `instrument()` without `inject_trace_context=True`, so `OTEL_PYTHON_LOG_CORRELATION=true` (or a small DAB-usage change) is required. | Probe with `inject_trace_context=True`: log line contained trace ID `def6a1…` and span ID `905082…`. |
| Q9 | Implementation/ownership cost? | **Low code, high operations.** Enablement is ~4 lines of config plus dependencies; collector deployment, sampling policy, and export-failure on-call are new operational surface with no current owner. | See [Implementation complexity](#implementation-complexity). |
| Q10 | Does OTel supersede the `X-Request-ID` contract? | **No — it complements it.** `request_id` remains the human/support search key and the outbound `X-Request-ID` header. `trace_id` is added alongside and is the join key into the trace backend. | Design; AAP-79587/79588 remain prerequisites. |

## Compatibility

### Django, DRF, and django-prometheus

Django auto-instrumentation is compatible with Django 5.2 and DRF.
`django-prometheus` is inserted by a Dynaconf `post_hook`
(`apps/settings/defaults.py:215-224`) rather than in the base middleware list,
so OTel's Django instrumentor wraps the final WSGI stack; no middleware-order
conflict was observed. Both libraries remain independently usable: Prometheus
keeps metrics, OTel adds spans.

### APScheduler

APScheduler 3.x runs in its own process and has no inbound HTTP request, so
Django auto-instrumentation cannot create a parent context. Two job classes
need explicit spans:

- the `periodic_db_sync` interval job (`apps/tasks/cron_scheduler.py:136-140`);
- `DateTrigger`/`CronTrigger` jobs that call
  `_execute_database_task` (`apps/tasks/cron_scheduler.py:385-450`, entry at
  `:452`).

Wrapping `_execute_database_task` in a span is sufficient: each fire becomes a
root span (or a child of the web span when the task row carries a
`traceparent`). No third-party instrumentor should be relied on.

### dispatcherd

dispatcherd's default `ForkServerManager` forks workers. `execute_db_task`
calls `ensure_django_setup()` (`apps/tasks/tasks_system.py:220`,
`apps/tasks/utils.py:32-47`), so a fresh Django setup — and therefore DAB's
`setup_observability()` — runs in each worker process. That avoids inheriting a
dead `BatchSpanProcessor` thread from the parent, but it must be verified in a
running dispatcherd worker before adoption; it was not exercised in this spike.

The propagation bridge is small and needs no dispatcherd changes:

- At submit time, inject the active W3C context into the task payload.
  `submit_task_to_dispatcher()` already calls
  `submit_task(execute_db_task, kwargs={"task_id": task.id}, queue=queue)`
  (`apps/tasks/tasks_system.py:248-277`).
- At execution time, extract it in `execute_db_task` and open a `CONSUMER`
  span (`apps/tasks/tasks_system.py:205-245`).

For web-originated tasks the `traceparent` should be persisted on the `Task`
row (e.g. in `task_data`, `apps/tasks/models.py:81`) so the scheduler process,
which may run the job much later, can reconstruct the link. For
scheduler-originated recurring tasks there is no web parent; a root span is
correct.

### Third-party HTTP

`opentelemetry-instrumentation-requests` instruments the `requests` library at
the session/adaptor layer. Both known seams are covered:

- DAB resource-registry calls — `ansible_base/resource_registry/service_client.py:146`
  (`requests.request`).
- metrics-utility Segment upload — `metrics_utility/library/storage/segment.py:310`
  (`requests.post`).

DAB's own `outgoing_request_hook` additionally forwards any headers matching
`ANSIBLE_OBSERVABILITY_CAPTURE_HEADERS`, which is how `X-Request-ID` can ride
alongside `traceparent`.

## Export target options

| Option | Fit | Assessment |
|---|---|---|
| **OTLP/gRPC → OpenTelemetry Collector** | Native to DAB | **Recommended target if adopted.** DAB's exporters are gRPC-only. Collector centralizes sampling, redaction, and routing; requires a deployment and owner. |
| OTLP/HTTP → collector | Not supported by DAB as-is | Would require a custom `SpanExporter` or replacing `setup_observability()`; no reason to prefer it here. |
| Jaeger (all-in-one) | Accepts OTLP | Fine for development/POC, not a supported production backend for AAP. Useful for the spike demo only. |
| Red Hat OpenShift distributed tracing (Tempo) | Accepts OTLP | Plausible production backend **if** the platform provides it to metrics-service. No evidence of that integration in the container/operator repos today. |
| Existing AAP observability stack | Prometheus only today | Prometheus scrapes `/metrics`; there is no trace store. Metrics and traces are complementary, not substitutes. |

**Deployment delta for any target:** collector (or Tempo) deployment and
ownership, `ANSIBLE_OBSERVABILITY_OTLP_ENDPOINT`/`OTEL_EXPORTER_OTLP_ENDPOINT`
on web/scheduler/worker pods, a network policy to the collector, sampling
configuration, and a resource budget for the exporter.

## Performance

A microbenchmark ran in an isolated venv, not against the service. It measures
span creation and export CPU only; it is **not** a load test and does not
include network I/O or the full DAB instrumentation set.

| Scenario | Cost per span (indicative) |
|---|---|
| No-op tracer (no SDK) | ~2.4 µs |
| SDK, `SimpleSpanProcessor` + in-memory exporter, 100% sampling | ~12.1 µs |
| SDK, `BatchSpanProcessor` + null exporter, 100% sampling | ~16.4 µs |
| SDK, `BatchSpanProcessor` + null exporter, 10% sampling | ~13.9 µs |

Observations:

- Sampling reduces export volume, not span-creation cost. The dominant
  per-request cost is the number of spans (HTTP, DB, outbound calls).
- A typical API request creates a handful of spans, so the added CPU is
  sub-millisecond; `BatchSpanProcessor` moves export off the request path.
- The proposed budget (≤ 5% p99 latency, ≤ 50 MB RSS per pod) is plausible but
  **unverified**. A load test with the full DAB stack (including psycopg and
  gRPC export) is required before "adopt now" is accepted.
- The 50 MB RSS budget is at risk: the OTel SDK and gRPC exporter add
  dependencies and buffers, and the container image grows by roughly nine
  packages via DAB's `observability` extra.

## Data safety and attribute allow-list

metrics-service handles RBAC data and anonymized Segment payloads. Traces must
never carry payload content, tenant identifiers, or credentials.

Proposed production allow-list:

| Attribute | Allowed |
|---|---|
| `service.name`, `service.version`, `deployment.environment` | Yes |
| `http.request.method`, `http.route`, `http.response.status_code`, `url.scheme`, `server.address`, `server.port` | Yes — route templates only, never raw paths with IDs |
| `db.system`, `db.operation`, `db.namespace` | Yes |
| `db.statement`, SQL parameters | **No** — disable/reject |
| `task.function_name`, `task.queue`, `task.id` (internal) | Yes |
| `traceparent` / `tracestate` | Yes (propagation only) |
| Request/response bodies, headers other than `traceparent`/`X-Request-ID` | **No** |
| User, organization, team IDs, usernames, emails | **No** |
| Segment payload fields, write key, API tokens | **No** |
| Exception type/stacktrace | Yes; free-text message only if it cannot contain payload data |

Controls required before adoption:

- `ANSIBLE_OBSERVABILITY_CAPTURE_HEADERS` stays empty (or an explicit minimal
  allow-list).
- A `SpanProcessor` or collector-side processor that drops `db.statement` and
  disallowed attributes.
- A decision on DAB's OTLP **log** export: it ships every log record,
  including existing `extra=` task details. Either restrict the exported
  loggers or confirm the current log payloads are safe.
- Confirm psycopg's parameter capture is off (default) and that statement text
  is removed.

These controls are not implemented in this spike. If they cannot be made
enforceable, the decision should remain "defer".

## Implementation complexity

| Area | Cost | Notes |
|---|---|---|
| Dependencies | Low | Add `observability` to `django-ansible-base[...]` in `pyproject.toml:29`; ~9 transitive OTel packages, image size grows |
| App wiring | Low | Add `ansible_base.observability` to `dab_applications` (`apps/settings/defaults.py:21-28`); make it conditional on an endpoint being configured |
| Configuration | Low | Service name, endpoint, batch delay, header allow-list, test-mode no-op exporters |
| Log correlation | Low | Emit `trace_id`/`span_id` in `apps/core/logging_config.py`; keep `request_id`; ensure `OTEL_PYTHON_LOG_CORRELATION=true` |
| Async propagation | Medium | Web → `Task.task_data` → scheduler → dispatcherd kwargs → `execute_db_task`; overlaps with AAP-79587 |
| APScheduler spans | Low–medium | Manual wrapper around `_execute_database_task` and the periodic sync job |
| Worker initialization | Medium | Verify DAB initialization under dispatcherd's forkserver; recreate providers after fork if needed |
| Operations | High | Collector/backend deployment, sampling policy, dashboards, export-failure alerting, on-call ownership |
| Rollout risk | Medium | Global tracer/logger providers are write-once per process; `setup_observability()` is deliberately non-idempotent |

## Decision criteria

| Criterion | Weight | Result | Why |
|---|---|---|---|
| Cross-process propagation without modifying dispatcherd | must-pass | **Pass (mechanism verified)** | W3C context survives the `Task` row and kwargs; no dispatcherd change |
| Overhead within budget | must-pass | **Unverified** | Indicative microbenchmark is favourable; no load test |
| No sensitive data exported | must-pass | **Not yet** | Allow-list defined; redaction and log-export controls not implemented |
| Deployment target available for AAP | must-pass | **Fail** | No collector/Tempo/OTLP endpoint in metrics-service deployment or AAP product wiring |
| Preserves `request_id` contract | must-pass | **Pass** | `trace_id` is additive; `request_id` stays the support key |
| Operational cost acceptable | high | **Fail** | No owner, on-call, or sampling policy for a collector |
| Third-party instrumentation works | medium | **Pass** | DAB and metrics-utility `requests` calls are covered |

Two must-pass criteria fail, so **adopt now** is not justified. The failures
are environmental (no backend, no owner), not structural, so **defer** — not
"do not adopt".

## Consequences

- No runtime change now; no new dependencies, image size, or exporter noise.
- AAP-79587/79588/79590/79596 deliver the ID contract; its `traceparent` and
  task-payload work becomes the transport layer for a future OTel adoption.
- Support continues to rely on `request_id` log search. If span-level latency
  becomes a support requirement, that is a trigger to reopen this ADR.
- The DAB observability app is the recommended implementation vehicle; no
  custom telemetry bootstrap module is needed.

## Follow-on work if adopted

1. **Enablement (0.5 day):** add DAB's `observability` extra and
   `ansible_base.observability`, conditional on a configured endpoint; set
   `ANSIBLE_OBSERVABILITY_SERVICE_NAME=metrics-service`; add no-op exporters
   in `apps/settings/test.py`.
2. **Log/trace join (0.5 day):** add `trace_id`/`span_id` to
   `apps/core/logging_config.py::JsonFormatter` from
   `record.otelTraceID`/`otelSpanID`; set `OTEL_PYTHON_LOG_CORRELATION=true`
   or call `inject_trace_context=True`; keep `request_id`.
3. **Async propagation (1–2 days, with AAP-79587):** persist `traceparent` on
   the originating `Task` row; inject it in `submit_task_to_dispatcher`
   (`apps/tasks/tasks_system.py:248`); extract and open a `CONSUMER` span in
   `execute_db_task` (`:205`). No dispatcherd changes.
4. **Scheduler spans (0.5 day):** wrap `_execute_database_task` and the
   periodic sync job in `apps/tasks/cron_scheduler.py`.
5. **Data safety (1 day):** implement the attribute allow-list and a
   `SpanProcessor`/collector redaction rule; decide whether DAB's OTLP log
   export is enabled or loggers are filtered.
6. **Deployment (owned by platform/ops):** deploy a collector or Tempo
   endpoint, wire the three pods, add network policy, sampling, and export
   alerting; define on-call ownership.
7. **Verification (0.5 day):** load test at realistic API and task rates to
   confirm ≤ 5% p99 and ≤ 50 MB/pod; confirm spans export from dispatcherd
   workers.

Total engineering effort excluding platform/ops is roughly 4–5 days on top of
AAP-79587/79588; operations effort is the larger, unbounded item.

## References

- `docs/task-system.md` — three-process runtime and dispatcherd hand-off
- `docs/apscheduler.md` — scheduler internals and job triggers
- `apps/tasks/tasks_system.py:205,248` — worker entry point and submit path
- `apps/tasks/cron_scheduler.py:70,136,452` — scheduler, periodic sync, dispatch
- `apps/core/logging_config.py:33` — `request_id` in JSON logs
- `apps/settings/defaults.py:21-28,215-224` — DAB apps and Prometheus middleware
- `pyproject.toml:29` — DAB dependency (add `observability` extra on adoption)
- `ansible_base/observability/instrument.py` and `propagation.py` — DAB OTel support
- `ansible_base/resource_registry/service_client.py:146`,
  `metrics_utility/library/storage/segment.py:310` — outbound HTTP seams
- Spike probe versions: Python 3.12.0, Django 5.2.17, APScheduler 3.11.0,
  `opentelemetry-sdk` 1.45.2, `opentelemetry-instrumentation-*` 0.66b2
