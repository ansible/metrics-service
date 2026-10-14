"""Copy these values into settings.local.py and set METRICS_SERVICE_SQLSERVER_PASSWORD."""

import os

_SQLSERVER_PASSWORD = os.environ.get("METRICS_SERVICE_SQLSERVER_PASSWORD", "")

DATABASES__default__ENGINE = "mssql"
DATABASES__default__HOST = "127.0.0.1"
DATABASES__default__PORT = "1433"
DATABASES__default__NAME = "metrics_service_poc"
DATABASES__default__USER = "sa"
DATABASES__default__PASSWORD = _SQLSERVER_PASSWORD
DATABASES__default__OPTIONS = {
    "driver": "ODBC Driver 18 for SQL Server",
    "extra_params": "Encrypt=yes;TrustServerCertificate=yes",
}

DATABASES__awx__ENGINE = "mssql"
DATABASES__awx__HOST = "127.0.0.1"
DATABASES__awx__PORT = "1433"
DATABASES__awx__NAME = "metrics_awx_poc"
DATABASES__awx__USER = "sa"
DATABASES__awx__PASSWORD = _SQLSERVER_PASSWORD
DATABASES__awx__OPTIONS = {
    "driver": "ODBC Driver 18 for SQL Server",
    "extra_params": "Encrypt=yes;TrustServerCertificate=yes",
}

# Keep dispatcherd on its separate database. These names remain independent of
# the Django DATABASES aliases.
DISPATCHERD_SQLSERVER__SERVER = "127.0.0.1"
DISPATCHERD_SQLSERVER__PORT = 1433
DISPATCHERD_SQLSERVER__DATABASE = "dispatcherd"
DISPATCHERD_SQLSERVER__USER = "sa"
DISPATCHERD_SQLSERVER__PASSWORD = _SQLSERVER_PASSWORD
DISPATCHERD_SQLSERVER__DRIVER = "ODBC Driver 18 for SQL Server"
DISPATCHERD_SQLSERVER__TRUST_SERVER_CERTIFICATE = "yes"

# Prevent scheduled groups with unported AWX SQL from starting. Explicit API
# tasks without a _feature_flag still run, including both job-host-summary types.
FEATURE__METRICS_COLLECTION = False
FEATURE__DASHBOARD_COLLECTION = False
FEATURE__INDIRECT_NODE_COLLECTION = False
FEATURE__ANONYMIZED_DATA_COLLECTION = False
