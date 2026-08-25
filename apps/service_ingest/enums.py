"""Known AAP services and event names for the ingest endpoint.

These enums seed the registry of known integrations. Services can register
with any service_name/event_name — the choices are documentation, not hard
enforcement constraints.
"""

from django.db import models


class KnownService(models.TextChoices):
    MCP_SERVER = "aap-mcp-server", "AAP MCP Server"
    EDA_SERVER = "aap-eda-server", "Event-Driven Ansible"
    AAP_GATEWAY = "aap-gateway", "AAP Gateway"
    HUB = "aap-hub", "Automation Hub"
    LIGHTSPEED = "ansible-lightspeed", "Ansible Lightspeed"


class KnownEvent(models.TextChoices):
    MCP_TOOL_CALLED = "mcp_tool_called", "MCP Tool Called"
    MCP_SERVER_STATUS = "mcp_server_status", "MCP Server Heartbeat"
    EDA_ACTIVATION_DAILY = "eda_activation_daily_summary", "EDA Daily Activation Summary"
    EDA_RULE_FIRINGS = "eda_rule_firing_hourly", "EDA Rule Firing Stats"
    GATEWAY_SNAPSHOT = "gateway_platform_snapshot", "Gateway Platform Snapshot"
    HUB_CONTENT_USAGE = "hub_content_usage_daily", "Hub Content Usage Daily"
