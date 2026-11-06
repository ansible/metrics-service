# Request ID / trace propagation

Metrics Service propagates the request ID of the API call that created a task
all the way into the dispatcherd worker that executes it, and — new in
AAP-79588 — onto the outbound HTTP calls the service makes, so a single log
search (or a single trace) returns both the API and worker entries and the
downstream services they talk to.

## The ID contract

- The inbound header is `X-Request-ID`. The canonical wire spelling is exactly
  that; HTTP header names are case-insensitive but log and trace parsers are not.
- The value must be a UUID. A missing or invalid header gets a freshly
  generated UUID; arbitrary strings are never propagated or logged.
- The API echoes the effective ID back in the `X-Request-ID` response header.

## Header contract (outbound)

| Header | Value | Notes |
|--------|-------|-------|
| `X-Request-ID` | Canonical UUID string | Same value the API received on the inbound request (or the ID restored from the task payload); never regenerated on an outbound seam |
| `traceparent` | `00-<trace-id>-<span-id>-<flags>` | **Pass-through only** — emitted only when the inbound request carried a valid W3C value |

`traceparent` values are validated against W3C Trace Context §3.2.2: any version
other than `ff` is accepted, and version-specific trailing fields are ignored
rather than rejected, so future OpenTelemetry senders are not silently dropped.
The value is normalised to lower-case before it is forwarded — it is *not*
passed through byte-for-byte when the sender used upper-case hex.

Invalid inbound values are dropped, never repaired, and the rejection is logged
at `DEBUG` (`dropping malformed traceparent: ...`). The context is empty in a
process with no restored request context (for example a worker that has not
been given a task payload request ID), and in that case no headers are added at
all — not an empty or `null`-valued header.

`outbound_headers()` is the **only** producer of these headers, so the allow-list
is closed: no caller-supplied key can be injected, and neither value can carry
`\r\n` because both are validated before they reach a `requests` header dict.

## How it travels

1. **Web process** — `apps.core.middleware.request_id.RequestIdMiddleware`
   accepts or generates the ID, binds a valid inbound `traceparent` alongside
   it, and puts both in `contextvars.ContextVar`s
   (`apps.core.request_context.request_id_var` / `traceparent_var`). It is
   registered by the `insert_request_id_middleware` post hook in
   `apps/settings/defaults.py`, which inserts it immediately *outside* DAB's
   `LogRequestMiddleware`/`LogTracebackMiddleware` so those records already see
   the ID; `dynaconf_merge_unique` alone would have appended it at the
   innermost position instead.
2. **Durable hop** — the ID is written to the nullable, indexed
   `Task.request_id` column when a task is created from an API request. The
   scheduler runs in a separate process and cannot see the web context, so the
   row is the hand-off point.
3. **Dispatcherd payload** — `submit_task_to_dispatcher()` adds `request_id` to
   the kwargs of `execute_db_task`. No dispatcherd code is modified.
4. **Worker** — `execute_db_task()` re-enters `request_context(request_id)` for
   the whole execution, so every log record carries the ID. If the payload has
   no key (rolling upgrade), the worker falls back to `Task.request_id` after
   claiming the task, and re-enters that context around error handling so
   failure/retry lines keep the ID too.
5. **Outbound** — anything the web process or the worker calls out to gets the
   same pair from `outbound_headers()` (see [Outbound seams](#outbound-seams)).

`apps.core.logging_filters.RequestIdFilter` keeps DAB's header/thread-local
behaviour and prefers the contextvar, which is what lets worker processes tag
records even though they have no Django request.

Recurring templates keep the ID of the request that created them; each
execution row copies it. Retries reuse the task row, so one originating request
produces one searchable ID across retries. A *manual* retry triggered from the
API (`POST /tasks/{pk}/retry/`) is likewise attributed to the original request,
not to the operator who retried it.

The ID is validated as a UUID at every *consumption* boundary (middleware,
`outbound_headers()`, worker re-entry, log formatting) — not at the database
boundary, where `Task.request_id` is a plain `CharField(max_length=36)`. That
is the boundary that matters for log and header injection, but a value written
directly to the column by hand is not rejected until it is read.

## Outbound seams

Both outbound HTTP paths go through third-party code, so propagation is
attached at a supported extension point rather than by a global monkeypatch.

### AAP Gateway — DAB `ResourceAPIClient`

`apps/core/gateway_client.py` defines `TracePropagatingResourceAPIClient`,
which overrides DAB's `requests_auth_kwargs` property and merges
`outbound_headers()` into the auth headers. `create_traced_api_client()` builds
it from settings, mirroring DAB's `create_api_client()`. The resource sync task
(`apps/tasks/simple/resource_sync.py`) uses it, so every Gateway call carries
`X-Request-ID` (and `traceparent` when present) alongside
`X-ANSIBLE-SERVICE-AUTH`.

`requests_auth_kwargs` copies the auth dict before updating it, so the service
auth header is never clobbered. `create_traced_api_client()` is a line-for-line
copy of DAB's factory and can be deleted if DAB ever grows native header support
or accepts a client *class*.

### Segment — `metrics_utility.library.storage.segment.StorageSegment`

**Status: code complete, wire-inert.** metrics-service passes
`headers=outbound_headers()` to the `StorageSegment` constructor, but the
pinned metrics-utility release does not consume it: `StorageSegment.__init__`
accepts arbitrary `**settings` and drops unknown keys, and `_send_batch()`
hard-codes `headers = {'Content-Type': 'application/json'}`. Nothing raises and
no header reaches the wire, so Segment calls are **not** traced today.

The upstream fix is
[ansible/metrics-utility#635](https://github.com/ansible/metrics-utility/pull/635)
("Allow StorageSegment to forward caller-supplied HTTP headers", open as a
draft). It merges caller headers *under* the `Content-Type`/`Content-Encoding`
keys the library requires, so it cannot break the Segment wire format.

`tests/unit/tasks/test_send_anonymized_to_segment_headers.py` is therefore
marked `xfail(strict=True)` with the blocking PR in the reason: it asserts only
that the header reaches the `StorageSegment` constructor, not that it reaches
`requests.post()`. Strict xfail means the moment the dependency lands and the
test can be made honest, it fails instead of staying falsely green. Unblock
steps are in PR #528's description.

A process-global `requests` monkeypatch was considered as a fallback and was
deliberately **not** shipped: it is easy to leave behind and affects every
library in the process.

## Searching logs

Verbose logs render `[<request_id>]`; JSON logs include a `request_id` field.
Search by the UUID, for example:

```bash
kubectl logs deploy/metrics-service | grep '<request-id>'
```

## Adding a new outbound call

Any new outbound HTTP client must obtain its headers from
`apps.core.request_context.outbound_headers()` — never read the inbound request
directly, and never build the header dict by hand. Use a client extension point
(such as a session/request hook) so the headers are applied automatically, and
add a test asserting `X-Request-ID` is present inside a `request_context(...)`
block and absent outside one.

## Scope and merge order

| PR | Owns | Status |
|----|------|------|
| [#532](https://github.com/ansible/metrics-service/pull/532) (AAP-79587) | Inbound ID lifecycle: accept/generate → echo → persist → worker re-entry. Canonical `apps/core/request_context.py`, `RequestIdMiddleware`, settings post hooks, `Task.request_id`, migration 0005. | base — merge first |
| [#528](https://github.com/ansible/metrics-service/pull/528) (AAP-79588) | Outbound side: `TracePropagatingResourceAPIClient`, resource-sync wiring, Segment header passthrough, this document. Stacked on #532. | merge second |
| [#536](https://github.com/ansible/metrics-service/pull/536) (AAP-79590) | Acceptance evidence: end-to-end trace continuity tests plus the manual verification procedure. Stacked on #532. | merge third |

Out of scope: OpenTelemetry spans and trace export (AAP-79589). This service
never synthesises a `traceparent`; it only forwards a valid inbound one.
