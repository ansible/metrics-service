"""Integration tests for the ``support_bundle`` management command."""

import json
import tarfile
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.tasks.models import Task

pytestmark = pytest.mark.integration

EXPECTED_FILES = {"tasks.json", "ingestion.json", "queues.json", "schema.json", "settings.json"}


@pytest.fixture(autouse=True)
def unavailable_dispatcherd():
    """Keep the command deterministic by forcing the DB-only fallback."""
    with patch(
        "apps.core.support_bundle.collectors.ensure_dispatcherd_configured",
        side_effect=RuntimeError("dispatcherd unavailable in tests"),
    ):
        yield


@pytest.mark.django_db
def test_command_writes_tarball_with_exactly_five_json_sections(tmp_path):
    call_command("support_bundle", "--output-dir", str(tmp_path), stdout=StringIO())

    bundles = list(tmp_path.glob("support-bundle-*.tar.gz"))
    assert len(bundles) == 1

    with tarfile.open(bundles[0]) as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        roots = {name.split("/", 1)[0] for name in names}
        assert len(roots) == 1
        assert roots.pop().startswith("support-bundle-")

        assert {name.split("/", 1)[1] for name in names} == EXPECTED_FILES
        for member in members:
            payload = archive.extractfile(member)
            assert payload is not None
            data = json.loads(payload.read())
            assert isinstance(data, dict)
            assert "meta" in data


@pytest.mark.django_db
def test_dry_run_writes_nothing_and_prints_manifest(tmp_path):
    out = StringIO()

    call_command("support_bundle", "--dry-run", "--output-dir", str(tmp_path), stdout=out)

    assert list(tmp_path.iterdir()) == []
    manifest = json.loads(out.getvalue())
    assert [entry["name"] for entry in manifest] == [
        "tasks.json",
        "ingestion.json",
        "queues.json",
        "schema.json",
        "settings.json",
    ]
    assert all(entry["bytes"] > 0 for entry in manifest)


@pytest.mark.django_db
def test_output_dir_that_does_not_exist_raises_command_error(tmp_path):
    missing = tmp_path / "does-not-exist"

    with pytest.raises(CommandError, match="does not exist"):
        call_command("support_bundle", "--output-dir", str(missing))

    assert not missing.exists()


@pytest.mark.django_db
def test_verbosity_zero_suppresses_success_line(tmp_path):
    out = StringIO()

    call_command("support_bundle", "--output-dir", str(tmp_path), verbosity=0, stdout=out)

    assert "Support bundle written to:" not in out.getvalue()
    assert len(list(tmp_path.glob("support-bundle-*.tar.gz"))) == 1


@pytest.mark.django_db
def test_command_does_not_modify_task_rows(tmp_path):
    pending = Task.objects.create(name="pending", function_name="hello_world", status="pending")
    running = Task.objects.create(
        name="running",
        function_name="collect_hourly_metrics",
        status="running",
        started_at=timezone.now() - timedelta(minutes=5),
    )
    before = {task.pk: (task.status, task.modified) for task in (pending, running)}

    call_command("support_bundle", "--output-dir", str(tmp_path), stdout=StringIO())

    for task in (pending, running):
        task.refresh_from_db()
        assert (task.status, task.modified) == before[task.pk]


def test_cli_maps_support_bundle_to_django_command():
    from metrics_service.cli import _DJANGO_COMMAND_MAP

    assert _DJANGO_COMMAND_MAP["support-bundle"] == "support_bundle"
