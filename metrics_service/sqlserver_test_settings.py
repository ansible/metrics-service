"""SQL Server test settings with a dedicated, isolated test database per alias."""

import os
from copy import deepcopy

from metrics_service.settings import *  # noqa: F403

DATABASES = deepcopy(DATABASES)  # noqa: F405
_test_suffix = os.environ.get("METRICS_SERVICE_TEST_DATABASE_SUFFIX", "sqlserver_poc")

for _alias, _database in DATABASES.items():
    if _database.get("ENGINE") == "mssql":
        _database["TEST"] = {
            **_database.get("TEST", {}),
            "NAME": f"metrics_service_test_{_test_suffix}_{_alias}",
        }
