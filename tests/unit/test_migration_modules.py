"""Tests for selecting the project migration set from the default database backend."""

import json
import os
import subprocess
import sys

import pytest


def _load_migration_modules_for_engines(default_engine, awx_engine):
    env = os.environ.copy()
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "metrics_service.settings",
            "METRICS_SERVICE_MODE": "development",
            "METRICS_SERVICE_DATABASES__DEFAULT__ENGINE": default_engine,
            "METRICS_SERVICE_DATABASES__AWX__ENGINE": awx_engine,
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; import django; django.setup(); from django.conf import settings; "
            "print(json.dumps({'modules': settings.MIGRATION_MODULES, 'awx_engine': settings.DATABASES['awx']['ENGINE']}, "
            "sort_keys=True))",
        ],
        capture_output=True,
        check=True,
        env=env,
        text=True,
    )
    return result


@pytest.mark.unit
def test_sql_server_default_database_selects_sql_server_migration_packages():
    """An MSSQL default database uses parallel migrations for each project app."""
    result = _load_migration_modules_for_engines("mssql", "django.db.backends.postgresql")
    selection = json.loads(result.stdout.splitlines()[-1])

    assert selection == {
        "awx_engine": "django.db.backends.postgresql",
        "modules": {
            "analytics": "apps.analytics.ms_migrations",
            "core": "apps.core.ms_migrations",
            "dashboard_reports": "apps.dashboard_reports.ms_migrations",
            "dynamic_settings": "apps.dynamic_settings.ms_migrations",
            "tasks": "apps.tasks.ms_migrations",
        },
    }


@pytest.mark.unit
def test_postgres_default_database_selects_postgres_migration_packages():
    """A PostgreSQL default database continues to use the existing migrations."""
    result = _load_migration_modules_for_engines("django.db.backends.postgresql", "mssql")
    selection = json.loads(result.stdout.splitlines()[-1])

    assert selection == {
        "awx_engine": "mssql",
        "modules": {
            "analytics": "apps.analytics.migrations",
            "core": "apps.core.migrations",
            "dashboard_reports": "apps.dashboard_reports.migrations",
            "dynamic_settings": "apps.dynamic_settings.migrations",
            "tasks": "apps.tasks.migrations",
        },
    }
