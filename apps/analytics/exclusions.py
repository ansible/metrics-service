"""Column exclusions applied to collector output on its way out of the service.

ANSTRAT-1587 requirement #8 bars usernames, email addresses and individual user login
timestamps from the data this service exposes. Some collectors return such a column
anyway because an *in-service* consumer needs it: ``controller.unified_jobs_dashboard``
carries ``launched_by_username`` so the automation-reports dashboard can map an
authenticated user back to their AWX ``launched_by_id`` (the local ``User`` pk is not
the AWX id, so there is no other link).

Dropping the column in the metrics-utility SQL would serve the API at the cost of the
dashboard, because a single ``gather()`` feeds both. Instead each
:class:`~apps.analytics.registry.CollectorEntry` declares ``exclude_columns`` and the
data is filtered at the boundaries where it leaves the service:

* :func:`~apps.analytics.persist.persist_analytics_payload` — everything written to
  ``AnalyticsPayload`` and served by the analytics read API;
* :func:`~apps.tasks.utils.generic_collect_metrics` — the data handed to the anonymized
  rollup processors. No entry needs an exclusion there today, but it is the same
  leaves-the-service boundary, so the field applies uniformly.

Deliberately **not** applied to ``post_collect_hook``: the dashboard ``JobData`` sync is
internal and is the reason the column is collected in the first place.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def apply_exclusions(raw_data: Any, exclude_columns: tuple[str, ...]) -> Any:
    """Return ``raw_data`` without ``exclude_columns``.

    Never mutates ``raw_data``: the same object is handed to in-service consumers that
    still need the excluded columns. Shapes other than a DataFrame, a dict or a list of
    dicts are returned unchanged — collectors only produce those three.

    Args:
        raw_data: a collector's ``gather()`` output.
        exclude_columns: column/key names to withhold; empty means no filtering.

    Returns:
        A filtered copy, or ``raw_data`` itself when there is nothing to remove.
    """
    if not exclude_columns or raw_data is None:
        return raw_data

    excluded = set(exclude_columns)

    if isinstance(raw_data, pd.DataFrame):
        present = [column for column in raw_data.columns if column in excluded]
        # .drop() copies, leaving the caller's frame intact for the dashboard sync.
        return raw_data.drop(columns=present) if present else raw_data

    if isinstance(raw_data, dict):
        return {key: value for key, value in raw_data.items() if key not in excluded}

    if isinstance(raw_data, list):
        return [
            {key: value for key, value in row.items() if key not in excluded} if isinstance(row, dict) else row
            for row in raw_data
        ]

    return raw_data
