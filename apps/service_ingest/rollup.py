"""
Schema-driven rollup engine for per-event ExternalEvents.

The rollup config is inferred from the JSON Schema declared at registration
time, stored in ServiceDefinition.rollup_config, and applied by RollupEngine
during the daily rollup task.
"""

import logging
from typing import Any

from django.db.models import Avg, Count, Max, Min

logger = logging.getLogger(__name__)

# Integer suffixes that indicate categorical values → group_by
_CATEGORICAL_INT_SUFFIXES = ("_status", "_code", "_type", "_flag", "_mode", "_level")
# Suffixes that classify a field as an identifier → excluded from grouping/stats
_ID_SUFFIXES = ("_pseudo_id", "_uuid", "_id", "_hash", "_key")


def infer_rollup_config(schema: dict) -> dict:
    """
    Infer a rollup configuration from a JSON Schema object.

    Classification priority per property:
    1. Explicit ``x-analytics-role`` extension key (group_by / stats / identifier / ignore)
    2. Name ends in an ID suffix → identifier
    3. type=string with enum list → group_by
    4. type=boolean → group_by
    5. type=string (other) → group_by
    6. type=integer|number with stats suffix in name → stats
    7. type=integer|number (other) → stats

    Returns a rollup_config dict with:
        strategy, group_by, stats_fields, identifier_fields, count_alias, inferred=True
    """
    properties: dict = schema.get("properties", {})
    if not properties:
        return {
            "strategy": "raw_daily_summary",
            "group_by": [],
            "stats_fields": [],
            "identifier_fields": [],
            "count_alias": "event_count",
            "inferred": True,
        }

    group_by: list[str] = []
    stats_fields: list[str] = []
    identifier_fields: list[str] = []

    for name, prop in properties.items():
        role = prop.get("x-analytics-role")
        field_type = prop.get("type", "")
        # Normalise type to a string even if it's a list (e.g. ["string", "null"])
        if isinstance(field_type, list):
            field_type = next((t for t in field_type if t != "null"), "string")

        if role == "group_by":
            group_by.append(name)
        elif role == "stats":
            stats_fields.append(name)
        elif role == "identifier":
            identifier_fields.append(name)
        elif role == "ignore":
            continue
        elif name.endswith(_ID_SUFFIXES):
            identifier_fields.append(name)
        elif field_type == "string" and prop.get("enum"):
            group_by.append(name)
        elif field_type == "boolean":
            group_by.append(name)
        elif field_type == "string":
            group_by.append(name)
        elif field_type in ("integer", "number"):
            if name.endswith(_CATEGORICAL_INT_SUFFIXES):
                group_by.append(name)
            else:
                stats_fields.append(name)

    # Choose strategy
    if stats_fields:
        strategy = "stats_by_field"
    elif group_by:
        strategy = "count_by_field"
    else:
        strategy = "raw_daily_summary"

    config = {
        "strategy": strategy,
        "group_by": group_by,
        "stats_fields": stats_fields,
        "identifier_fields": identifier_fields,
        "count_alias": "event_count",
        "inferred": True,
    }
    logger.debug("Inferred rollup config: %s", config)
    return config


class RollupEngine:
    """
    Applies a ServiceDefinition's rollup_config to a queryset of ExternalEvents,
    producing a list of aggregated payload dicts ready for analytics.track().
    """

    def rollup(self, events_qs, definition) -> list[dict[str, Any]]:
        """
        Aggregate events according to definition.rollup_config.

        Args:
            events_qs: QuerySet of ExternalEvent (already filtered to the target date/status)
            definition: ServiceDefinition instance

        Returns:
            List of dicts, each representing one Segment track() call.
        """
        config = definition.rollup_config or {}
        strategy = config.get("strategy", "raw_daily_summary")

        if strategy == "count_by_field":
            return self._count_by_field(events_qs, config)
        elif strategy == "stats_by_field":
            return self._stats_by_field(events_qs, config)
        elif strategy == "raw_daily_summary":
            return self._raw_daily_summary(events_qs, config)
        elif strategy == "passthrough":
            return self._passthrough(events_qs)
        else:
            logger.warning("Unknown rollup strategy '%s' for %s; using raw_daily_summary", strategy, definition)
            return self._raw_daily_summary(events_qs, config)

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    def _extract_payload_field(self, events_qs, field: str):
        """Pull a top-level payload field value from each event (Python-side grouping)."""
        return [e.payload.get(field) for e in events_qs]

    def _count_by_field(self, events_qs, config: dict) -> list[dict]:
        group_by: list[str] = config.get("group_by", [])
        count_alias: str = config.get("count_alias", "event_count")

        if not group_by:
            count = events_qs.count()
            return [{"event_count": count}] if count > 0 else []

        # Group in Python (JSON fields can't be annotated directly in SQLite/PG without jsonb ops)
        groups: dict[tuple, int] = {}
        for event in events_qs:
            key = tuple(event.payload.get(f) for f in group_by)
            groups[key] = groups.get(key, 0) + 1

        results = []
        for key, count in groups.items():
            row = dict(zip(group_by, key))
            row[count_alias] = count
            results.append(row)
        return results

    def _stats_by_field(self, events_qs, config: dict) -> list[dict]:
        group_by: list[str] = config.get("group_by", [])
        stats_fields: list[str] = config.get("stats_fields", [])
        count_alias: str = config.get("count_alias", "event_count")

        # Group in Python so we work across any DB backend
        groups: dict[tuple, list[dict]] = {}
        for event in events_qs:
            key = tuple(event.payload.get(f) for f in group_by) if group_by else (None,)
            groups.setdefault(key, []).append(event.payload)

        results = []
        for key, payloads in groups.items():
            row: dict[str, Any] = {}
            if group_by:
                row.update(dict(zip(group_by, key)))
            row[count_alias] = len(payloads)

            for field in stats_fields:
                values = [p[field] for p in payloads if isinstance(p.get(field), (int, float))]
                if not values:
                    logger.warning("All values for stats field '%s' are non-numeric; skipping", field)
                if values:
                    row[f"{field}_min"] = min(values)
                    row[f"{field}_max"] = max(values)
                    row[f"{field}_mean"] = round(sum(values) / len(values), 3)
                    sorted_vals = sorted(values)
                    p95_idx = int(len(sorted_vals) * 0.95)
                    row[f"{field}_p95"] = sorted_vals[min(p95_idx, len(sorted_vals) - 1)]

            results.append(row)
        return results

    def _raw_daily_summary(self, events_qs, config: dict) -> list[dict]:
        """Merge all payload dicts for the period into one summary."""
        merged: dict[str, Any] = {}
        count = 0
        for event in events_qs:
            count += 1
            for k, v in event.payload.items():
                if isinstance(v, (int, float)) and k in merged:
                    merged[k] = merged[k] + v
                else:
                    merged[k] = v
        if count == 0:
            return []
        merged["event_count"] = count
        return [merged]

    def _passthrough(self, events_qs) -> list[dict]:
        """Return each event payload individually (for batch-type events only)."""
        return [event.payload for event in events_qs]
