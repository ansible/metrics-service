# SQL Server broker for dispatcherd

metrics-service sends dispatcherd task messages to a dedicated SQL Server
database named `dispatcherd`. The metrics-service application database remains
PostgreSQL in this transition step; broker connection settings are independent
of Django's `DATABASES` setting.

## Connection settings

Configure these environment variables using your deployment's secret store:

| Variable | Default | Description |
|---|---|---|
| `METRICS_SERVICE_DISPATCHERD_SQLSERVER__SERVER` | Empty | SQL Server host or address |
| `METRICS_SERVICE_DISPATCHERD_SQLSERVER__PORT` | `1433` | SQL Server TCP port |
| `METRICS_SERVICE_DISPATCHERD_SQLSERVER__DATABASE` | `dispatcherd` | Broker database |
| `METRICS_SERVICE_DISPATCHERD_SQLSERVER__USER` | Empty | SQL Server login |
| `METRICS_SERVICE_DISPATCHERD_SQLSERVER__PASSWORD` | Empty | SQL Server password |
| `METRICS_SERVICE_DISPATCHERD_SQLSERVER__DRIVER` | `ODBC Driver 18 for SQL Server` | Installed ODBC driver name |
| `METRICS_SERVICE_DISPATCHERD_SQLSERVER__TRUST_SERVER_CERTIFICATE` | `yes` | Set to `no` when the server certificate is trusted |
| `METRICS_SERVICE_DISPATCHERD_SQLSERVER__CONNECT_TIMEOUT_SECONDS` | `15` | Maximum time to establish a broker connection |
| `METRICS_SERVICE_DISPATCHERD_SQLSERVER__QUERY_TIMEOUT_SECONDS` | `30` | Maximum time for a broker SQL statement |

The broker uses `pyodbc` 5.3 or newer and Microsoft ODBC Driver 18. The
metrics-service production and development images install the driver and
unixODBC runtime. Running metrics-service directly from a host virtualenv also
requires unixODBC and Microsoft ODBC Driver 18 on that host; installing the
Python `pyodbc` package alone is not enough.

Until a dispatcherd release containing the SQL Server broker is available,
local development must install the sibling checkout after syncing metrics-service:

```bash
# From components/metrics-service
uv pip install --python .venv/bin/python --editable '../dispatcherd[sql_server]'
```

Container images that install dispatcherd from the package index also need a
dispatcherd release containing this broker before they can use the SQL Server
configuration.

Use `localhost` when metrics-service runs directly on the host. From a separate
Podman container connecting to a host-published SQL Server port, use
`host.containers.internal` or the SQL Server container's network alias when the
containers share a network.

## Database setup

Run `components/dispatcherd/tools/sql_server/setup.sql` against the SQL Server
instance with an administrative login. The idempotent script creates the
`dispatcherd` database, the `dbo.dispatcherd_messages` table, and its channel
index. The metrics-service runtime login needs permissions to insert, select,
and delete message rows in that table.

## Delivery behavior

Dispatcherd polls the `metrics`, `dashboard`, and `maintenance` channels. A
consumer atomically deletes a batch as it claims it, so the broker delivers a
claimed message at most once. metrics-service keeps task state in its PostgreSQL
application database and periodically resubmits pending work if dispatcherd was
unavailable before the message was claimed.
