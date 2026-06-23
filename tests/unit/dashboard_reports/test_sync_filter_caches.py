# test_sync_filter_caches.py — Unit tests for sync_dashboard_filter_caches task

import sys
from unittest.mock import MagicMock, patch

import pytest

from apps.dashboard_reports.models import AWXJobTemplate, AWXLabel, AWXOrganization, AWXProject
from apps.dashboard_reports.tasks import _sync_cache, sync_dashboard_filter_caches

# ---------------------------------------------------------------------------
# The sync_dashboard_filter_caches task lazily imports
# metrics_utility.library.collectors.dashboard.filter_options at call time.
# That module lives in the companion metrics-utility PR and may not be
# installed in CI yet.  We inject a stub into sys.modules so the import
# succeeds regardless of what version of metrics-utility is installed.
# ---------------------------------------------------------------------------

_FILTER_OPTIONS_PATH = "metrics_utility.library.collectors.dashboard.filter_options"
_DASHBOARD_PKG_PATH = "metrics_utility.library.collectors.dashboard"


def _make_filter_options_stub(orgs=None, templates=None, projects=None, labels=None):
    """Return a MagicMock module whose fetch_* functions return the given lists."""
    stub = MagicMock()
    stub.fetch_organizations.return_value = orgs or []
    stub.fetch_job_templates.return_value = templates or []
    stub.fetch_projects.return_value = projects or []
    stub.fetch_labels.return_value = labels or []
    return stub

# ---------------------------------------------------------------------------
# _sync_cache helper
# ---------------------------------------------------------------------------

ORGS = [{"id": 1, "name": "Default"}, {"id": 2, "name": "Operations"}]
LABELS = [{"id": 42, "name": "production"}, {"id": 43, "name": "staging"}]


@pytest.mark.unit
@pytest.mark.django_db
class TestSyncCacheHelper:
    def test_creates_records_when_none_exist(self):
        _sync_cache(AWXOrganization, "org_id", ORGS)
        assert AWXOrganization.objects.count() == 2
        assert AWXOrganization.objects.get(org_id=1).name == "Default"
        assert AWXOrganization.objects.get(org_id=2).name == "Operations"

    def test_updates_name_for_existing_record(self):
        AWXOrganization.objects.create(org_id=1, name="Old Name")
        _sync_cache(AWXOrganization, "org_id", [{"id": 1, "name": "New Name"}])
        assert AWXOrganization.objects.get(org_id=1).name == "New Name"

    def test_deletes_stale_records_not_in_rows(self):
        AWXOrganization.objects.create(org_id=99, name="Stale")
        _sync_cache(AWXOrganization, "org_id", ORGS)
        assert not AWXOrganization.objects.filter(org_id=99).exists()

    def test_returns_count_of_synced_rows(self):
        count = _sync_cache(AWXOrganization, "org_id", ORGS)
        assert count == 2

    def test_empty_rows_deletes_all_existing(self):
        AWXOrganization.objects.create(org_id=1, name="Default")
        _sync_cache(AWXOrganization, "org_id", [])
        assert AWXOrganization.objects.count() == 0

    def test_idempotent_when_run_twice(self):
        _sync_cache(AWXOrganization, "org_id", ORGS)
        _sync_cache(AWXOrganization, "org_id", ORGS)
        assert AWXOrganization.objects.count() == 2


# ---------------------------------------------------------------------------
# sync_dashboard_filter_caches task
# ---------------------------------------------------------------------------

_TASKS_MOD = "apps.dashboard_reports.tasks"


@pytest.mark.unit
@pytest.mark.django_db
class TestSyncDashboardFilterCaches:
    def _run_with_stub(self, orgs=None, templates=None, projects=None, labels=None, db_error=None):
        """Run sync_dashboard_filter_caches with a stub filter_options module in sys.modules.

        Injecting via sys.modules guarantees the lazy import inside the task function
        resolves to our stub regardless of what version of metrics-utility is installed.
        """
        stub = _make_filter_options_stub(orgs=orgs, templates=templates, projects=projects, labels=labels)
        # Ensure the parent package attribute also resolves so attribute-lookup patches work
        extra = {
            _FILTER_OPTIONS_PATH: stub,
        }
        mock_db = MagicMock() if db_error is None else None
        with patch.dict(sys.modules, extra):
            if db_error:
                with patch(f"{_TASKS_MOD}.get_db_connection", side_effect=db_error):
                    return sync_dashboard_filter_caches()
            with patch(f"{_TASKS_MOD}.get_db_connection", return_value=mock_db):
                return sync_dashboard_filter_caches()

    def test_returns_success_with_counts(self):
        result = self._run_with_stub(
            orgs=[{"id": 1, "name": "Default"}],
            templates=[{"id": 10, "name": "Deploy"}],
            projects=[{"id": 5, "name": "Proj"}],
            labels=[{"id": 42, "name": "production"}],
        )
        assert result["status"] == "success"
        assert result["organizations"] == 1
        assert result["job_templates"] == 1
        assert result["projects"] == 1
        assert result["labels"] == 1

    def test_populates_all_four_cache_models(self):
        self._run_with_stub(
            orgs=[{"id": 1, "name": "Default"}],
            templates=[{"id": 10, "name": "Deploy"}],
            projects=[{"id": 5, "name": "Proj"}],
            labels=[{"id": 42, "name": "production"}],
        )
        assert AWXOrganization.objects.filter(org_id=1).exists()
        assert AWXJobTemplate.objects.filter(template_id=10).exists()
        assert AWXProject.objects.filter(project_id=5).exists()
        assert AWXLabel.objects.filter(label_id=42).exists()

    def test_returns_error_when_db_connection_fails(self):
        result = self._run_with_stub(db_error=Exception("DB unreachable"))
        assert result["status"] == "error"
        assert "DB unreachable" in result["error"]

    def test_deletes_stale_entries_across_all_models(self):
        AWXOrganization.objects.create(org_id=99, name="Stale")
        AWXLabel.objects.create(label_id=99, name="OldLabel")
        self._run_with_stub(
            orgs=[{"id": 1, "name": "Default"}],
            labels=[{"id": 42, "name": "production"}],
        )
        assert not AWXOrganization.objects.filter(org_id=99).exists()
        assert not AWXLabel.objects.filter(label_id=99).exists()
        assert AWXOrganization.objects.filter(org_id=1).exists()
        assert AWXLabel.objects.filter(label_id=42).exists()

    def test_task_in_task_functions(self):
        from apps.tasks.tasks import TASK_FUNCTIONS

        assert "sync_dashboard_filter_caches" in TASK_FUNCTIONS

    def test_task_in_task_metadata(self):
        from apps.tasks.tasks import TASK_METADATA

        meta = TASK_METADATA["sync_dashboard_filter_caches"]
        assert meta["queue"] == "dashboard"
        assert "database" in meta["parameters"]
