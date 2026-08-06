"""
Tests for the service_ingest rollup engine.

Covers infer_rollup_config() (pure-function, no DB) and RollupEngine
(requires ExternalEvent model instances via django_db).
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.service_ingest.models import ExternalEvent, ServiceDefinition
from apps.service_ingest.rollup import RollupEngine, infer_rollup_config


# ======================================================================
# infer_rollup_config — no DB required
# ======================================================================


@pytest.mark.unit
class TestInferRollupConfig:
    """Pure-function tests for infer_rollup_config()."""

    def test_mcp_schema_classification(self):
        """MCP-style schema classifies fields correctly by suffix and type."""
        schema = {
            "properties": {
                "tool_name": {"type": "string"},
                "mcp_tool_set": {"type": "string"},
                "http_status": {"type": "integer"},
                "execution_time_ms": {"type": "integer"},
                "user_pseudo_id": {"type": "string"},
                "installer_pseudo_id": {"type": "string"},
            }
        }
        config = infer_rollup_config(schema)

        assert config["strategy"] == "stats_by_field"
        assert "tool_name" in config["group_by"]
        assert "mcp_tool_set" in config["group_by"]
        # http_status ends in _status → categorical int → group_by
        assert "http_status" in config["group_by"]
        assert "execution_time_ms" in config["stats_fields"]
        assert "user_pseudo_id" in config["identifier_fields"]
        assert "installer_pseudo_id" in config["identifier_fields"]

    def test_x_analytics_role_overrides_suffix_heuristics(self):
        """Explicit x-analytics-role takes precedence over suffix-based rules."""
        schema = {
            "properties": {
                "event_id": {"type": "string", "x-analytics-role": "group_by"},
            }
        }
        config = infer_rollup_config(schema)

        # event_id would normally go to identifier_fields (ends in _id),
        # but x-analytics-role: group_by wins.
        assert "event_id" in config["group_by"]
        assert "event_id" not in config["identifier_fields"]

    def test_empty_schema_returns_raw_daily_summary(self):
        """Empty schema produces a raw_daily_summary fallback config."""
        config = infer_rollup_config({})

        assert config["strategy"] == "raw_daily_summary"
        assert config["group_by"] == []
        assert config["stats_fields"] == []
        assert config["identifier_fields"] == []

    def test_boolean_fields_go_to_group_by(self):
        """Boolean-typed fields are classified as group_by."""
        schema = {
            "properties": {
                "enabled": {"type": "boolean"},
            }
        }
        config = infer_rollup_config(schema)

        assert "enabled" in config["group_by"]

    def test_nullable_type_arrays_normalized(self):
        """Type arrays like ["string", "null"] are normalized to the non-null type."""
        schema = {
            "properties": {
                "name": {"type": ["string", "null"]},
            }
        }
        config = infer_rollup_config(schema)

        # Normalised to string → group_by
        assert "name" in config["group_by"]

    def test_categorical_int_suffixes_go_to_group_by(self):
        """Integer fields with categorical suffixes go to group_by, others to stats."""
        schema = {
            "properties": {
                "error_code": {"type": "integer"},
                "retry_count": {"type": "integer"},
            }
        }
        config = infer_rollup_config(schema)

        # _code is a categorical suffix → group_by
        assert "error_code" in config["group_by"]
        # _count has no categorical suffix → stats_fields
        assert "retry_count" in config["stats_fields"]


# ======================================================================
# RollupEngine — requires DB for ExternalEvent fixtures
# ======================================================================


@pytest.fixture
def service_definition(db):
    """Create a minimal ServiceDefinition for test events."""
    return ServiceDefinition.objects.create(
        service_name="test-service",
        event_name="test_event",
        display_name="Test Event",
        version="1.0.0",
        segment_event_name="Test Event Fired",
        payload_schema={},
        rollup_config={},
    )


def _create_events(service_definition, payloads):
    """Helper to create ExternalEvent instances from a list of payload dicts."""
    events = []
    for payload in payloads:
        events.append(
            ExternalEvent.objects.create(
                service=service_definition,
                payload_type="event",
                payload=payload,
                status="pending",
            )
        )
    return events


@pytest.mark.django_db
class TestRollupEngineStatsByField:
    """Tests for the stats_by_field rollup strategy."""

    def test_stats_by_field_produces_correct_aggregates(self, service_definition):
        """stats_by_field groups by specified fields and computes min/max/mean/p95."""
        _create_events(
            service_definition,
            [
                {"tool_name": "create_inventory", "execution_time_ms": 100},
                {"tool_name": "create_inventory", "execution_time_ms": 200},
                {"tool_name": "run_playbook", "execution_time_ms": 500},
            ],
        )

        service_definition.rollup_config = {
            "strategy": "stats_by_field",
            "group_by": ["tool_name"],
            "stats_fields": ["execution_time_ms"],
            "count_alias": "event_count",
        }
        service_definition.save()

        engine = RollupEngine()
        qs = ExternalEvent.objects.filter(service=service_definition)
        results = engine.rollup(qs, service_definition)

        # Should produce two groups
        assert len(results) == 2
        by_tool = {r["tool_name"]: r for r in results}

        inv = by_tool["create_inventory"]
        assert inv["event_count"] == 2
        assert inv["execution_time_ms_min"] == 100
        assert inv["execution_time_ms_max"] == 200
        assert inv["execution_time_ms_mean"] == 150.0
        assert inv["execution_time_ms_p95"] in (100, 200)  # with 2 values, p95 index rounds

        pb = by_tool["run_playbook"]
        assert pb["event_count"] == 1
        assert pb["execution_time_ms_min"] == 500
        assert pb["execution_time_ms_max"] == 500


@pytest.mark.django_db
class TestRollupEngineCountByField:
    """Tests for the count_by_field rollup strategy."""

    def test_count_by_field_produces_correct_counts(self, service_definition):
        """count_by_field groups and counts events per group_by value."""
        _create_events(
            service_definition,
            [
                {"region": "us-east-1"},
                {"region": "us-east-1"},
                {"region": "eu-west-1"},
            ],
        )

        service_definition.rollup_config = {
            "strategy": "count_by_field",
            "group_by": ["region"],
            "count_alias": "event_count",
        }
        service_definition.save()

        engine = RollupEngine()
        qs = ExternalEvent.objects.filter(service=service_definition)
        results = engine.rollup(qs, service_definition)

        assert len(results) == 2
        by_region = {r["region"]: r for r in results}
        assert by_region["us-east-1"]["event_count"] == 2
        assert by_region["eu-west-1"]["event_count"] == 1


@pytest.mark.django_db
class TestRollupEngineRawDailySummary:
    """Tests for the raw_daily_summary rollup strategy."""

    def test_raw_daily_summary_sums_numeric_last_write_wins_others(self, service_definition):
        """raw_daily_summary sums numeric fields and uses last-write-wins for non-numeric."""
        _create_events(
            service_definition,
            [
                {"total_hosts": 10, "region": "us-east-1"},
                {"total_hosts": 20, "region": "eu-west-1"},
                {"total_hosts": 5, "region": "ap-south-1"},
            ],
        )

        service_definition.rollup_config = {
            "strategy": "raw_daily_summary",
        }
        service_definition.save()

        engine = RollupEngine()
        qs = ExternalEvent.objects.filter(service=service_definition)
        results = engine.rollup(qs, service_definition)

        assert len(results) == 1
        summary = results[0]
        # Numeric fields are summed
        assert summary["total_hosts"] == 35
        # Non-numeric: last-write-wins (the last event's value)
        assert summary["region"] == "us-east-1"
        assert summary["event_count"] == 3


@pytest.mark.django_db
class TestRollupEnginePassthrough:
    """Tests for the passthrough rollup strategy."""

    def test_passthrough_returns_each_payload_individually(self, service_definition):
        """passthrough returns every event's payload as-is."""
        payloads = [
            {"action": "install", "version": "2.5"},
            {"action": "upgrade", "version": "2.6"},
        ]
        _create_events(service_definition, payloads)

        service_definition.rollup_config = {
            "strategy": "passthrough",
        }
        service_definition.save()

        engine = RollupEngine()
        qs = ExternalEvent.objects.filter(service=service_definition)
        results = engine.rollup(qs, service_definition)

        assert len(results) == 2
        # Each payload should appear individually
        actions = {r["action"] for r in results}
        assert actions == {"install", "upgrade"}


@pytest.mark.django_db
class TestRollupEngineEmptyQueryset:
    """Tests for empty queryset handling across all strategies."""

    @pytest.mark.parametrize(
        "strategy",
        ["stats_by_field", "count_by_field", "raw_daily_summary", "passthrough"],
    )
    def test_empty_queryset_returns_empty_list(self, service_definition, strategy):
        """All strategies return an empty list for an empty queryset."""
        service_definition.rollup_config = {
            "strategy": strategy,
            "group_by": ["tool_name"],
            "stats_fields": ["execution_time_ms"],
            "count_alias": "event_count",
        }
        service_definition.save()

        engine = RollupEngine()
        qs = ExternalEvent.objects.filter(service=service_definition)
        results = engine.rollup(qs, service_definition)

        assert results == []


@pytest.mark.django_db
class TestRollupEngineNonNumericStatsField:
    """Tests for stats fields with non-numeric values."""

    def test_non_numeric_stats_field_skipped(self, service_definition):
        """Stats field with all string values produces no min/max/mean keys."""
        _create_events(
            service_definition,
            [
                {"category": "alpha", "label": "foo"},
                {"category": "beta", "label": "bar"},
            ],
        )

        service_definition.rollup_config = {
            "strategy": "stats_by_field",
            "group_by": ["category"],
            "stats_fields": ["label"],
            "count_alias": "event_count",
        }
        service_definition.save()

        engine = RollupEngine()
        qs = ExternalEvent.objects.filter(service=service_definition)
        results = engine.rollup(qs, service_definition)

        for row in results:
            assert "label_min" not in row
            assert "label_max" not in row
            assert "label_mean" not in row
            assert "label_p95" not in row
            # Count should still be present
            assert "event_count" in row


@pytest.mark.unit
class TestInferRollupConfigExtended:
    """Extended classification and nested schema tests."""

    def test_x_analytics_role_ignore(self):
        schema = {"type": "object", "properties": {"internal_debug": {"type": "string", "x-analytics-role": "ignore"}, "tool_name": {"type": "string"}}}
        config = infer_rollup_config(schema)
        assert "internal_debug" not in config["group_by"]
        assert "tool_name" in config["group_by"]

    def test_x_analytics_role_stats(self):
        schema = {"type": "object", "properties": {"custom_metric": {"type": "string", "x-analytics-role": "stats"}}}
        config = infer_rollup_config(schema)
        assert "custom_metric" in config["stats_fields"]

    def test_x_analytics_role_identifier(self):
        schema = {"type": "object", "properties": {"session_token": {"type": "string", "x-analytics-role": "identifier"}}}
        config = infer_rollup_config(schema)
        assert "session_token" in config["identifier_fields"]

    def test_unknown_x_analytics_role_falls_through(self):
        schema = {"type": "object", "properties": {"name": {"type": "string", "x-analytics-role": "foobar"}}}
        config = infer_rollup_config(schema)
        assert "name" in config["group_by"]  # falls through to string -> group_by

    def test_string_with_enum_goes_to_group_by(self):
        schema = {"type": "object", "properties": {"status": {"type": "string", "enum": ["active", "inactive"]}}}
        config = infer_rollup_config(schema)
        assert "status" in config["group_by"]

    def test_nested_object_properties_flattened(self):
        schema = {"type": "object", "properties": {
            "resource": {"type": "object", "properties": {
                "service_name": {"type": "string"},
                "version": {"type": "string"},
            }},
            "execution_time_ms": {"type": "integer"},
        }}
        config = infer_rollup_config(schema)
        assert "resource.service_name" in config["group_by"]
        assert "resource.version" in config["group_by"]
        assert "execution_time_ms" in config["stats_fields"]

    def test_number_type_classified_as_stats(self):
        schema = {"type": "object", "properties": {"latency": {"type": "number"}}}
        config = infer_rollup_config(schema)
        assert "latency" in config["stats_fields"]

    def test_field_with_no_type_dropped(self):
        schema = {"type": "object", "properties": {"mystery": {"description": "no type"}}}
        config = infer_rollup_config(schema)
        assert "mystery" not in config["group_by"]
        assert "mystery" not in config["stats_fields"]
        assert "mystery" not in config["identifier_fields"]

    def test_array_type_ignored_without_role(self):
        schema = {"type": "object", "properties": {"tags": {"type": "array", "items": {"type": "string"}}}}
        config = infer_rollup_config(schema)
        assert "tags" not in config["group_by"]
        assert "tags" not in config["stats_fields"]

    def test_timestamp_suffix_excluded(self):
        schema = {"type": "object", "properties": {
            "created_at": {"type": "string"},
            "tool_name": {"type": "string"},
        }}
        config = infer_rollup_config(schema)
        assert "created_at" not in config["group_by"]
        assert "tool_name" in config["group_by"]

    def test_format_datetime_excluded(self):
        schema = {"type": "object", "properties": {
            "event_ts": {"type": "string", "format": "date-time"},
            "name": {"type": "string"},
        }}
        config = infer_rollup_config(schema)
        assert "event_ts" not in config["group_by"]
        assert "name" in config["group_by"]

    def test_x_analytics_role_timestamp(self):
        schema = {"type": "object", "properties": {"custom_ts": {"type": "string", "x-analytics-role": "timestamp"}}}
        config = infer_rollup_config(schema)
        assert "custom_ts" not in config["group_by"]
        assert "custom_ts" not in config["stats_fields"]
        assert "custom_ts" not in config["identifier_fields"]

    def test_strategy_selection_stats(self):
        schema = {"type": "object", "properties": {"latency": {"type": "number"}}}
        config = infer_rollup_config(schema)
        assert config["strategy"] == "stats_by_field"

    def test_strategy_selection_count_only(self):
        schema = {"type": "object", "properties": {"region": {"type": "string"}}}
        config = infer_rollup_config(schema)
        assert config["strategy"] == "count_by_field"

    def test_strategy_selection_raw(self):
        config = infer_rollup_config({"type": "object", "properties": {}})
        assert config["strategy"] == "raw_daily_summary"


@pytest.mark.django_db
class TestRollupEngineNestedFields:
    """Tests for dot-path field access in rollup strategies."""

    def test_stats_by_field_with_nested_stats(self, service_definition):
        # Create events with nested payloads
        service_definition.rollup_config = {
            "strategy": "stats_by_field",
            "group_by": ["tool_name"],
            "stats_fields": ["resource.latency_ms"],
            "count_alias": "event_count",
        }
        service_definition.save()
        _create_events(service_definition, [
            {"tool_name": "a", "resource": {"latency_ms": 100}},
            {"tool_name": "a", "resource": {"latency_ms": 200}},
        ])
        engine = RollupEngine()
        qs = ExternalEvent.objects.filter(service=service_definition)
        results = engine.rollup(qs, service_definition)
        row = [r for r in results if r["tool_name"] == "a"][0]
        assert row["resource.latency_ms_min"] == 100
        assert row["resource.latency_ms_max"] == 200

    def test_count_by_field_with_nested_group_by(self, service_definition):
        service_definition.rollup_config = {
            "strategy": "count_by_field",
            "group_by": ["resource.service_name"],
            "count_alias": "event_count",
        }
        service_definition.save()
        _create_events(service_definition, [
            {"resource": {"service_name": "controller"}},
            {"resource": {"service_name": "controller"}},
            {"resource": {"service_name": "eda"}},
        ])
        engine = RollupEngine()
        qs = ExternalEvent.objects.filter(service=service_definition)
        results = engine.rollup(qs, service_definition)
        by_svc = {r["resource.service_name"]: r for r in results}
        assert by_svc["controller"]["event_count"] == 2
        assert by_svc["eda"]["event_count"] == 1
