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
   accepts or generates the ID and puts it in a `contextvars.ContextVar`
   (`apps.core.request_context.request_id_var`). It is registered by a post hook
   in `apps/settings/defaults.py` immediately *outside* DAB's
   `LogRequestMiddleware`/`LogTracebackMiddleware`, so those records already see
   the ID; `dynaconf_merge_unique` would have appended it at the innermost
   position instead.
2. **Durable hop** — the ID is written to the nullable, indexed
   `Task.request_id` column when a task is created from an API request. The
   scheduler runs in a separate process and cannot see the web context, so the
   row is the hand-off point.
3. **Dispatcherd payload** — `submit_task_to_dispatcher()` adds `request_id` to
   the kwargs of `execute_db_task`. No dispatcherd code is modified.
4. **Worker** — `execute_db_task()` re-enters
   `request_context(request_id)` for the whole execution, so every log record
   carries the ID. If the payload has no key (rolling upgrade), the worker falls
   back to `Task.request_id` after claiming the task, and re-enters that context
   around error handling so failure/retry lines keep the ID too.

`apps.core.logging_filters.RequestIdFilter` keeps DAB's header/thread-local
behaviour and prefers the contextvar, which is what lets worker processes tag
records even though they have no Django request.

Recurring templates keep the ID of the request that created them; each
execution row copies it. Retries reuse the task row, so one originating request
produces one searchable ID across retries.

## Searching logs

Verbose logs render `[<request_id>]`; JSON logs (`METRICS_SERVICE_MODE=production`
or `METRICS_SERVICE_LOG_FORMAT=json`) carry it as a top-level `request_id` key.
Search by the UUID, for example:

```bash
kubectl logs deploy/metrics-service | grep '<request-id>'
```

## Scope

This change owns the request ID lifecycle (accept/generate → echo → persist →
worker re-entry). `apps/core/request_context.py` also exposes the additive trace
API used by the outbound side: a validated inbound W3C `traceparent` is bound on
the same context (`current_traceparent()`), and `outbound_headers()` returns the
`X-Request-ID`/`traceparent` pair for outbound HTTP calls. Wiring those headers
into the Gateway client and the Segment sender is AAP-79588 (PR #528) and is
deliberately not part of this PR.

Out of scope: OpenTelemetry spans and trace export (AAP-79589). This service
never synthesises a `traceparent`; it only forwards a valid inbound one.

## Verifying trace continuity

### Automated (CI / local)

Three layers of regression coverage keep this property from silently breaking:

- **Tier 1 — in-process** (`tests/unit/tasks/test_trace_continuity.py`): exercises
  middleware → `Task.request_id` → `submit_task_to_dispatcher` payload →
  `execute_db_task` context → log records, with only the dispatcherd broker
  mocked. Runs on every PR via the normal `pytest` job.
- **Tier 2 — scheduler in the loop**
  (`tests/unit/tasks/test_trace_continuity_scheduler.py`): drives
  `UnifiedTaskScheduler._execute_database_task()` for both the non-recurring and
  the recurring (execution-row) branch. Runs on every PR via the normal `pytest`
  job.
- **Tier 3 — cross-process** (`tests/integration/test_trace_continuity_process.py`):
  starts a real scheduler and a real dispatcherd worker as subprocesses (real
  pg_notify broker) and asserts the ID appears in the worker process's own log
  output. **Opt-in only — it is not run in CI**: `.github/workflows/pytest.yml`
  does not set `TRACE_E2E`, so this file is collected and skipped there. Run it
  explicitly, against a PostgreSQL instance, with:

  ```bash
  make test-trace-e2e
  # equivalent to:
  TRACE_E2E=1 uv run pytest tests/integration/test_trace_continuity_process.py -s -v
  ```

  It creates the probe table it needs inside a dedicated `trace_e2e_probe`
  schema and drops that schema afterwards, and it has a hard timeout, so it is
  safe to run repeatedly against a `--reuse-db` database. Expect roughly half a
  minute of wall-clock time.

  Adding a nightly or `workflow_dispatch` job that sets `TRACE_E2E=1` is tracked
  as a follow-up decision (needs maintainer agreement on CI cost); until then
  nothing in CI exercises the cross-process hop, and Tiers 1–2 remain the
  CI-enforced guarantee.

### Manual (deployed instance)

For a deployed instance (or `docker-compose.prod.single.yml`):

1. Send a request with a known ID and confirm the response echoes it:

   ```bash
   curl -sS -D - -o /dev/null \
     -H "X-Request-ID: 6f1d1c2a-1f0e-4f0b-9a3e-2b1c4d5e6f70" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -X POST .../api/v1/tasks/schedule_immediate/ \
     -d '{"function_name": "hello_world", "name": "trace-check"}'
   # expect: X-Request-ID: 6f1d1c2a-1f0e-4f0b-9a3e-2b1c4d5e6f70 in the response headers
   ```

2. Find the API-side entries:

   ```bash
   kubectl logs deploy/metrics-service | grep 6f1d1c2a-1f0e-4f0b-9a3e-2b1c4d5e6f70
   ```

3. Find the worker-side entries for the same ID — task start/run/complete lines
   such as `Task 'hello_world' start` and `Task execution finished with status: completed`:

   ```bash
   kubectl logs deploy/metrics-service-worker | grep 6f1d1c2a-1f0e-4f0b-9a3e-2b1c4d5e6f70
   ```

4. Expected result: **both** streams contain the ID. Record the output as
   acceptance evidence on the verifying ticket (AAP-79590).
