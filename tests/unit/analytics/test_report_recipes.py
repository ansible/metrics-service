"""Exercise the documented raw-envelope adapter against real metrics-utility report code."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from openpyxl import load_workbook

from docs.examples.renewal_guidance import build_report

SINCE = datetime(2026, 9, 1, tzinfo=UTC)
UNTIL = datetime(2026, 9, 30, tzinfo=UTC)


@pytest.fixture
def envelope():
    """Include alias dedup, a deleted host, and a deletion-only change outside usage scope."""
    base = {
        "id": 1,
        "hostname": "node-a",
        "host_id": 10,
        "first_automation": "2026-01-01T00:00:00Z",
        "last_automation": "2026-09-20T00:00:00Z",
        "automated_counter": 5,
        "deleted_counter": 0,
        "last_deleted": None,
        "deleted": False,
        "used_in_inventories": 1,
        "ansible_product_serial": "serial-a",
        "ansible_machine_id": "machine-a",
        "ansible_host_variable": None,
        "ansible_connection_variable": "local",
    }
    return {
        "id": 100,
        "collector": "controller.main_hostmetric",
        "source": "local",
        "cluster_id": "11111111-1111-1111-1111-111111111111",
        "since": "2026-09-01T00:00:00Z",
        "until": None,
        "payload": [
            base,
            {**base, "hostname": "alias-a", "id": 2, "host_id": 11, "automated_counter": 7},
            {
                **base,
                "hostname": "deleted-b",
                "id": 3,
                "host_id": 0,
                "deleted": True,
                "ansible_product_serial": None,
                "ansible_machine_id": None,
                "last_deleted": "2026-09-21T00:00:00Z",
            },
            {**base, "hostname": "old-c", "id": 4, "last_automation": "2026-08-01T00:00:00Z"},
        ],
    }


def test_renewal_workbook_from_raw_envelope(envelope, tmp_path):
    """Default dedup merges aliases, keeps local connections, and drops deletion-only old usage."""
    workbook = build_report(envelope, SINCE, UNTIL)
    path = tmp_path / "renewal.xlsx"
    workbook.save(path)
    saved = load_workbook(path, data_only=True)
    assert saved.sheetnames == ["Usage Reporting", "Managed nodes", "Deleted Managed nodes"]
    quantities = {row[0]: row[1] for row in saved["Usage Reporting"].values}
    assert quantities["Automated hosts"] == 1
    assert quantities["Deleted Automated hosts"] == 1
    active = list(saved["Managed nodes"].values)
    assert len(active) == 2
    assert active[1][3] == 12  # Sum counters from the two alias records.


def test_inventory_host_matches_are_not_collapsed_by_metric_id(envelope):
    """Two inventory-host matches for one metric ID are legitimate input rows, not API retries."""
    envelope["payload"] = [envelope["payload"][0], {**envelope["payload"][0], "host_id": 99}]
    workbook = build_report(envelope, SINCE, UNTIL)
    active = list(workbook["Managed nodes"].values)
    assert active[1][3] == 10
    assert active[1][7] == 1  # Record counts use distinct hostnames, not SQL row count.


def test_report_until_does_not_filter_lifecycle_input(envelope):
    """The adapter preserves the CLI's open upper bound rather than silently fixing the report."""
    envelope["payload"] = [{**envelope["payload"][0], "last_automation": "2026-10-01T00:00:00Z"}]
    workbook = build_report(envelope, SINCE, UNTIL)
    quantities = {row[0]: row[1] for row in workbook["Usage Reporting"].values}
    assert quantities["Automated hosts"] == 1


def test_ephemeral_views_use_existing_report_calculation(envelope, monkeypatch):
    """Freeze execution date because the existing classifier uses now, not report until."""
    from metrics_utility.automation_controller_billing.report import report_renewal_guidance

    class ReportDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 23, tzinfo=tz)

    monkeypatch.setattr(report_renewal_guidance.datetime, "datetime", ReportDateTime)
    envelope["payload"] = [
        {
            **envelope["payload"][0],
            "first_automation": "2026-09-05T00:00:00Z",
            "last_automation": "2026-09-06T00:00:00Z",
        }
    ]
    workbook = build_report(envelope, SINCE, UNTIL, ephemeral_days=7)
    quantities = {row[0]: row[1] for row in workbook["Usage Reporting"].values}
    assert quantities["Automated hosts"] == 0
    assert quantities["Ephemeral automated hosts total"] == 1
    assert quantities["Ephemeral automated hosts maximum\nconcurrent usage in defined interval"] == 1
    assert "Managed nodes ephemeral usage" in workbook.sheetnames


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("collector", "controller.main_host"),
        ("cluster_id", None),
        ("source", "other"),
        ("since", "2026-08-01T00:00:00Z"),
        ("until", "2026-10-01T00:00:00Z"),
        ("payload", []),
        ("payload", {}),
    ],
)
def test_reject_wrong_or_incomplete_input(envelope, field, value):
    """Do not quietly combine installations, daily windows, or incompatible payload shapes."""
    invalid = deepcopy(envelope)
    invalid[field] = value
    with pytest.raises(ValueError):
        build_report(invalid, SINCE, UNTIL)
