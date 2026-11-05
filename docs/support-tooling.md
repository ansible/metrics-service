# Support tooling for metrics-service

A task-oriented guide for support engineers. It assumes you know what a
Kubernetes/OpenShift pod is and how to attach a file to a ticket — it does
**not** assume any Python or Django knowledge, and you never need to look at
the source code.

Everything in this guide is **read-only and safe to run on a live customer
instance**, with one exception: `set-log-level`, which changes log verbosity
temporarily and reverts automatically.

> Last verified against: metrics-service 1.0.0 with the support tooling from
> epic AAP-79578 (`support-bundle`, `tasks diagnose`, `set-log-level`).

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
prefer the web pod if the processes are split, since the commands are
read-only):

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

`200` = healthy. `503` = the service cannot reach its database or the upstream
transmission target — check the database first.

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

```
Support bundle written to: /tmp/support-bundle-20261105-124110.tar.gz
```

**Copy it out of the pod:**

```bash
oc cp <NAMESPACE>/<POD_NAME>:/tmp/support-bundle-20261105-124110.tar.gz ./support-bundle.tar.gz
```

The filename always has the form `support-bundle-YYYYMMDD-HHMMSS.tar.gz`; use
the exact name the command printed.

**What is inside** — five JSON files under a `support-bundle-.../` directory:

| File | What it contains |
|------|------------------|
| `tasks.json` | All pending/running tasks (capped at 500), which ones are stuck, and whether the task broker (dispatcherd) answered |
| `ingestion.json` | Last successful/failed collection per collector, daily summary status, upstream (Segment) transmission status |
| `queues.json` | Pending job counts per queue, plus live queue/worker state if the broker answered |
| `schema.json` | Database connectivity, server version, and applied/unapplied migrations |
| `settings.json` | The running configuration with all secret-named values redacted |

Each file also carries a `meta` block with the generation timestamp, hostname,
and metrics-service version.

**Safety and redaction.** The command is read-only: it takes no locks and
writes nothing except the tarball. Any setting whose name contains `SECRET`,
`PASSWORD`, `TOKEN`, `KEY`, `CREDENTIAL`, `AUTH`, or `PRIVATE` (case
insensitive) is replaced with `**REDACTED**` — this covers database passwords
and the Segment write key. Credentials embedded in database URLs
(`scheme://user:password@host`) and `Bearer`/`Basic`/`Token` header values are
also replaced. `settings.json` includes a `_redaction` section listing how
many fields were redacted (paths only, never values). The authoritative marker
list lives in [`apps/core/support_bundle/redaction.py`](../apps/core/support_bundle/redaction.py).

**Verify before attaching (optional):**

```bash
tar -tzf support-bundle.tar.gz
tar -xOzf support-bundle.tar.gz '*/settings.json' | grep -c REDACTED
```

The second command prints the number of redacted values (a count of 0 on a
real deployment is suspicious — do not attach the bundle and mention it in the
ticket).

**Dry run** — prints what the bundle would contain, writes nothing:

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service support-bundle --dry-run
```

**Troubleshooting:**

- `Output directory does not exist or is not a directory` — use `--output-dir /tmp` or another path that exists in the pod.
- `"available": false` in the `dispatcherd` section of `tasks.json`/`queues.json` is not fatal — the bundle falls back to database-only data. It usually means the task broker control channel could not be reached from the pod you ran in; try running the command from the worker pod and compare.

**Attach the tarball to the ticket.** Do not extract and paste individual
files unless asked — the tarball is the unit engineering expects.

If you have host-level access to the machine (not just pod access) and the
customer runs `sos`, the sosreport plugin under
[`tools/sosreport/`](../tools/sosreport/) collects the same bundle as part of a
system report — see [`tools/sosreport/TESTING.md`](../tools/sosreport/TESTING.md).

## 3. Diagnose task health

**When:** tasks are late, failing, or look stuck.

**Run this:**

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service tasks diagnose
```

**What good output looks like** (example trimmed):

```
Metrics service task diagnostics
==================================================
Generated at: 2026-11-05T12:42:42.784172+00:00
Stuck threshold: 3600s
Failure window: 24h

Stuck tasks (0)
--------------------------------------------------
No stuck tasks.
Last successful run by task type
--------------------------------------------------
  FUNCTION                                 LAST SUCCESS                 AGE
  collect_hourly_metrics                   2026-11-05T11:00:04+00:00    01:42:38
  daily_metrics_rollup                     2026-11-05T00:05:11+00:00    12:37:31
  send_anonymized_to_segment               never                        never

Failures in the last 24h
--------------------------------------------------
  collect_hourly_metrics: 3 failure(s) | last: 2026-11-05T10:00:06+00:00
    Last error: OperationalError: could not connect to server
Queue depth
--------------------------------------------------
  QUEUE            PENDING (DB)   QUEUED  BLOCKED  DELAYED
  metrics                    14        0        0        0
  maintenance                 4        0        0        0
  dashboard                   2        0        0        0
Workers: 1 | Producers: 1
  worker-0: idle | current task: idle

Use --format json for scripting.
```

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
  error message (truncated).
- **Queue depth** — `PENDING (DB)` is the backlog recorded in the database;
  `QUEUED`/`BLOCKED`/`DELAYED` are live broker counts. A pending backlog that
  is not shrinking means workers are down or the broker channel is broken.
  `Live dispatcherd state unavailable: ...` means the live counts could not be
  collected — the DB numbers are still valid.

**What to do:** if the worker pod is missing or `Workers: 0`, restart the
worker deployment. Otherwise capture the output for the ticket.

**Options** (all optional):

```bash
metrics-service tasks diagnose --format json        # machine-readable, for ticket attachments and scripts
metrics-service tasks diagnose --hours 72           # failure lookback window in hours (default 24)
metrics-service tasks diagnose --stuck-timeout 1800 # stuck threshold in seconds (default: TASK_TIMEOUT)
metrics-service tasks diagnose --limit 50           # max rows per section (default 20)
```

Save JSON to a file for the ticket:

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service tasks diagnose --format json > diagnose.json
```

## 4. Temporarily raise the log level

**When:** you need DEBUG-level detail in the logs while reproducing a problem,
without restarting the service (a restart would clear the very state you are
looking at).

**Run this:**

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service set-log-level DEBUG --ttl 900
```

`LEVEL` is one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. `--ttl` is
seconds before the change expires (default and maximum: 3600 = 1 hour).

**What good output looks like:**

```
Log level set to DEBUG until 2026-11-05T12:58:38.950171+00:00 (set by cli:metrics-abc12:support).
Running processes apply the change within one request/task cycle (refresh interval: 1s). Restarting the service reverts to INFO.
```

**Check the current state:**

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service set-log-level --show
```

```
Override: level=DEBUG expires_at=2026-11-05T12:58:38.950171+00:00 set_by=cli:metrics-abc12:support modified=2026-11-05T12:43:38.955895+00:00 (active).
```

or, when nothing is set:

```
No override set (using baseline INFO).
```

**What it affects:** the change is shared through the database and picked up
by every service process — web requests, task workers, and the scheduler —
within roughly one request/task cycle (the refresh interval is 1 second by
default). It applies to the service's own loggers (`metrics_service`, `apps`,
`django`, `ansible_base`); it does not change the web server's (Gunicorn)
access-log level.

**It reverts automatically.** The override expires at the TTL, and any process
started after the override was written ignores it — restarting the service
always returns to the level configured by the deployment
(`METRICS_SERVICE_LOG_LEVEL`, default `INFO`). You never need to remember to
undo it.

**Turn it off early:**

```bash
oc exec -n <NAMESPACE> <POD_NAME> -- metrics-service set-log-level --clear
```

```
Runtime log level override cleared.
```

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

Do not paste raw logs that may contain customer data into the ticket body —
attach them as files. The support bundle is already redacted; logs are not.

## 6. Escalation

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
  unavailable from every pod.
- The problem reproduces with DEBUG logs but the logs show nothing actionable.

Escalations feed the RCA process tracked under epic AAP-79581.

## 7. Reference

| Command | Purpose |
|---------|---------|
| `metrics-service support-bundle [--output-dir PATH] [--dry-run]` | Collect a redacted diagnostic tarball |
| `metrics-service tasks diagnose [--format text\|json] [--hours N] [--stuck-timeout N] [--limit N]` | Task health: stuck tasks, last success, failures, queue depth |
| `metrics-service set-log-level LEVEL [--ttl N]` | Temporarily change the log level (auto-reverts) |
| `metrics-service set-log-level --show` | Show the active log level override |
| `metrics-service set-log-level --clear` | Remove the log level override early |

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
