# Emerging Services conformance checker

`check_support_standard.py` verifies a service against the
[Emerging Services Support & Diagnostic Tooling Standard](../../docs/emerging-services-support-standard.md)
(ES-SUP-1..5). It is stdlib-only Python 3 and imports nothing from the service
under test, so any service can vendor it unchanged.

## Run it against metrics-service

```bash
python tools/emerging-services/check_support_standard.py \
  --base-url http://localhost:8080 \
  --health-path /health/ \
  --diagnostics-command "metrics-service tasks diagnose --format json" \
  --bundle-command "metrics-service support-bundle --output-dir /tmp" \
  --bundle-path /tmp/metrics-service-support.tar.gz \
  --log-level-env METRICS_SERVICE_LOG_LEVEL \
  --log-level-observed DEBUG \
  --docs-path docs/support-tooling.md
```

`--log-level-observed` is the level seen in a real log line after setting
`METRICS_SERVICE_LOG_LEVEL=DEBUG`. The checker deliberately never reads its own
environment: a variable exported in your shell says nothing about the service
under test.

`--json` emits the machine-readable contract:

```json
{"version": 1, "overall": "incomplete", "exit_code": 3,
 "results": [{"requirement": "ES-SUP-1", "check": "endpoint reachable",
              "result": "PASS", "detail": "...", "required": true}]}
```

## Exit-code contract

| Code | Meaning |
|---|---|
| `0` | PASS — every required requirement (ES-SUP-1, 2, 3, 5) is fully verified |
| `1` | FAIL — at least one check failed |
| `2` | USAGE — bad arguments |
| `3` | INCOMPLETE — nothing failed, but a required requirement is unverified |

A required requirement is PASS only when **all** of its checks pass, so leaving
out `--diagnostics-command` or `--docs-path` can never produce a green result:
it produces `3`. `SKIP`/`MANUAL` are therefore allowed on recommended ES-SUP-4
but block conformance on the required set.

`FAIL` always wins over `INCOMPLETE`. The failure summary is printed to stderr
in both human and `--json` modes.

## Services with custom key names

ES-SUP-3 key names are service-specific. Map your concepts with a JSON file:

```json
{"running": ["jobs.running"],
 "stuck": ["jobs.stuck"],
 "last_success": ["last_ok"],
 "failures": ["failure_counts_{window}h"],
 "queue_depth": ["backlog"]}
```

```bash
python check_support_standard.py --base-url http://localhost:8080 \
  --diagnostics-command "./svc-diagnostics --json" \
  --diagnostics-map ./diagnostics-map.json \
  --failure-window 24
```

`{window}` is replaced by `--failure-window` (hours, default 24). Dotted paths
are resolved against nested objects. A candidate ending in `*` matches any
sibling key with that prefix, so `failures*` covers `failures_in_window`,
`failures_in_window_seconds`, and so on.

A section that is **present and empty** is valid evidence: zero stuck tasks and
zero failures are results, not missing coverage. The reference implementation
(`tasks diagnose`) reports `running` through its `stuck_tasks` scan (each row
carries `duration_seconds`) and through `queue_depth.dispatcherd_workers` when
the live broker is reachable, so both are accepted for that concept.

## ES-SUP-4 redaction scan

With `--bundle-path` (a file, `.zip`/`.tar` archive, or directory) the checker
scans the produced bundle for unredacted values of `*SECRET*`, `*PASSWORD*`,
`*TOKEN*`, `*KEY*`, `*CREDENTIAL*`, `*AUTH*`, `*PRIVATE*` keys, plus known token
patterns (AWS/GitHub/Slack/Stripe keys, JWTs, private-key blocks,
`Authorization:` headers) and URL userinfo.

Counter and metadata keys are not credentials: a key ending in `_count`,
`_counts`, `_budget`, `_ms`, `_seconds`, `_bytes` or `_policy` is exempt, as is
a value that is redacted, a boolean/`enabled`/`disabled` style token, an
ENV-VAR-style reference such as `METRICS_SERVICE_DB_PASSWORD` or
`${DB_PASSWORD}`, a dotted Python path, or a bare URL without userinfo. A
suspicious key with a real-looking value still fails, so `redacted_key_count: 11`
passes while `DB_PASSWORD: HUNTER2` does not.

Findings report the key or pattern name only — never the secret — so they are
safe to paste into a ticket. Without `--bundle-path` the redaction row is
`MANUAL`, not `PASS`.

## ES-SUP-5 support guide

`--docs-path` is accepted in either form:

1. the guide cites `ES-SUP-1`, `ES-SUP-2` and `ES-SUP-3`; or
2. the guide has an "Emerging Services conformance" section **and** links
   `emerging-services-support-standard.md`.

The second form exists because a support guide can map its tools to the
standard by name without repeating the rule ids.

## Adopting it in another service

1. Copy `check_support_standard.py` into the service's repo (no dependencies needed).
2. Point `--health-path` at the service's health endpoint and `--log-level-env`
   at its `<SERVICE>_LOG_LEVEL` variable.
3. Supply the service's diagnostics command (ES-SUP-3), the optional bundle
   command and output path (ES-SUP-4), and the support guide path (ES-SUP-5).
4. Record the printed evidence table in the service's docs, attach the manual
   evidence, and reference it from the service's row in the standard's
   conformance section.
