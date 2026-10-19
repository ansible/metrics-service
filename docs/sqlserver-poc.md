# SQL Server proof of concept

This POC runs metrics-service's `default` database, an AWX-shaped fixture, and the dispatcherd broker on three SQL Server databases. PostgreSQL remains the default backend unless an alias's `ENGINE` is changed.

## Prerequisites

- SQL Server 2022 reachable on port 1433. The POC fixture uses SQL Server scalar functions and `JSON_VALUE`.
- Microsoft ODBC Driver 18, unixODBC, and pyodbc installed in the development environment.
- Local `AAP-96550` checkouts of dispatcherd, metrics-utility, and django-ansible-base next to metrics-service.

The service pins `mssql-django` to the 1.x line so its SQL Server connections use pyodbc and the existing ODBC Driver 18 installation. Microsoft documents the `mssql` engine and `driver`/`extra_params` settings in its [mssql-django connection options](https://learn.microsoft.com/en-us/sql/connect/python/mssql-django/connection-options?view=sql-server-ver17). The [2.0 release notes](https://github.com/microsoft/mssql-django/releases) add a required `mssql-python` package even when pyodbc remains the selected driver.

The local django-ansible-base branch bounds indexed RBAC and resource-registry keys so SQL Server can create their indexes. Role names, object IDs, and parent references are limited to 450 characters; permission codenames are limited to 100.

## Configure local settings

Copy [settings.local.mssql.example.py](examples/settings.local.mssql.example.py) into `settings.local.py`, then set `METRICS_SERVICE_SQLSERVER_PASSWORD` in the environment or root `.env` file. It configures:

- Django `default` → `metrics_service_poc`
- Django `awx` → `metrics_awx_poc`
- dispatcherd → its separate `dispatcherd` database

`DATABASES.default.ENGINE` and `DATABASES.awx.ENGINE` are independent. Each can be `mssql` or `django.db.backends.postgresql`; the POC exercises both as SQL Server. PostgreSQL-specific `sslmode` defaults are applied only to PostgreSQL aliases.

The example turns off scheduled collector groups whose AWX SQL remains PostgreSQL-specific. The two job-host-summary collectors remain available through explicit API-created tasks without a `_feature_flag`.

## Create and load the AWX fixture

Install the local dispatcherd and metrics-utility branches after syncing the metrics-service environment:

```bash
uv pip install --python .venv/bin/python -e ../dispatcherd
uv pip install --python .venv/bin/python -e ../metrics-utility
```

Keep the local checkouts first on `PYTHONPATH` when running migrations, the fixture, or the dev server. This ensures Python uses the checked-out dispatcherd, metrics-utility, and django-ansible-base changes even if the environment also contains packaged versions.

The fixture command creates the two named POC databases if missing, creates the eight minimal AWX-shaped tables, inserts one job with JSON and YAML host variables, installs the two helper functions, runs both collectors against the raw pyodbc connection, checks AWX readiness, and acquires/releases a SQL Server application lock. Use `UV_NO_SYNC=true` when starting the dev script so `uv run` does not replace the editable metrics-utility checkout.

Django's `migrate` command and the dev server expect their configured database to already exist. Run the AWX fixture first; it creates `metrics_service_poc` and `metrics_awx_poc`.

```bash
PYTHONPATH=../metrics-utility:../django-ansible-base .venv/bin/python tools/sqlserver_awx_fixture.py
PYTHONPATH=../django-ansible-base UV_NO_SYNC=true .venv/bin/python manage.py migrate --database default
```

### Set up the dispatcherd database

Dispatcherd uses a separate SQL Server database named `dispatcherd`. Its [`setup.sql`](../../dispatcherd/tools/sql_server/setup.sql) script creates that database, the `dbo.dispatcherd_messages` table, and its index. Run the script with `sqlcmd` inside the running SQL Server Podman container. Run these commands from the metrics-service repository root:

```bash
# Find the SQL Server container name.
podman ps --format '{{.Names}}'

# Copy the script from the host into that container. Replace <container-name>.
podman cp ../dispatcherd/tools/sql_server/setup.sql <container-name>:/tmp/dispatcherd-setup.sql

# Execute the script. sqlcmd prompts for the sa password.
podman exec -it <container-name> /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -C -i /tmp/dispatcherd-setup.sql
```

`-C` tells `sqlcmd` to trust the SQL Server container's certificate. The `-i` option runs the copied file, including its `GO` batch separators. If the container does not have `/opt/mssql-tools18/bin/sqlcmd`, try the older path `/opt/mssql-tools/bin/sqlcmd`.

To verify that the script created the message table, run this query from the container. `sqlcmd` prompts for the `sa` password again; a non-NULL `messages_table_id` means the table exists.

```bash
podman exec -it <container-name> /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -C -d dispatcherd \
  -Q "SELECT OBJECT_ID(N'dbo.dispatcherd_messages', N'U') AS messages_table_id"
```

The fixture contains `main_jobhostsummary`, `main_unifiedjob`, `main_job`, `main_unifiedjobtemplate`, `main_inventory`, `main_organization`, `django_content_type`, and the legacy collector's additional `main_host` subset (`id`, `variables`). It is not a conversion of the full AWX PostgreSQL schema dump.

## Run metrics-service

Start the dev API, dispatcherd worker, and scheduler:

```bash
PYTHONPATH=../dispatcherd:../metrics-utility:../django-ansible-base UV_NO_SYNC=true tools/dev.sh --init
```

With `settings.local.py` configured for the local dev superuser created by `tools/dev.sh --init`, submit both collector tasks for the fixture's fixed hour:

```bash
http --ignore-stdin --auth admin:admin POST :8000/api/v1/tasks/schedule_immediate/ \
  name="SQL Server job host summary service" \
  function_name=collect_hourly_metrics \
  task_data:='{"collector_type":"job_host_summary_service","hour_timestamp":"2026-10-09T12:00:00Z"}'

http --ignore-stdin --auth admin:admin POST :8000/api/v1/tasks/schedule_immediate/ \
  name="SQL Server legacy job host summary" \
  function_name=collect_hourly_metrics \
  task_data:='{"collector_type":"job_host_summary","hour_timestamp":"2026-10-09T12:00:00Z"}'
```

Poll each task with `GET /api/v1/tasks/{id}/`. Both should complete through dispatcherd. `job_host_summary_service` writes its hourly collection and analytics payload; legacy `job_host_summary` writes an analytics payload and exercises both SQL Server helper functions using the JSON and YAML fixture rows.

To run the unit suite against a dedicated SQL Server test database, put the same local checkouts first on `PYTHONPATH` and use the SQL Server test settings module. Change `METRICS_SERVICE_TEST_DATABASE_SUFFIX` when you need a fresh test database after changing migrations.

```bash
PYTHONPATH=../dispatcherd:../metrics-utility:../django-ansible-base \
METRICS_SERVICE_TEST_DATABASE_SUFFIX=sqlserver_poc \
.venv/bin/python -m pytest --ds=metrics_service.sqlserver_test_settings tests/unit -q
```

The dashboard leaderboard and report details endpoints can also be called against SQL Server `default`; their user-facing response shape remains unchanged, including zero-filled time buckets.

## Scope

The SQL Server claim covers metrics-service's `default` database, the two job-host-summary collectors against this fixture, task locks/readiness checks, and the targeted dashboard leaderboard/chart paths. Other metrics-utility collectors and remaining direct AWX SQL (including Controller retention and Automation Reports AWX views) remain PostgreSQL-only in this POC. Dispatcherd stays an independent broker database.
