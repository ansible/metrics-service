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
  --bundle-command "metrics-service support-bundle --dry-run" \
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
are resolved against nested objects.

## ES-SUP-4 redaction scan

With `--bundle-path` (a file, `.zip`/`.tar` archive, or directory) the checker
scans the produced bundle for unredacted values of `*SECRET*`, `*PASSWORD*`,
`*TOKEN*`, `*KEY*`, `*CREDENTIAL*`, `*AUTH*`, `*PRIVATE*` keys, plus known token
patterns (AWS/GitHub/Slack/Stripe keys, JWTs, private-key blocks) and URL
userinfo. Findings report the key or pattern name only — never the secret — so
they are safe to paste into a ticket. Without `--bundle-path` the redaction row
is `MANUAL`, not `PASS`.

## Adopting it in another service

1. Copy `check_support_standard.py` into the service's repo (no dependencies needed).
2. Point `--health-path` at the service's health endpoint and `--log-level-env`
   at its `<SERVICE>_LOG_LEVEL` variable.
3. Supply the service's diagnostics command (ES-SUP-3), the optional bundle
   command and output path (ES-SUP-4), and the support guide path (ES-SUP-5).
4. Record the printed evidence table in the service's docs, attach the manual
   evidence, and reference it from the service's row in the standard's
   conformance section.
