"""
Schema-driven rollup engine for per-event ExternalEvents.

The rollup config is inferred from the JSON Schema declared at registration
time, stored in ServiceDefinition.rollup_config, and applied by RollupEngine
during the daily rollup task.
"""

import logging
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)

# Integer suffixes that indicate categorical values → group_by
_CATEGORICAL_INT_SUFFIXES = ("_status", "_code", "_type", "_flag", "_mode", "_level")
# Suffixes that classify a field as an identifier → excluded from grouping/stats
_ID_SUFFIXES = ("_pseudo_id", "_uuid", "_id", "_hash", "_key")
# Suffixes that classify a field as a timestamp → excluded from rollup
_TIMESTAMP_SUFFIXES = ("_at", "_time", "_timestamp", "_date")

KNOWN_STRATEGIES = ("count_by_field", "stats_by_field", "raw_daily_summary", "passthrough")
KNOWN_ROLES = ("group_by", "stats", "identifier", "ignore", "timestamp")


def _normalise_type(field_type) -> str:
    """Normalise a JSON Schema type to a single string (handles nullable arrays)."""
    if isinstance(field_type, list):
        return next((t for t in field_type if t != "null"), "string")
    return field_type or ""


def _walk_properties(properties: dict, prefix: str = "") -> Iterator[tuple[str, dict]]:
    """Yield (dotted_name, property_schema) for all leaf properties, flattening nested objects."""
    for name, prop in properties.items():
        full_name = f"{prefix}.{name}" if prefix else name
        field_type = _normalise_type(prop.get("type", ""))
        if field_type == "object" and prop.get("properties"):
            yield from _walk_properties(prop["properties"], full_name)
        else:
            yield full_name, prop


def _get_nested(payload: dict, dotted_key: str):
    """Resolve 'a.b.c' into payload['a']['b']['c']. Returns None on any miss."""
    parts = dotted_key.split(".")
    val = payload
    for part in parts:
        if not isinstance(val, dict):
            return None
        val = val.get(part)
    return val


def _classify_field(name: str, prop: dict) -> str | None:
    """
    Classify a single schema property into a role.

    Returns one of: "group_by", "stats", "identifier", "timestamp", "ignore", or None (unclassifiable).
    """
    role = prop.get("x-analytics-role")
    if role in KNOWN_ROLES:
        return role if role != "ignore" else None

    # If x-analytics-role is present but unrecognized, fall through to heuristics
    field_type = _normalise_type(prop.get("type", ""))

    # Leaf name (last segment after dots) drives suffix matching
    leaf_name = name.rsplit(".", 1)[-1] if "." in name else name

    if leaf_name.endswith(_ID_SUFFIXES):
        return "identifier"

    if leaf_name.endswith(_TIMESTAMP_SUFFIXES) or prop.get("format") == "date-time":
        return "timestamp"

    if field_type == "string" and prop.get("enum"):
        return "group_by"
    if field_type == "boolean":
        return "group_by"
    if field_type == "string":
        return "group_by"
    if field_type in ("integer", "number"):
        if leaf_name.endswith(_CATEGORICAL_INT_SUFFIXES):
            return "group_by"
        return "stats"

    return None


def infer_rollup_config(schema: dict) -> dict:
    """
    Infer a rollup configuration from a JSON Schema object.

    Classification priority per property:
    1. Explicit ``x-analytics-role`` extension key
    2. Name ends in an ID suffix → identifier
    3. Name ends in a timestamp suffix or format=date-time → excluded
    4. type=string with enum → group_by
    5. type=boolean → group_by
    6. type=string → group_by
    7. type=integer|number with categorical suffix → group_by
    8. type=integer|number → stats
    9. type=object with properties → recursively flatten children
    10. Anything else → silently dropped
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

    for name, prop in _walk_properties(properties):
        role = _classify_field(name, prop)
        if role == "group_by":
            group_by.append(name)
        elif role == "stats":
            stats_fields.append(name)
        elif role == "identifier":
            identifier_fields.append(name)
        # "timestamp" and None are intentionally dropped

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

    def _count_by_field(self, events_qs, config: dict) -> list[dict]:
        group_by: list[str] = config.get("group_by", [])
        count_alias: str = config.get("count_alias", "event_count")

        if not group_by:
            count = events_qs.count()
            return [{"event_count": count}] if count > 0 else []

        groups: dict[tuple, int] = {}
        for event in events_qs:
            key = tuple(_get_nested(event.payload, f) for f in group_by)
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

        groups: dict[tuple, list[dict]] = {}
        for event in events_qs:
            key = tuple(_get_nested(event.payload, f) for f in group_by) if group_by else (None,)
            groups.setdefault(key, []).append(event.payload)

        results = []
        for key, payloads in groups.items():
            row: dict[str, Any] = {}
            if group_by:
                row.update(dict(zip(group_by, key)))
            row[count_alias] = len(payloads)

            for field in stats_fields:
                values = [_get_nested(p, field) for p in payloads if isinstance(_get_nested(p, field), (int, float))]
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
        return [event.payload for event in events_qs]
