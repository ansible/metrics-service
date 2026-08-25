# Service Ingest Schema Registry

This directory contains JSON Schema definitions and rollup configurations for AAP services that send telemetry to metrics-service via the service ingest API.

## Directory Structure

Each service has a subdirectory containing one YAML file per event type:

```
schemas/service_ingest/
├── aap-mcp-server/
│   ├── mcp_tool_called.yaml
│   └── mcp_server_status.yaml
├── aap-eda-server/
│   ├── eda_activation_daily_summary.yaml
│   └── eda_rule_firing_hourly.yaml
├── aap-gateway/
│   └── gateway_request_stats.yaml
└── aap-hub/
    └── hub_collection_stats.yaml
```

## YAML Schema Format

Each schema file defines a single event type and contains:

### Required Fields

- **`service_name`** (string): Machine identifier for the service (e.g., `aap-mcp-server`). Must match across all files for the same service.
- **`event_name`** (string): Logical event type within the service (e.g., `mcp_tool_called`). Unique per service.
- **`display_name`** (string): Human-readable name for UI/reporting
- **`version`** (string): Schema version (e.g., `"1.0.0"`). Increment for breaking changes.
- **`segment_event_name`** (string): Event name that appears in Segment/Amplitude (e.g., `"AAP MCP Tool Called"`)
- **`payload_schema`** (object): JSON Schema (Draft 7) describing the `payload` structure

### Optional Fields

- **`rollup_config`** (object): Explicit rollup/aggregation configuration
  - If omitted, metrics-service auto-infers based on `payload_schema`
  - See section below for structure
- **`validate_payload`** (boolean): Whether to validate inbound payloads against `payload_schema` (default: false)

## JSON Schema Definition

The `payload_schema` is a JSON Schema (Draft 7) that describes the structure of telemetry payloads. Use standard JSON Schema syntax:

```yaml
payload_schema:
  type: object
  properties:
    field_name:
      type: string
      description: "Human-readable description"
    numeric_field:
      type: integer
      description: "Numeric value"
      x-analytics-role: stats  # Mark for aggregation
    status_code:
      type: integer
      x-analytics-role: group_by  # Mark for grouping
```

### Field Classification

Fields are classified automatically based on type and `x-analytics-role` hint:

- **`group_by`** fields: Used to partition aggregated results
  - Integer fields ending in `_status`, `_code`, `_type`, `_flag`, `_mode`, `_level`
  - Fields marked with `x-analytics-role: group_by`
- **`stats`** fields: Aggregated with min/max/mean/p95 statistics
  - Numeric fields NOT classified as group_by
  - Fields marked with `x-analytics-role: stats`
- **`identifier`** fields: Unique identifiers (hashed user IDs, session IDs)
  - Fields marked with `x-analytics-role: identifier`
- **`timestamp`** fields: Event timestamps
  - String fields with `format: date-time`
  - Fields marked with `x-analytics-role: timestamp`

## Rollup Configuration

Metrics-service aggregates per-event payloads before sending to Segment using a `rollup_config`:

### Auto-Inferred (Default)

If `rollup_config` is omitted, it's auto-inferred from `payload_schema`:

```yaml
# This example omits rollup_config — auto-inferred based on field types
service_name: aap-mcp-server
event_name: mcp_tool_called
payload_schema:
  type: object
  properties:
    tool_name: {type: string}
    duration_ms: {type: integer, x-analytics-role: stats}
```

Produces:

```python
rollup_config = {
    "strategy": "stats_by_field",
    "group_by": ["tool_name"],
    "stats_fields": ["duration_ms"],
}
```

### Explicit Rollup Config

For fine-grained control, specify `rollup_config`:

```yaml
rollup_config:
  strategy: stats_by_field
  group_by: [tool_name, http_status]
  stats_fields: [duration_ms, parameter_length]
  count_alias: invocation_count
  daily_quota: 50000
```

### Available Strategies

| Strategy | Output | Use Case |
|----------|--------|----------|
| `count_by_field` | COUNT grouped by specified fields | "How many times was each tool called?" |
| `stats_by_field` | COUNT + min/max/mean for numeric fields, grouped | "What was the p50 execution time per tool?" |
| `raw_daily_summary` | All events for the day merged into one summary | Status heartbeats, daily snapshots |
| `passthrough` | Each event sent individually | Already pre-aggregated data |

### Rollup Config Fields

- **`strategy`**: One of the above
- **`group_by`**: List of payload field paths to group on (e.g., `["tool_name", "http_status"]`)
- **`stats_fields`**: List of numeric fields to compute statistics on
- **`count_alias`**: Field name for the count (default: `count`)
- **`daily_quota`**: Max events from this service per day (default: unlimited)

## Adding a New Schema

### Step 1: Create the YAML file

Create `schemas/service_ingest/<service_name>/<event_name>.yaml`:

```yaml
service_name: aap-my-service
event_name: my_event_type
display_name: My Service Event
version: "1.0.0"
segment_event_name: My Service Event Type
validate_payload: false

payload_schema:
  type: object
  properties:
    field1:
      type: string
    field2:
      type: integer
```

### Step 2: Load into database

Run the management command:

```bash
python manage.py load_ingest_schemas --verbose
```

Should output:

```
Loading schemas from: /path/to/schemas/service_ingest
  Processing: aap-my-service/my_event_type.yaml
    Created: aap-my-service/my_event_type
Loaded X schemas: 1 created, 0 updated, 0 errors
```

### Step 3: Commit and push

```bash
git add schemas/
git commit -m "Add schema for aap-my-service/my_event_type"
git push origin feature/branch-name
```

## Schema Evolution

### Adding Fields (Safe — No Version Bump Needed)

Add optional fields at any time. Old events without the new field will still validate:

```yaml
# Before
properties:
  tool_name: {type: string}
  duration_ms: {type: integer}

# After (no version bump)
properties:
  tool_name: {type: string}
  duration_ms: {type: integer}
  cpu_usage: {type: number}  # NEW FIELD
```

### Removing or Renaming Fields (Breaking Change)

Create a new event type instead of modifying the existing one:

```yaml
# NEW FILE: aap-my-service/my_event_v2.yaml
service_name: aap-my-service
event_name: my_event_v2  # NEW event name
# ... rest of config ...
```

This ensures:
- Old dashboards continue using the original event
- New deployments use the v2 event
- No data loss or confusion

## Testing Your Schema

### Validate YAML Structure

```bash
python manage.py load_ingest_schemas --dry-run --schema-dir /path/to/schemas/
```

This parses YAML, validates JSON Schema syntax, and checks rollup config without saving to the database.

### Test Event Ingestion

Once schema is loaded:

```bash
curl -X POST http://localhost:8000/api/v1/ingest/events/ \
  -H "X-Ansible-Service-Auth: <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "aap-my-service",
    "event_name": "my_event_type",
    "payload_type": "event",
    "event_timestamp": "2026-08-25T15:30:00Z",
    "payload": {
      "field1": "value",
      "field2": 42
    }
  }'
```

Should return `202 Accepted`.

## FAQ

**Q: What happens if I add a field to the schema?**  
A: Services sending events without the new field will still validate. The field will be null/absent in old events.

**Q: Can I change the rollup strategy?**  
A: Yes. Update the `rollup_config` in the YAML file and re-run `load_ingest_schemas`. The rollup strategy changes take effect on the next daily rollup.

**Q: What if I need to change the event name?**  
A: Create a new event type (e.g., add `_v2` suffix) with a new YAML file. Old dashboards can continue using the original event.

**Q: How do I know if my schema is loaded?**  
A: Check Django admin at `/admin/service_ingest/servicedefinition/` or query the database directly.

## References

- [JSON Schema Draft 7](https://json-schema.org/draft-07/)
- [ANSTRAT-2255](https://redhat.atlassian.net/browse/ANSTRAT-2255) — Metrics Service Ingress Endpoint & MCP Server Integration
