"""Create the small SQL Server AWX fixture used by the SQL Server POC."""

import os
import sys
from datetime import UTC, datetime

import django
from django.conf import settings
from django.db import connections
from metrics_utility.library.collectors.controller.job_host_summary import job_host_summary
from metrics_utility.library.collectors.controller.job_host_summary_service import job_host_summary_service
from metrics_utility.library.collectors.util import ensure_functions

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metrics_service.settings")
django.setup()


_TABLE_DDL = (
    """
    IF OBJECT_ID(N'dbo.django_content_type', N'U') IS NULL
        CREATE TABLE dbo.django_content_type (
            id INT NOT NULL PRIMARY KEY,
            model NVARCHAR(100) NOT NULL
        )
    """,
    """
    IF OBJECT_ID(N'dbo.main_organization', N'U') IS NULL
        CREATE TABLE dbo.main_organization (
            id INT NOT NULL PRIMARY KEY,
            name NVARCHAR(512) NOT NULL
        )
    """,
    """
    IF OBJECT_ID(N'dbo.main_inventory', N'U') IS NULL
        CREATE TABLE dbo.main_inventory (
            id INT NOT NULL PRIMARY KEY,
            name NVARCHAR(512) NOT NULL
        )
    """,
    """
    IF OBJECT_ID(N'dbo.main_unifiedjobtemplate', N'U') IS NULL
        CREATE TABLE dbo.main_unifiedjobtemplate (
            id INT NOT NULL PRIMARY KEY,
            name NVARCHAR(512) NOT NULL
        )
    """,
    """
    IF OBJECT_ID(N'dbo.main_unifiedjob', N'U') IS NULL
        CREATE TABLE dbo.main_unifiedjob (
            id INT NOT NULL PRIMARY KEY,
            created DATETIMEOFFSET NOT NULL,
            finished DATETIMEOFFSET NULL,
            unified_job_template_id INT NULL,
            ansible_version NVARCHAR(100) NULL,
            launch_type NVARCHAR(100) NULL,
            organization_id INT NULL,
            polymorphic_ctype_id INT NULL,
            name NVARCHAR(512) NULL
        )
    """,
    """
    IF OBJECT_ID(N'dbo.main_job', N'U') IS NULL
        CREATE TABLE dbo.main_job (
            unifiedjob_ptr_id INT NOT NULL PRIMARY KEY,
            project_id INT NULL,
            inventory_id INT NULL
        )
    """,
    """
    IF OBJECT_ID(N'dbo.main_jobhostsummary', N'U') IS NULL
        CREATE TABLE dbo.main_jobhostsummary (
            id INT NOT NULL PRIMARY KEY,
            created DATETIMEOFFSET NOT NULL,
            modified DATETIMEOFFSET NOT NULL,
            host_name NVARCHAR(1024) NOT NULL,
            changed INT NOT NULL,
            dark INT NOT NULL,
            failures INT NOT NULL,
            ok INT NOT NULL,
            processed INT NOT NULL,
            skipped INT NOT NULL,
            failed BIT NOT NULL,
            host_id INT NULL,
            job_id INT NOT NULL,
            ignored INT NOT NULL,
            rescued INT NOT NULL
        )
    """,
    """
    IF OBJECT_ID(N'dbo.main_host', N'U') IS NULL
        CREATE TABLE dbo.main_host (
            id INT NOT NULL PRIMARY KEY,
            variables NVARCHAR(MAX) NOT NULL
        )
    """,
)

_FIXTURE_ROWS = (
    (
        "DELETE FROM dbo.main_jobhostsummary WHERE id IN (2001, 2002)",
        (),
    ),
    ("DELETE FROM dbo.main_host WHERE id IN (301, 302)", ()),
    (
        "IF NOT EXISTS (SELECT 1 FROM dbo.django_content_type WHERE id = 1) "
        "INSERT INTO dbo.django_content_type (id, model) VALUES (1, N'job')",
        (),
    ),
    (
        "IF NOT EXISTS (SELECT 1 FROM dbo.main_organization WHERE id = 1) "
        "INSERT INTO dbo.main_organization (id, name) VALUES (1, N'SQL Server PoC Org')",
        (),
    ),
    (
        "IF NOT EXISTS (SELECT 1 FROM dbo.main_inventory WHERE id = 1) "
        "INSERT INTO dbo.main_inventory (id, name) VALUES (1, N'SQL Server PoC Inventory')",
        (),
    ),
    (
        "IF NOT EXISTS (SELECT 1 FROM dbo.main_unifiedjobtemplate WHERE id = 1) "
        "INSERT INTO dbo.main_unifiedjobtemplate (id, name) VALUES (1, N'SQL Server PoC Job Template')",
        (),
    ),
    (
        "IF NOT EXISTS (SELECT 1 FROM dbo.main_unifiedjobtemplate WHERE id = 2) "
        "INSERT INTO dbo.main_unifiedjobtemplate (id, name) VALUES (2, N'SQL Server PoC Project')",
        (),
    ),
    (
        "IF NOT EXISTS (SELECT 1 FROM dbo.main_unifiedjob WHERE id = 1001) "
        "INSERT INTO dbo.main_unifiedjob "
        "(id, created, finished, unified_job_template_id, ansible_version, launch_type, "
        "organization_id, polymorphic_ctype_id, name) "
        "VALUES (1001, %s, %s, 1, N'2.18.0', N'manual', 1, 1, N'SQL Server PoC Job')",
        ("2026-10-09T12:05:00+00:00", "2026-10-09T12:30:00+00:00"),
    ),
    (
        "IF NOT EXISTS (SELECT 1 FROM dbo.main_job WHERE unifiedjob_ptr_id = 1001) "
        "INSERT INTO dbo.main_job (unifiedjob_ptr_id, project_id, inventory_id) VALUES (1001, 2, 1)",
        (),
    ),
    (
        "IF EXISTS (SELECT 1 FROM dbo.main_host WHERE id = 301) "
        "UPDATE dbo.main_host SET variables = %s WHERE id = 301 "
        "ELSE INSERT INTO dbo.main_host (id, variables) VALUES (301, %s)",
        (
            '{"ansible_host":"json.example","ansible_connection":"ssh"}',
            '{"ansible_host":"json.example","ansible_connection":"ssh"}',
        ),
    ),
    (
        "IF EXISTS (SELECT 1 FROM dbo.main_host WHERE id = 302) "
        "UPDATE dbo.main_host SET variables = %s WHERE id = 302 "
        "ELSE INSERT INTO dbo.main_host (id, variables) VALUES (302, %s)",
        (
            "ansible_host: yaml.example\nansible_connection: ssh\n",
            "ansible_host: yaml.example\nansible_connection: ssh\n",
        ),
    ),
    (
        "INSERT INTO dbo.main_jobhostsummary "
        "(id, created, modified, host_name, changed, dark, failures, ok, processed, skipped, failed, host_id, job_id, ignored, rescued) "
        "VALUES (2001, %s, %s, N'json.example', 1, 0, 0, 1, 1, 0, 0, 301, 1001, 0, 0)",
        ("2026-10-09T12:35:00+00:00", "2026-10-09T12:35:00+00:00"),
    ),
    (
        "INSERT INTO dbo.main_jobhostsummary "
        "(id, created, modified, host_name, changed, dark, failures, ok, processed, skipped, failed, host_id, job_id, ignored, rescued) "
        "VALUES (2002, %s, %s, N'yaml.example', 0, 0, 0, 1, 1, 0, 0, 302, 1001, 0, 0)",
        ("2026-10-09T12:40:00+00:00", "2026-10-09T12:40:00+00:00"),
    ),
)


def create_poc_databases() -> None:
    """Create the two dedicated POC databases if they do not exist."""
    import pyodbc

    broker = settings.DISPATCHERD_SQLSERVER
    server = str(broker["server"])
    if broker.get("port"):
        server = f"{server},{broker['port']}"

    def escaped(value):
        return "{" + str(value).replace("}", "}}") + "}"

    connection_string = (
        f"DRIVER={escaped(broker['driver'])};SERVER={server};DATABASE=master;"
        f"UID={escaped(broker['user'])};PWD={escaped(broker['password'])};"
        "Encrypt=yes;TrustServerCertificate=yes"
    )
    connection = pyodbc.connect(connection_string, autocommit=True, timeout=15)
    try:
        with connection.cursor() as cursor:
            for database in ("metrics_service_poc", "metrics_awx_poc"):
                cursor.execute(f"IF DB_ID(N'{database}') IS NULL CREATE DATABASE [{database}]")
    finally:
        connection.close()


def load_awx_fixture() -> None:
    """Create the required tables/data and install helper UDFs on the AWX alias."""
    create_poc_databases()
    connection = connections["awx"]
    if connection.vendor != "microsoft":
        raise RuntimeError("DATABASES.awx must use the mssql backend to load this fixture")

    with connection.cursor() as cursor:
        for statement in _TABLE_DDL:
            cursor.execute(statement)
        for statement, params in _FIXTURE_ROWS:
            cursor.execute(statement, params)

    ensure_functions(connection)
    _verify_helper_functions(connection)
    _verify_collectors(connection)
    _verify_metrics_service_database_primitives()
    sys.stdout.write(f"SQL Server AWX fixture ready in database '{connection.settings_dict['NAME']}'.\n")


def _verify_helper_functions(connection) -> None:
    """Exercise SQL Server UDF behavior for JSON validation and flat YAML fields."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                dbo.metrics_utility_is_valid_json(%s),
                dbo.metrics_utility_is_valid_json(%s),
                dbo.metrics_utility_parse_yaml_field(%s, %s),
                dbo.metrics_utility_parse_yaml_field(%s, %s)
            """,
            [
                '{"ansible_host":"json.example"}',
                "{invalid json",
                'ansible_host: "yaml.example"\nansible_connection: ssh\n',
                "ansible_host",
                "ansible_host=yaml.example\nansible_connection=ssh\n",
                "ansible_connection",
            ],
        )
        result = cursor.fetchone()

    expected = (True, False, "yaml.example", "ssh")
    if tuple(result) != expected:
        raise RuntimeError(f"SQL Server helper function results {tuple(result)!r} did not match {expected!r}")


def _verify_collectors(connection) -> None:
    """Run both supported collectors against the inserted JSON/YAML fixture rows."""
    since = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    until = datetime(2026, 10, 9, 13, 0, tzinfo=UTC)
    connection.ensure_connection()
    raw_connection = connection.connection
    service_rows = job_host_summary_service(db=raw_connection, since=since, until=until).gather()
    legacy_rows = job_host_summary(db=raw_connection, since=since, until=until).gather()

    if len(service_rows) != 2 or len(legacy_rows) != 2:
        raise RuntimeError(f"Expected two rows from each collector; got {len(service_rows)} and {len(legacy_rows)}")

    legacy_by_host = {row["host_name"]: row for _, row in legacy_rows.iterrows()}
    expected_hosts = {
        "json.example": ("json.example", "ssh"),
        "yaml.example": ("yaml.example", "ssh"),
    }
    for hostname, (expected_host, expected_connection) in expected_hosts.items():
        row = legacy_by_host[hostname]
        if (row["ansible_host_variable"], row["ansible_connection_variable"]) != (
            expected_host,
            expected_connection,
        ):
            raise RuntimeError(f"Legacy collector returned incorrect host variables for {hostname!r}")


def _verify_metrics_service_database_primitives() -> None:
    """Check the SQL Server AWX readiness probe and default-database application lock."""
    from apps.tasks.utils import awx_db_ready, run_with_lock

    if not awx_db_ready():
        raise RuntimeError("Metrics-service did not detect main_unifiedjob in the SQL Server AWX database")

    result = run_with_lock(
        "sqlserver_poc_fixture_check",
        "sqlserver_poc_fixture_check",
        lambda: {"status": "success"},
    )
    if result != {"status": "success"}:
        raise RuntimeError(f"SQL Server task lock check returned {result!r}")


if __name__ == "__main__":
    load_awx_fixture()
