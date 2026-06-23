# test_sync_filter_caches.py — Unit tests for sync_dashboard_filter_caches task

from unittest.mock import MagicMock, call, patch

import pytest

from apps.dashboard_reports.models import AWXJobTemplate, AWXLabel, AWXOrganization, AWXProject
from apps.dashboard_reports.tasks import _sync_cache, sync_dashboard_filter_caches

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

# Patch at the import site inside the task function (lazy imports inside the function body)
_FILTER_OPTIONS_MOD = "metrics_utility.library.collectors.dashboard.filter_options"
_TASKS_MOD = "apps.dashboard_reports.tasks"


def _patch_fetchers(orgs=None, templates=None, projects=None, labels=None):
    """Return a context manager that patches all four fetch_* functions."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch(f"{_FILTER_OPTIONS_MOD}.fetch_organizations", return_value=orgs or []))
    stack.enter_context(patch(f"{_FILTER_OPTIONS_MOD}.fetch_job_templates", return_value=templates or []))
    stack.enter_context(patch(f"{_FILTER_OPTIONS_MOD}.fetch_projects", return_value=projects or []))
    stack.enter_context(patch(f"{_FILTER_OPTIONS_MOD}.fetch_labels", return_value=labels or []))
    return stack


@pytest.mark.unit
@pytest.mark.django_db
class TestSyncDashboardFilterCaches:
    def test_returns_success_with_counts(self):
        mock_db = MagicMock()
        with (
            patch(f"{_TASKS_MOD}.get_db_connection", return_value=mock_db),
            _patch_fetchers(
                orgs=[{"id": 1, "name": "Default"}],
                templates=[{"id": 10, "name": "Deploy"}],
                projects=[{"id": 5, "name": "Proj"}],
                labels=[{"id": 42, "name": "production"}],
            ),
        ):
            result = sync_dashboard_filter_caches()

        assert result["status"] == "success"
        assert result["organizations"] == 1
        assert result["job_templates"] == 1
        assert result["projects"] == 1
        assert result["labels"] == 1

    def test_populates_all_four_cache_models(self):
        mock_db = MagicMock()
        with (
            patch(f"{_TASKS_MOD}.get_db_connection", return_value=mock_db),
            _patch_fetchers(
                orgs=[{"id": 1, "name": "Default"}],
                templates=[{"id": 10, "name": "Deploy"}],
                projects=[{"id": 5, "name": "Proj"}],
                labels=[{"id": 42, "name": "production"}],
            ),
        ):
            sync_dashboard_filter_caches()

        assert AWXOrganization.objects.filter(org_id=1).exists()
        assert AWXJobTemplate.objects.filter(template_id=10).exists()
        assert AWXProject.objects.filter(project_id=5).exists()
        assert AWXLabel.objects.filter(label_id=42).exists()

    def test_returns_error_when_db_connection_fails(self):
        with patch(f"{_TASKS_MOD}.get_db_connection", side_effect=Exception("DB unreachable")):
            result = sync_dashboard_filter_caches()
        assert result["status"] == "error"
        assert "DB unreachable" in result["error"]

    def test_deletes_stale_entries_across_all_models(self):
        AWXOrganization.objects.create(org_id=99, name="Stale")
        AWXLabel.objects.create(label_id=99, name="OldLabel")
        mock_db = MagicMock()
        with (
            patch(f"{_TASKS_MOD}.get_db_connection", return_value=mock_db),
            _patch_fetchers(
                orgs=[{"id": 1, "name": "Default"}],
                labels=[{"id": 42, "name": "production"}],
            ),
        ):
            sync_dashboard_filter_caches()

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
