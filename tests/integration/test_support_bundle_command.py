"""Integration tests for the ``support_bundle`` management command."""

import json
import stat
import sys
import tarfile
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.core.support_bundle import SupportBundleError, bundle
from apps.tasks.models import DailyMetricsSummary, HourlyMetricsCollection, Task

pytestmark = pytest.mark.integration

EXPECTED_FILES = {"tasks.json", "ingestion.json", "queues.json", "schema.json", "settings.json"}


class FixedDatetime(datetime):
    """Pin the bundle timestamp so symlink/collision tests are deterministic."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 2, 3, 4, 5, tzinfo=tz or UTC)


def _read_section(bundle_path, section):
    with tarfile.open(bundle_path) as archive:
        member = next(name for name in archive.getnames() if name.endswith(f"/{section}"))
        return json.loads(archive.extractfile(member).read())


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


@pytest.mark.django_db
def test_cli_resolves_support_bundle_through_the_metrics_service_command(monkeypatch, capsys):
    """``metrics-service support-bundle`` must work via the unified command.

    ``metrics_service/cli.py`` is a framework-protected file, so the subcommand
    is registered on ``apps.tasks.management.commands.metrics_service`` and
    reached through the CLI's unknown-subcommand fallback.
    """
    from metrics_service import cli

    monkeypatch.setattr(sys, "argv", ["metrics-service", "support-bundle", "--dry-run"])

    assert cli.main() == 0

    manifest = json.loads(capsys.readouterr().out)
    assert [entry["name"] for entry in manifest] == [
        "tasks.json",
        "ingestion.json",
        "queues.json",
        "schema.json",
        "settings.json",
    ]


@pytest.mark.django_db
def test_metrics_service_command_writes_a_bundle(tmp_path):
    out = StringIO()

    call_command("metrics_service", "support-bundle", "--output-dir", str(tmp_path), stdout=out)

    assert "Support bundle written to:" in out.getvalue()
    assert len(list(tmp_path.glob("support-bundle-*.tar.gz"))) == 1


@pytest.mark.django_db
def test_tarball_is_created_with_mode_0600(tmp_path):
    result = bundle.write_tarball(tmp_path, {"tasks.json": {"ok": True}})

    assert stat.S_IMODE(result.path.stat().st_mode) == 0o600
    assert result.path.exists()


@pytest.mark.django_db
def test_write_tarball_refuses_a_pre_planted_symlink(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, "datetime", FixedDatetime)
    victim = tmp_path / "victim.txt"
    victim.write_text("original")
    (tmp_path / "support-bundle-20260102-030405.tar.gz").symlink_to(victim)

    with pytest.raises(SupportBundleError, match="symlink"):
        bundle.write_tarball(tmp_path, {"tasks.json": {"ok": True}})

    assert victim.read_text() == "original"


@pytest.mark.django_db
def test_second_bundle_in_the_same_second_gets_a_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle, "datetime", FixedDatetime)

    first = bundle.write_tarball(tmp_path, {"tasks.json": {"ok": 1}})
    second = bundle.write_tarball(tmp_path, {"tasks.json": {"ok": 2}})

    assert first.path.name == "support-bundle-20260102-030405.tar.gz"
    assert second.path.name == "support-bundle-20260102-030405-2.tar.gz"
    assert first.path.read_bytes() != second.path.read_bytes()


@pytest.mark.django_db
def test_tarball_redacts_secrets_from_error_messages(tmp_path):
    """End-to-end: DB error text with a token/DSN must not reach the tarball."""
    HourlyMetricsCollection.objects.create(
        collector_type="unified_jobs",
        collection_timestamp=timezone.now(),
        status="failed",
        error_message="failed to POST https://segment/api?token=abc123 (401)",
    )
    DailyMetricsSummary.objects.create(
        summary_date=timezone.now().date(),
        status="failed",
        hourly_collections_count=0,
        error_message="curl --password=hunter2 --user=admin",
    )

    result = bundle.write_tarball(tmp_path)

    payload = json.dumps(_read_section(result.path, "ingestion.json"))
    assert "abc123" not in payload
    assert "hunter2" not in payload
    assert "failed to POST" in payload
