# Support tooling for metrics-service

A task-oriented guide for support engineers. It assumes you know what a
Kubernetes/OpenShift pod is and how to attach a file to a ticket — it does
**not** assume any Python or Django knowledge, and you never need to look at
the source code to run the commands below.

Everything in this guide is **read-only and safe to run on a live customer
instance**, with one exception: `set-log-level`, which changes log verbosity
temporarily and reverts automatically.

> Last verified against: the tool branches that ship in epic AAP-79578 —
> `support-bundle` (#530, tip `8183cf9`), `tasks diagnose` (#531, tip
> `0aa25fc`), `set-log-level` (#522, tip `e5da276`) and the Emerging Services
> standard (#533, tip `a4580d8`) — on 2026-11-06, with metrics-service 1.0.0.
> Every sample output below was produced by running the command against those
> tips. Re-check the flags and sample output after the PRs merge.
>
> **Blocked by / related.** This guide documents four unmerged PRs and must
> land after them: [#530](https://github.com/ansible/metrics-service/pull/530)
> (`support-bundle`), [#531](https://github.com/ansible/metrics-service/pull/531)
> (`tasks diagnose`), [#522](https://github.com/ansible/metrics-service/pull/522)
> (`set-log-level`), and
> [#533](https://github.com/ansible/metrics-service/pull/533) — the Emerging
> Services support standard, whose conformance checker consumes this guide. The
> rule-by-rule mapping is in
> [§6](#6-emerging-services-conformance).

## 0. Before you start

metrics-service collects automation metrics from Ansible Automation Platform
and forwards anonymized data upstream. It runs as **three cooperating
processes**, which may live in the same pod or in separate pods:

| Process | Role | What breaks if it is down |
|---------|------|---------------------------|
| Web | Serves the REST API | API requests fail; tasks keep running |
| Worker | Executes background tasks | Tasks sit pending forever |
| Scheduler | Submits pending tasks to workers | Nothing new starts; existing tasks finish |

This is why the web pod can look healthy while tasks are stuck — check all
three.

Find the pods:

```bash
oc get pods -n <NAMESPACE> | grep metrics
```

Run any command from this guide inside a pod (any metrics-service pod works;
prefer the web pod if the processes are split, since every command except
`set-log-level` is read-only):

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service <COMMAND>
```

Read recent logs (logs go to stdout, there is no log file inside the pod):

```bash
oc logs -n <NAMESPACE> <POD_NAME> --tail=500
```

Health check (port is `8080` unless the deployment overrides it):

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/health/
```

`200` = healthy. `503` = the **database** check failed — only the database can
make `/health/` return `503`. A failed upstream (Segment) transmission does
**not** change the status code; it shows up inside the `200` response body as
`checks.segment_send.status: "failed"`, so read the body, not just the code:

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- curl -s http://localhost:8080/health/
```

On builds that include the health-check hardening from #533, the body reports
a stable reason (`"error: database_unavailable"`) and the driver message —
which includes the database host, port and user — is written to the pod logs
only, so run `oc logs` for the detail. Older builds repeat the driver message
in the response body. `checks.segment_send` is absent until there is at least
one payload to report on.

A few things that make a command return a misleadingly empty result:

- **Wrong database.** The command runs in the pod you `oc exec` into. If that
  pod points at a different database than the web pods (split-pod or DR
  setups), it describes a different instance and the problem looks absent.
  Compare with the `database` block in `schema.json`.
- **Missing `metrics-service` script.** Older or minimal images may not have it
  on `PATH`; use the `python manage.py` form in [§8](#8-reference).
- **Clock skew.** Timestamps (`expires_at`, `started_at`, log times) are
  compared across pods. If pods disagree about the current time, TTL expiry and
  the stuck threshold look wrong; check `date -u` in two pods before chasing
  either.

If you cannot `oc exec`/`oc cp` into the customer's cluster (RBAC), send the
command blocks from this guide to the customer and ask them to run them and
attach the output.

## 1. "Something is broken" — which tool do I use?

| Symptom | Start with |
|---------|-----------|
| Any non-trivial issue; first contact on a ticket | [Collect a support bundle](#2-collect-a-support-bundle) |
| Tasks never run, are late, or fail repeatedly | [Diagnose task health](#3-diagnose-task-health) |
| A task has been running forever | [Diagnose task health](#3-diagnose-task-health) (stuck tasks) |
| You need more detail in the logs while reproducing | [Temporarily raise the log level](#4-temporarily-raise-the-log-level) |
| API errors / service appears down | `health/` check + `oc logs`, then a support bundle |

## 2. Collect a support bundle

**When:** first contact on any non-trivial issue. The bundle is a single
tarball that answers most "what does the instance look like" questions.

**Run this** (the output directory must already exist; `/tmp` always does):

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service support-bundle --output-dir /tmp
```

**What good output looks like:**

```text
Support bundle written to: /tmp/support-bundle-20261105-124110.tar.gz
```

**Copy it out of the pod:**

```bash
oc cp <NAMESPACE>/<POD_NAME>:/tmp/support-bundle-20261105-124110.tar.gz ./support-bundle.tar.gz
```

The filename always has the form `support-bundle-YYYYMMDD-HHMMSS.tar.gz`; a
second run in the same second gets a `-2` suffix (`...-2.tar.gz`) instead of
overwriting the first. Use the exact name the command printed.

**What is inside** — five JSON files under a `support-bundle-.../` directory:

| File | What it contains |
|------|------------------|
| `tasks.json` | All pending/running tasks (capped at 500), which ones are stuck, and whether the task broker (dispatcherd) answered |
| `ingestion.json` | Last successful/failed collection per collector, daily summary status, upstream (Segment) transmission status, and the `cluster_id` seen by analytics payloads |
| `queues.json` | Pending job counts per queue, plus live queue/worker state if the broker answered |
| `schema.json` | Database connectivity, server version, applied/unapplied migrations, and the database host/name in use |
| `settings.json` | The running configuration with secret-named keys and secret-shaped values redacted |

Each file also carries a `meta` block with the generation timestamp, hostname,
process ID, and the metrics-service, Django and Python versions.

**Safety and redaction.** The command is read-only: it takes no locks and
writes nothing except the tarball, which is created `0600` and never overwrites
an existing file or follows a pre-planted symlink. Redaction runs over **every
section**, not just `settings.json`: any key whose name contains `SECRET`,
`PASSWORD`, `TOKEN`, `KEY`, `CREDENTIAL`, `AUTH`, or `PRIVATE` (case
insensitive) is replaced with `**REDACTED**`, and secrets embedded in values
are stripped too — URL userinfo (`scheme://user:password@host`, including the
password-only `redis://:pw@host` form), `Bearer`/`Basic`/`Token` header values,
and `password=`/`token=`/`api_key=`-style pairs in free-text error messages.
`settings.json` also carries a `_redaction` section: `redacted_key_count` is an
integer — how many keys/values the pass removed — and `redacted_paths` lists
the dotted paths of the fields that were redacted (paths only, never values).
A real example:

```json
{
  "redacted_key_count": 11,
  "redacted_paths": [
    "AUTHENTICATION_BACKENDS",
    "AUTH_PASSWORD_VALIDATORS",
    "AUTH_USER_MODEL",
    "DATABASES.awx.PASSWORD",
    "DATABASES.default.PASSWORD",
    "LOGGING.loggers.ansible_base.jwt_consumer.common.auth",
    "MANAGE_ORGANIZATION_AUTH",
    "REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES",
    "REST_FRAMEWORK.UNAUTHENTICATED_TOKEN",
    "REST_FRAMEWORK.UNAUTHENTICATED_USER",
    "SECRET_KEY"
  ]
}
```

The authoritative marker list lives in
[`apps/core/support_bundle/redaction.py`](../apps/core/support_bundle/redaction.py).

**Verify before attaching (optional):**

```bash
tar -tzf support-bundle.tar.gz
tar -xOzf support-bundle.tar.gz '*/settings.json' | grep -c REDACTED || true
```

The second command prints the number of **matching lines**, not the number of
values — one line can contain several redactions. It is a smoke test: `0` on a
real deployment is suspicious, so do not attach the bundle and mention it in
the ticket. `grep -c` exits with status 1 when there are no matches, which is
why the command ends in `|| true`; without it a checklist runner or a `set -e`
script treats the suspicious case as a command failure.

**Dry run** — prints a per-section manifest (filename, record count, serialized
size in bytes) and writes nothing:

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service support-bundle --dry-run
```

```json
[
  {
    "name": "tasks.json",
    "records": 6,
    "bytes": 7703
  },
  {
    "name": "ingestion.json",
    "records": 7,
    "bytes": 3447
  },
  {
    "name": "queues.json",
    "records": 5,
    "bytes": 904
  },
  {
    "name": "schema.json",
    "records": 12,
    "bytes": 4943
  },
  {
    "name": "settings.json",
    "records": 3,
    "bytes": 14476
  }
]
```

(the byte counts depend on the data in the instance)

**Troubleshooting:**

- `Output directory does not exist: /path` or `Output directory is not a directory: /path` — use `--output-dir /tmp` or another path that exists inside the pod.
- The `dispatcherd` block in `tasks.json` and `queues.json` reports how the
  live control probe went. `"available": false` is **not** fatal — the bundle
  falls back to database-only data and sets
  `"error": "no replies from dispatcherd (control timeout)"`. This is the
  normal result on a default deployment even when dispatcherd is running
  (see [§3](#3-diagnose-task-health) for the cause and the one-line fix):

  ```json
  {
    "available": false,
    "error": "no replies from dispatcherd (control timeout)",
    "node_count": 0,
    "nodes": [],
    "partial": false,
    "reply_counts": {
      "running": 0,
      "workers": 0
    },
    "running": {},
    "workers": {}
  }
  ```

  When the control channel reaches the daemon the same block reports the
  nodes that answered, how many replies each control command got, and the live
  worker/producer state. `"partial": true` means some control commands answered
  and others did not; `nodes`/`node_count` name the dispatcherd nodes that
  replied and `reply_counts` shows the per-command reply count:

  ```json
  {
    "available": true,
    "node_count": 1,
    "nodes": [
      "8d94258e-53c0-4f86-adc8-1f921060bdae"
    ],
    "partial": false,
    "reply_counts": {
      "running": 1,
      "workers": 1
    },
    "running": {},
    "workers": {
      "worker-0": {
        "active_cancel": false,
        "age": 12.571263792007812,
        "current_task": null,
        "current_task_uuid": null,
        "finished_count": 0,
        "pid": 86562,
        "status": "ready",
        "worker_id": 0
      }
    }
  }
  ```

- The command still returns within a few seconds when the broker is dead: all control probes in one section share a ~5 s budget.

**Attach the tarball to the ticket.** Do not extract and paste individual
files unless asked — the tarball is the unit engineering expects.

If you have host-level access to the machine (not just pod access) and the
customer runs `sos`, the sosreport plugin under
[`tools/sosreport/`](../tools/sosreport/) does **not** collect a second bundle.
It copies the dynaconf settings override files (an allow-listed set:
`settings.*`, `*.yaml`, `*.yml`, `*.toml`, `*.json`, `*.conf`, `*.ini` and
`.env`), forbids key material, scrubs secret values, and captures the output of
`metrics-service support-bundle --dry-run` (the manifest above) and
`pip freeze`. No bundle contents and no tarball — see
[`tools/sosreport/TESTING.md`](../tools/sosreport/TESTING.md).

## 3. Diagnose task health

**When:** tasks are late, failing, or look stuck.

**Run this:**

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service tasks diagnose
```

**What good output looks like** (one real run; this instance has a stuck task
and a failing task type):

```text
Metrics service task diagnostics
==================================================
Generated at: 2026-11-06T13:41:25.488201+00:00
Stuck threshold: 3600s
Failure window: 24h

Stuck tasks (1)
--------------------------------------------------
  Hourly metrics collection (ID: 1142)
    Function: collect_hourly_metrics
    Started: 2026-11-06T11:34:27.129894+00:00 | Duration: 02:06:58
    Attempts: 1 | Worker: unknown
    Reported by dispatcherd: none (worker may have died)

Last successful run by task type
--------------------------------------------------
  FUNCTION                                 LAST SUCCESS                 AGE
  hello_world                              never                        never
  cleanup_old_tasks                        never                        never
  sync_resources_from_gateway              never                        never
  cleanup_activitystream                   never                        never
  cleanup_metrics_data                     never                        never
  collect_snapshot_metrics                 never                        never
  collect_daily_metrics                    never                        never
  collect_analytics_on_demand              never                        never
  daily_metrics_rollup                     never                        never
  daily_anonymize_and_prepare              never                        never
  send_anonymized_to_segment               never                        never
  collect_dashboard_reports_data           never                        never
  collect_dashboard_reports_initial_data   never                        never
  backfill_dashboard_organization_names    never                        never
  backfill_dashboard_job_types             never                        never
  cleanup_dashboard_reports_old_data       never                        never
  cleanup_dashboard_telemetry              never                        never
  sync_dashboard_job_records               never                        never
  sync_dashboard_host_summaries            never                        never
  collect_hourly_metrics                   2026-11-06T11:57:40.361912+00:00 01:43:45

Failures in the last 24h
--------------------------------------------------
  collect_hourly_metrics: 3 failure(s) | last: 2026-11-06T12:37:40.361912+00:00
    Last error: OperationalError: could not connect to server
Queue depth
--------------------------------------------------
  QUEUE            PENDING (DB)   QUEUED  BLOCKED  DELAYED
  dashboard                   2        0        0        0
  maintenance                 4        0        0        0
  metrics                    14        0        0        0
Live dispatcherd state unavailable: no replies from dispatcherd (control timeout)

Use --format json for scripting.
```

The `Live dispatcherd state unavailable` line is what a default deployment
prints **even when dispatcherd is healthy** — see
[Live dispatcherd state](#live-dispatcherd-state-is-unavailable-on-a-default-deployment)
below. The database columns (`PENDING (DB)`, stuck tasks, last success,
failures) are unaffected.

Queues are listed in alphabetical order of the channel names configured in
`apps/settings/dispatcherd.yaml` (`dashboard`, `maintenance`, `metrics` by
default).

**How to read it:**

- **Stuck tasks** — tasks marked running for longer than the stuck threshold
  (default 3600s = 60 minutes, from the `TASK_TIMEOUT` setting). The line
  `Reported by dispatcherd: none (worker may have died)` means the database
  says the task is running but no worker reports executing it — the usual
  cause is a dead worker pod.
- **Last successful run by task type** — `never` means that task type has not
  completed successfully since the database was created. A task type that has
  succeeded before but is now stale points at a scheduler or worker problem.
- **Failures in the last 24h** — count per task type with the most recent
  error message (truncated). The header shows the `--hours` window actually
  used.
- **Queue depth** — `PENDING (DB)` is the backlog recorded in the database;
  `QUEUED`/`BLOCKED`/`DELAYED` are live broker counts. A pending backlog that
  is not shrinking means workers are down or the broker channel is broken.
  `Live dispatcherd state unavailable: ...` means no control reply arrived —
  the database numbers are still valid. `Warning: ignored N malformed
  dispatcherd worker entries` means dispatcherd answered but some worker
  entries had an unexpected shape (for example its JSON-parse-error fallback);
  the rest of the report is still valid. Reply metadata such as `node_id` is
  filtered out, so a healthy deployment does not print this line.
  `Warning: <command> query failed: ...` means one control command failed while
  the others answered.

**What to do:** if the worker pod is missing, or the report shows `Workers: 0`
while dispatcherd answered, restart the worker deployment. If you see
`Live dispatcherd state unavailable`, it is almost always the default-deployment
configuration gap described below, not a dead worker — check the worker pod with
`oc get pods` and `oc logs` before restarting anything. Otherwise capture the
output for the ticket.

### Live dispatcherd state is unavailable on a default deployment

This is a known limitation of the current tool, not a symptom of a broken
deployment. `tasks diagnose` asks dispatcherd for live state over its control
channel, but `get_control_from_settings()` returns a `Control` object whose
`queuename` is `None`. With the `pg_notify` broker that makes the request get
published to the reply queue itself, so the only thing that comes back is an
echo of the request. The tool discards those echoes (correctly — they prove
nothing about the daemon), finds no real reply, and prints:

```text
Live dispatcherd state unavailable: no replies from dispatcherd (control timeout)
```

This happens with a healthy daemon running, and JSON output shows
`"live_available": false` with the same `error`. Everything derived from the
database — stuck tasks, last success, failures, `PENDING (DB)` — is unaffected.

**To get live state**, point the control request at a channel the daemon
listens on by setting `default_publish_channel` on the `pg_notify` broker in
`apps/settings/dispatcherd.yaml` (the `metrics` channel is the one
`set-log-level` already uses):

```yaml
brokers:
  pg_notify:
    channels:
      - 'dashboard'
      - 'maintenance'
      - 'metrics'
    default_publish_channel: metrics
```

Restart is not required: each `tasks diagnose` run re-reads the file, and the
daemon already listens on `metrics` by default. The queue-depth section then
reports the live worker and producer state instead of the unavailable line:

```text
Workers: 1 | Producers: 1
  worker-0: ready | current task: idle
  pg_notify-producer: produced 8
```

The support bundle reads the same setting and switches from
`"available": false` to the populated block shown in
[§2](#2-collect-a-support-bundle). Once the fix ships in code, the setting is no
longer needed.

**Options** (all optional):

```bash
metrics-service tasks diagnose --format json        # machine-readable, for ticket attachments and scripts
metrics-service tasks diagnose --hours 72           # failure lookback window in hours (default 24)
metrics-service tasks diagnose --stuck-timeout 1800 # stuck threshold in seconds (default: TASK_TIMEOUT)
metrics-service tasks diagnose --limit 50           # max rows per section (default 20)
```

**JSON output.** `--format json` emits one JSON object with
`schema_version: 2`. The failure section is `failures_in_window`, and
`window_hours` echoes the `--hours` value, so a `--hours 72` run is labelled
correctly (there is no `failures_last_24h` key). `queue_depth` carries the live
state as `dispatcherd_workers`, `dispatcherd_producers`, `live_available` and
`error` alongside the per-queue database counts; `failures_in_window` rows carry
`failure_count`, `last_failure_at`, `last_error` and `legacy_task_failures`.
Errors go to stderr, so redirecting stdout always produces parseable JSON:

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service tasks diagnose --format json > diagnose.json
```

This is a real run with the `last_success` array removed for length (the command
emits it as well, one entry per known task type, in the same object):

```json
{
  "failures_in_window": [
    {
      "failure_count": 3,
      "function_name": "collect_hourly_metrics",
      "last_error": "OperationalError: could not connect to server",
      "last_failure_at": "2026-11-06T12:37:40.361912+00:00",
      "legacy_task_failures": 0
    }
  ],
  "generated_at": "2026-11-06T13:41:26.617283+00:00",
  "queue_depth": {
    "dispatcherd_producers": [],
    "dispatcherd_workers": [],
    "error": "no replies from dispatcherd (control timeout)",
    "live_available": false,
    "query_errors": {},
    "queues": [
      {
        "blocked_live": 0,
        "delayed_live": 0,
        "pending_in_db": 2,
        "queue": "dashboard",
        "queued_live": 0
      },
      {
        "blocked_live": 0,
        "delayed_live": 0,
        "pending_in_db": 4,
        "queue": "maintenance",
        "queued_live": 0
      },
      {
        "blocked_live": 0,
        "delayed_live": 0,
        "pending_in_db": 14,
        "queue": "metrics",
        "queued_live": 0
      }
    ],
    "warnings": []
  },
  "schema_version": 2,
  "stuck_tasks": [
    {
      "attempts": 1,
      "duration_seconds": 7619.487389,
      "execution_id": null,
      "function_name": "collect_hourly_metrics",
      "name": "Hourly metrics collection",
      "reported_by": [],
      "started_at": "2026-11-06T11:34:27.129894+00:00",
      "task_id": 1142,
      "worker_id": null
    }
  ],
  "task_timeout_seconds": 3600,
  "window_hours": 24
}
```

## 4. Temporarily raise the log level

**When:** you need DEBUG-level detail in the logs while reproducing a problem,
without restarting the service (a restart would clear the very state you are
looking at).

> **Watch the log volume.** `DEBUG` is far noisier than `INFO` on a busy
> instance: every request and task can produce several lines, and enabling the
> `django.db.backends` logger adds a line per SQL statement. An hour at DEBUG
> can flood the log pipeline or fill the node's disk. Use the shortest TTL that
> covers the reproduction, collect the excerpt with `oc logs`, then clear it.

**Run this:**

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service set-log-level DEBUG --ttl 900
```

`LEVEL` is one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. `--ttl` is
seconds before the change expires (default and maximum: 3600 = 1 hour). A TTL
above 3600 is rejected with
`TTL must not exceed RUNTIME_LOG_LEVEL_MAX_TTL (3600s)`, and `0` is rejected
too.

**What good output looks like:**

```text
Log level set to DEBUG until 2026-11-06T13:51:56.612270+00:00 (set by cli:cshiels-mac:cshiels).
Web requests apply the change within ~1s. Dispatcherd workers apply it within ~1s or when they next start a task. The task scheduler picks it up at its next check interval (30s by default, 60s when started via metrics-service run). Restarting the service reverts to the configured log levels.
```

**Check the current state:**

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service set-log-level --show
```

```text
Override: level=DEBUG expires_at=2026-11-06T13:51:56.612270+00:00 set_by=cli:cshiels-mac:cshiels modified=2026-11-06T13:36:56.619673+00:00 (active).
```

or, when nothing is set:

```text
No override set (using baseline INFO).
```

An expired row that has not been cleaned up is shown with `(expired)` and a
second line, `Expired overrides are ignored; processes are using INFO.`

**What it affects:** the change is shared through the database and picked up
by every service process, but not at the same moment:

| Process | When the new level applies |
|---------|----------------------------|
| Web requests | within ~1 s (request middleware) |
| dispatcherd workers | within ~1 s while idle (each forked worker has its own refresh thread), or when a busy worker starts its next task |
| Task scheduler | at its next check interval — 30 s by default, 60 s under `metrics-service run` |
| dispatcherd main process | not reliably: the immediate `set`/`--clear` notify currently fails silently (see below), so in practice it keeps its old level until it restarts |

**Known limitation — the dispatcherd main process.** `set-log-level` and
`--clear` try to push the change to the dispatcherd main process immediately
over its control channel. At the current tip that call raises
`TypeError: Broker.__init__() got an unexpected keyword argument 'sslmode'`.
The database connection dict is handed to `dispatcherd.control.Control` in a
shape the broker does not accept: Django's `OPTIONS` keys are splatted as
broker kwargs, and the flat `dbname`/`host` fields fail the same way once they
are removed. The error is logged at DEBUG and the change is dropped. Two
consequences for triage:

- The dispatcherd main-process logger keeps its previous level until that
  process restarts. Do not expect DEBUG lines from `dispatcherd.service.*` in
  the pod log during the override window.
- A **TTL expiry** is never pushed to that process at all; it is only applied
  when it restarts. `--clear` is affected in the same way.

Worker loggers are *not* affected — they poll from their own thread and also
re-read the override at task entry. Tracked as a follow-up to #522.

It applies to the service's own loggers (`metrics_service`, `apps`, `django`,
`ansible_base`, and `dispatcherd` when it is configured); it does not change
the web server's (Gunicorn) access-log level.

**It reverts automatically.** The override expires at the TTL, and any process
started after the override was written ignores it. A **full** restart therefore
returns every process to the level configured by the deployment
(`METRICS_SERVICE_LOG_LEVEL`, default `INFO`, or a per-logger
`LOGGING__loggers__<name>__level` override). A **partial** restart — a rolling
update, an HPA scale-up, or one OOM-killed pod — does not: old pods keep the
raised level while new pods run at the configured level until the TTL expires
or you `--clear`. Expect mixed log levels across pods in `oc logs` during that
window, and clear early if it confuses triage.

**Turn it off early:**

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service set-log-level --clear
```

```text
Runtime log level override cleared.
```

If there was nothing to clear, the command prints
`No runtime log level override was set.`

While the level is raised, collect what you need with `oc logs`, then clear
(or let it expire). Attach the log excerpt to the ticket.

## 5. Attaching diagnostics to a ticket

Checklist for a well-formed ticket:

- The **support bundle tarball** (always, for non-trivial issues).
- The **`tasks diagnose` JSON or text output** (if the issue involves tasks).
- Pod names and the namespace, plus **timestamps in UTC** and the timezone the
  customer reports symptoms in.
- The **exact commands you ran** and their output.
- A **log excerpt** covering the incident window if you raised the log level.

Every file in the bundle has been through the redaction pass, but that pass
removes *secrets*, not *customer data*: `meta.hostname`, `cluster_id` in
`ingestion.json`, and the database host/name in `schema.json` are all present,
and an over-eager pattern match can remove part of a free-text error that would
have been diagnostically useful. Logs are not redacted at all. Treat both as
customer data and attach them as files rather than pasting them into the ticket
body.

**Correlating logs with a request.** Every API call has a request ID: the
`X-Request-ID` response header echoes it, verbose logs render it as
`[<uuid>]`, and JSON logs carry a `request_id` field. Tasks created by that
request keep the ID through to the worker, so one search by the UUID returns
both the API and worker lines. Outbound trace headers are still being wired
(`traceparent`, and Segment-side propagation depends on
`metrics-utility#635`), so do not assume the ID is present in upstream
(Segment) request logs yet.

## 6. Emerging Services conformance

The Emerging Services team's normative
[support and diagnostic tooling standard](emerging-services-support-standard.md)
(`docs/emerging-services-support-standard.md`, v1.0, PR
[#533](https://github.com/ansible/metrics-service/pull/533)) defines five
requirements, `ES-SUP-1` to `ES-SUP-5`. The checker that enforces it
(`tools/emerging-services/check_support_standard.py --docs-path
docs/support-tooling.md`) reads **this guide** for the documentation evidence,
so the mapping is recorded here. The tooling in this guide satisfies:

| Rule | How the documented tooling meets it | Evidence in this guide |
|------|-------------------------------------|------------------------|
| **ES-SUP-1** — health endpoint | The `GET /health/` contract is unauthenticated, returns `{"status": "<good\|degraded>", "checks": {...}}`, maps a database failure to HTTP 503 with a stable reason token, and keeps driver text in the pod log. | [§0](#0-before-you-start): the `curl` health check, the 200/503 rule and the `checks.segment_send` caveat. |
| **ES-SUP-2** — log level via environment variable | The application level is controlled by `METRICS_SERVICE_LOG_LEVEL`, which this guide documents with its default (`INFO`); `set-log-level` then raises and restores it at runtime. | [§4](#4-temporarily-raise-the-log-level): the variable and default in the "reverts automatically" paragraph, plus the temporary-override commands. |
| **ES-SUP-3** — task/job state visibility | `tasks diagnose` is read-only and reports four of the five mandated concepts from the database: stuck jobs, last success per type, failure counts over a configurable window, and queue depth. `--format json` is the machine-readable form (`schema_version: 2`). | [§3](#3-diagnose-task-health): the text and JSON samples, `--hours`/`--stuck-timeout`/`--limit`, and the `failures_in_window`/`queue_depth` keys. |
| **ES-SUP-4** — diagnostic bundle | `support-bundle` writes a timestamped tarball with every section redacted: secret-named keys become `**REDACTED**`, URL userinfo/`Authorization`/`key=value` values are stripped, the file is `0600`, and the `_redaction` block records paths (never values). | [§2](#2-collect-a-support-bundle): the five-section table, the redaction rules, and the real `_redaction` block. |
| **ES-SUP-5** — documentation | This document is the support-engineer guide: copy-paste `oc exec` commands, expected output produced from the shipping tips, and no assumption of source knowledge. | This section and every command block above. |

**Partially satisfied.** Three gaps are documented rather than hidden because
the checker or the deployment cannot verify them yet:

- **ES-SUP-3, "jobs currently running and their elapsed time"** — the command
  lists *stuck* tasks with their elapsed time, not every running job, and it
  names the failure section `failures_in_window` rather than the checker's
  `failures`/`failure_counts`. Two of the five concepts therefore fail the
  v1.0 checker's **default** key map; supply both aliases when you run it:

  ```bash
  check_support_standard.py \
    --diagnostics-command 'metrics-service tasks diagnose --format json' \
    --diagnostics-map '{"running": "stuck_tasks", "failures": "failures_in_window"}'
  ```

  With that map all five concepts pass against the JSON shown in
  [§3](#3-diagnose-task-health). Full live running state additionally needs the
  control channel configured; without it the report is database-only (see
  [§3](#live-dispatcherd-state-is-unavailable-on-a-default-deployment)).
- **ES-SUP-3 / ES-SUP-4, live dispatcherd state** — on a default deployment
  `Control.queuename is None`, so both the diagnose command and the bundle
  report `live_available`/`available` as false even with a healthy daemon. They
  do so honestly (echoed requests are discarded, not counted). Set
  `default_publish_channel` as shown in [§3](#live-dispatcherd-state-is-unavailable-on-a-default-deployment)
  to make the live sections work.
- **ES-SUP-4, checker strictness** — the v1.0 key-name heuristic flags
  metadata counters such as `redacted_key_count` as unredacted values. The
  bundle itself contains no credentials; tightening the heuristic is tracked in
  [#533](https://github.com/ansible/metrics-service/pull/533).

`ES-SUP-2` is otherwise verified by the checker with `--log-level-env
METRICS_SERVICE_LOG_LEVEL --log-level-observed <LEVEL>`; `ES-SUP-3` and
`ES-SUP-5` need `--diagnostics-command`/`--docs-path`, and `ES-SUP-4` needs
`--bundle-path` to move from `MANUAL` to `PASS`.

## 7. Escalation

**Support can resolve alone:**

- Restart a missing/crashed worker or scheduler pod.
- Raise the log level temporarily to capture DEBUG detail.
- Collect and attach a support bundle and diagnose output.

**Escalate to engineering when:**

- Stuck tasks persist after a worker restart.
- The same task type fails repeatedly with the same error.
- `schema.json` in the bundle shows unapplied migrations on a healthy
  deployment, or the database will not connect.
- `tasks.json`/`queues.json` report the task broker (dispatcherd) as
  unavailable **and** the worker pods are missing or crash-looping. On their
  own, `dispatcherd.available: false` and the `Live dispatcherd state
  unavailable` line are the default-deployment limitation described in
  [§3](#live-dispatcherd-state-is-unavailable-on-a-default-deployment), not a
  reason to escalate.
- The problem reproduces with DEBUG logs but the logs show nothing actionable.

Escalations feed the RCA process tracked under epic AAP-79581.

## 8. Reference

| Command | Purpose |
|---------|---------|
| `metrics-service support-bundle [--output-dir PATH] [--dry-run]` | Collect a redacted diagnostic tarball |
| `metrics-service tasks diagnose [--format text\|json] [--hours N] [--stuck-timeout N] [--limit N]` | Task health: stuck tasks, last success, failures, queue depth |
| `metrics-service set-log-level LEVEL [--ttl N]` | Temporarily change the log level (auto-reverts) |
| `metrics-service set-log-level --show` | Show the active log level override |
| `metrics-service set-log-level --clear` | Remove the log level override early |

`set-log-level` also accepts `--local`, which applies the level to the
short-lived command process itself. It exists for smoke testing only; support
engineers do not need it.

If the `metrics-service` script is not on `PATH` inside the container, the
equivalent `python manage.py` invocations are:

```bash
python manage.py support_bundle --output-dir /tmp
python manage.py metrics_service tasks diagnose
python manage.py set_log_level DEBUG --ttl 900
```

(note the underscores in `support_bundle` and `set_log_level`).

Related documentation:

- [task-system.md](task-system.md) — task architecture and the other `tasks` subcommands
- [task-state-machine.md](task-state-machine.md) — task states, retries, crash recovery
- [README](../README.md) — deployment, endpoints, and configuration reference
