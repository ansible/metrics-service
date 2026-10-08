Developer tools, unrelated to production.

- `tasks/` — task dashboard and runner scripts (talk to local API)
- `dev.sh` — dev server with auto-reload (runserver + dispatcherd + scheduler)
- `seed-awx-demo.sql` — disposable AWX data for exercising collectors locally

Seed the local AWX database after starting the compose stack:

```bash
podman exec -i postgres psql -U awx -d awx < tools/seed-awx-demo.sql
```

The seed adds four completed UTC hours of jobs, events, host summaries, workflow
nodes, and indirect-node audits, plus supporting inventory, credentials, host
metrics, and monthly summary data. Host changes, host metrics, and indirect-node
audits are timestamped in the current UTC day for daily collector windows. It is
safe to run repeatedly; a marker job prevents duplicate demo rows.

Performance tests are in `../metrics-utility/tools/`
(`service_perf/`, `dashboard_perf/`).
