# Emerging Services conformance checker

`check_support_standard.py` verifies a running service against the
[Emerging Services Support & Diagnostic Tooling Standard](../../docs/emerging-services-support-standard.md)
(ES-SUP-1..4). It is stdlib-only Python 3 and imports nothing from the service
under test, so any service can vendor it unchanged.

## Run it against metrics-service

```bash
python tools/emerging-services/check_support_standard.py \
  --base-url http://localhost:8080 \
  --health-path /health/ \
  --diagnostics-command "metrics-service tasks diagnose --format json" \
  --log-level-env METRICS_SERVICE_LOG_LEVEL
```

Add `--bundle-command "metrics-service support-bundle --dry-run"` to also check
ES-SUP-4, and `--json` for machine-readable output.

Exit code is 0 when all required checks PASS (SKIP is allowed for optional or
unset inputs) and 1 when anything FAILs.

## Adopting it in another service

1. Copy `check_support_standard.py` into the service's repo (no dependencies needed).
2. Point `--health-path` at the service's health endpoint and `--log-level-env`
   at its `<SERVICE>_LOG_LEVEL` variable.
3. Supply the service's diagnostics command (ES-SUP-3) and, if implemented, its
   bundle command (ES-SUP-4).
4. Record the printed evidence table in the service's docs and reference it from
   the service's row in the standard's conformance section.
