# Request ID / trace propagation

Metrics Service propagates the request ID of the API call that created a task
all the way into the dispatcherd worker that executes it, so a single log
search returns both the API and worker entries.

## The ID contract

- The inbound header is `X-Request-ID`.
- The value must be a UUID. A missing or invalid header gets a freshly
  generated UUID; arbitrary strings are never propagated or logged.
- The API echoes the effective ID back in the `X-Request-ID` response header.

## How it travels

1. **Web process** — `apps.core.middleware.request_id.RequestIdMiddleware`
   (installed right after DAB's `LogRequestMiddleware`) accepts or generates the
   ID and puts it in a `contextvars.ContextVar`
   (`apps.core.request_context.request_id_var`).
2. **Durable hop** — the ID is written to the nullable, indexed
   `Task.request_id` column when a task is created from an API request. The
   scheduler runs in a separate process and cannot see the web context, so the
   row is the hand-off point.
3. **Dispatcherd payload** — `submit_task_to_dispatcher()` adds `request_id` to
   the kwargs of `execute_db_task`. No dispatcherd code is modified.
4. **Worker** — `execute_db_task()` re-enters
   `request_context(request_id)` for the whole execution, so every log record
   carries the ID. If the payload has no key (rolling upgrade), the worker falls
   back to `Task.request_id` after claiming the task.

`apps.core.logging_filters.RequestIdFilter` keeps DAB's header/thread-local
behaviour and prefers the contextvar, which is what lets worker processes tag
records even though they have no Django request.

Recurring templates keep the ID of the request that created them; each
execution row copies it. Retries reuse the task row, so one originating request
produces one searchable ID across retries.

## Searching logs

Verbose logs render `[<request_id>]`; JSON logs include a `request_id` field.
Search by the UUID, for example:

```bash
kubectl logs deploy/metrics-service | grep '<request-id>'
```

## Scope

Out of scope for this implementation: W3C `traceparent` handling and
OpenTelemetry spans (see AAP-79588 and AAP-79589).
