"""Build the existing renewal report from one exported analytics envelope, without a DB."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from metrics_utility.automation_controller_billing.dataframe_engine.db_dataframe_host_metric import (
    DBDataframeHostMetric,
)
from metrics_utility.automation_controller_billing.dedup.factory import Factory as DedupFactory
from metrics_utility.automation_controller_billing.report.report_renewal_guidance import ReportRenewalGuidance
from openpyxl import Workbook


class EnvelopeExtractor:
    """Supply the same raw dataframe that the CLI's Controller DB extractor supplies."""

    def __init__(self, payload: list[dict[str, Any]], extra_params: dict[str, Any]) -> None:
        self.payload = payload
        self.extra_params = extra_params

    def iter_batches(self) -> Iterator[dict[str, pd.DataFrame]]:
        """Yield one complete lifecycle dataset, including legitimate inventory-host matches."""
        yield {"host_metric": pd.DataFrame(self.payload)}


def build_report(
    envelope: dict[str, Any], since: datetime, until: datetime, ephemeral_days: int | None = None
) -> Workbook:
    """Adapt an API envelope to the unchanged default renewal dataframe/dedup/report pipeline."""
    if since.tzinfo is None or until.tzinfo is None or until < since:
        raise ValueError("Use timezone-aware bounds with until >= since")
    if ephemeral_days is not None and ephemeral_days < 1:
        raise ValueError("ephemeral_days must be positive")
    if envelope.get("collector") != "controller.main_hostmetric":
        raise ValueError("Expected controller.main_hostmetric")
    if envelope.get("source") != "local" or not envelope.get("cluster_id"):
        raise ValueError("Select a local envelope with a known Controller cluster_id")
    collected_since = envelope.get("since")
    if (
        not collected_since
        or datetime.fromisoformat(collected_since.replace("Z", "+00:00")) != since
        or envelope.get("until") is not None
    ):
        raise ValueError("Select a complete collection with the report since and an open until")
    payload = envelope.get("payload")
    if not isinstance(payload, list) or not payload:
        raise ValueError("Select a populated array payload")

    params = {
        "opt_since": since,
        "since_date": since.date(),
        "until_date": until.date(),
        "report_period": f"{since.date()}, {until.date()}",
        "report_type": "RENEWAL_GUIDANCE",
        "deduplicator": "renewal",
        "report_renewal_guidance_dedup_iterations": "3",
        "ephemeral_days": ephemeral_days,
        "optional_sheets": ["managed_nodes"],
    }
    extractor = EnvelopeExtractor(payload, params)
    engine = DBDataframeHostMetric(extractor=extractor, month=None, extra_params=params)
    dataframes = DedupFactory({"host_metric": engine}, params).create().run()
    if dataframes["host_metric"].empty:
        raise ValueError("No hosts have last_automation >= since")
    return ReportRenewalGuidance(dataframes, params).build_spreadsheet()


def main() -> None:
    """Read an exported envelope and write a reference workbook."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("envelope", type=Path)
    parser.add_argument("--since", required=True, help="Inclusive date, YYYY-MM-DD")
    parser.add_argument("--until", required=True, help="Report end date, YYYY-MM-DD (not a collection upper bound)")
    parser.add_argument("--ephemeral", type=int, default=None, help="Optional ephemeral threshold in days")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=UTC)
    until = datetime.strptime(args.until, "%Y-%m-%d").replace(tzinfo=UTC)
    envelope = json.loads(args.envelope.read_text())
    build_report(envelope, since, until, args.ephemeral).save(args.output)


if __name__ == "__main__":
    main()
