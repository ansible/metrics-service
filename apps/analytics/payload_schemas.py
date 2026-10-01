"""Payload shapes for the metrics-utility collectors exposed by analytics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PayloadField:
    """Describe one JSON property returned by a collector."""

    name: str
    type: str
    description: str = ""
    nullable: bool = True
    fields: tuple[PayloadField, ...] = ()
    items: PayloadField | None = None
    additional_properties: PayloadField | None = None


@dataclass(frozen=True)
class PayloadSchema:
    """Describe the top-level JSON shape returned by a collector."""

    name: str
    kind: str
    description: str
    fields: tuple[PayloadField, ...] = ()
    item_fields: tuple[PayloadField, ...] = ()
    additional_properties: PayloadField | None = None


def _field(name: str, type_: str, description: str = "", *, nullable: bool = True, **kwargs) -> PayloadField:
    return PayloadField(name, type_, description, nullable, **kwargs)


def _object(name: str, fields: tuple[PayloadField, ...] = (), description: str = "", **kwargs) -> PayloadField:
    return _field(name, "object", description, fields=fields, **kwargs)


def _array(name: str, items: PayloadField, description: str = "") -> PayloadField:
    return _field(name, "array", description, items=items)


def _map_value(name: str, type_: str = "object", fields: tuple[PayloadField, ...] = ()) -> PayloadField:
    return PayloadField(name, type_, fields=fields)


_JOB_FIELDS = (
    _field("id", "integer", "Unified job identifier", nullable=False),
    _field("polymorphic_ctype_id", "integer"),
    _field("model", "string"),
    _field("organization_id", "integer"),
    _field("organization_name", "string"),
    _field("execution_environment_image", "string"),
    _field("inventory_id", "integer"),
    _field("inventory_name", "string"),
    _field("execution_environment_id", "integer"),
    _field("created", "datetime"),
    _field("modified", "datetime"),
    _field("name", "string"),
    _field("unified_job_template_id", "integer"),
    _field("launch_type", "string"),
    _field("schedule_id", "integer"),
    _field("execution_node", "string"),
    _field("controller_node", "string"),
    _field("cancel_flag", "boolean"),
    _field("status", "string"),
    _field("failed", "boolean"),
    _field("started", "datetime"),
    _field("finished", "datetime"),
    _field("elapsed", "number"),
    _field("job_explanation", "string"),
    _field("instance_group_id", "integer"),
    _field("installed_collections", "object"),
    _field("ansible_version", "string"),
    _field("forks", "integer"),
    _field("job_template_name", "string"),
    _field("scm_type", "string"),
)

UNIFIED_JOBS_DASHBOARD = PayloadSchema(
    name="UnifiedJobsDashboardPayload",
    kind="array",
    description="Job execution records returned by unified_jobs_dashboard.",
    item_fields=_JOB_FIELDS
    + (
        _field("project_id", "integer"),
        _field("project_name", "string"),
        _field("launched_by_id", "integer"),
        _field("launched_by_username", "string"),
        _field("label_ids", "string", "Comma-separated label IDs."),
        _field("num_hosts", "integer"),
    ),
)

JOB_HOST_SUMMARY = PayloadSchema(
    name="JobHostSummaryServicePayload",
    kind="array",
    description="Per-job host summary records returned by job_host_summary_service.",
    item_fields=(
        _field("id", "integer", nullable=False),
        _field("created", "datetime"),
        _field("modified", "datetime"),
        _field("host_name", "string"),
        _field("host_remote_id", "integer"),
        _field("changed", "integer"),
        _field("dark", "integer"),
        _field("failures", "integer"),
        _field("ok", "integer"),
        _field("processed", "integer"),
        _field("skipped", "integer"),
        _field("failed", "integer"),
        _field("ignored", "integer"),
        _field("rescued", "integer"),
        _field("job_created", "datetime"),
        _field("job_remote_id", "integer"),
        _field("job_template_remote_id", "integer"),
        _field("job_template_name", "string"),
        _field("ansible_version", "string"),
        _field("launch_type", "string"),
        _field("inventory_remote_id", "integer"),
        _field("inventory_name", "string"),
        _field("organization_remote_id", "integer"),
        _field("organization_name", "string"),
        _field("project_remote_id", "integer"),
        _field("project_name", "string"),
        _field("model", "string"),
    ),
)

CREDENTIALS = PayloadSchema(
    name="CredentialsServicePayload",
    kind="array",
    description="Managed credential types used by jobs in the collection window.",
    item_fields=(_field("credential_type", "string", nullable=False),),
)

EVENT_FIELDS = (
    _field("id", "integer", nullable=False),
    _field("created", "datetime"),
    _field("modified", "datetime"),
    _field("job_created", "datetime"),
    _field("uuid", "string"),
    _field("parent_uuid", "string"),
    _field("event", "string"),
    _field("task_action", "string"),
    _field("resolved_action", "string"),
    _field("resolved_role", "string"),
    _field("failed", "boolean"),
    _field("changed", "boolean"),
    _field("playbook", "string"),
    _field("play", "string"),
    _field("task", "string"),
    _field("role", "string"),
    _field("job_id", "integer"),
    _field("host_id", "integer"),
    _field("host_name", "string"),
)

MAIN_JOBEVENT = PayloadSchema(
    name="MainJobeventServicePayload",
    kind="array",
    description="Selected job events returned by main_jobevent_service.",
    item_fields=EVENT_FIELDS
    + (
        _field("duration", "string"),
        _field("start", "datetime"),
        _field("end", "datetime"),
        _field("task_uuid", "string"),
        _field("ignore_errors", "boolean"),
        _field("job_remote_id", "integer"),
        _field("host_remote_id", "integer"),
        _array("warnings", _field("warning", "string")),
        _array("deprecations", _field("deprecation", "string")),
        _field("event_data_length", "integer"),
        _field("job_failed", "boolean"),
        _field("job_started", "datetime"),
    ),
)

EVENTS_TABLE = PayloadSchema(
    name="EventsTablePayload",
    kind="array",
    description="Raw job events returned by events_table.",
    item_fields=EVENT_FIELDS
    + (
        _object("playbook_on_stats"),
        _field("start", "datetime"),
        _field("end", "datetime"),
        _field("duration", "string"),
        _array("warnings", _field("warning", "string")),
        _array("deprecations", _field("deprecation", "string")),
    ),
)

WORKFLOW_NODE_FIELDS = (
    _field("id", "integer", nullable=False),
    _field("created", "datetime"),
    _field("modified", "datetime"),
    _field("job_id", "integer"),
    _field("unified_job_template_id", "integer"),
    _field("workflow_job_id", "integer"),
    _field("inventory_id", "integer"),
    _array("success_nodes", _field("node_id", "integer")),
    _array("failure_nodes", _field("node_id", "integer")),
    _array("always_nodes", _field("node_id", "integer")),
    _field("do_not_run", "boolean"),
    _field("all_parents_must_converge", "boolean"),
)

WORKFLOW_JOB_NODE = PayloadSchema(
    name="WorkflowJobNodeTablePayload",
    kind="array",
    description="Workflow job node executions and their edge relationships.",
    item_fields=WORKFLOW_NODE_FIELDS,
)

QUERY_INFO = PayloadSchema(
    name="QueryInfoPayload",
    kind="object",
    description="Collection metadata returned by query_info.",
    fields=(
        _field("last_run", "string", "String representation of the requested start bound."),
        _field("current_time", "string", "String representation of the requested end bound."),
        _field("collection_type", "string"),
    ),
)

EXECUTION_ENVIRONMENTS = PayloadSchema(
    name="ExecutionEnvironmentsPayload",
    kind="array",
    description="Execution environment records.",
    item_fields=(
        _field("id", "integer", nullable=False),
        _field("created", "datetime"),
        _field("modified", "datetime"),
        _field("description", "string"),
        _field("image", "string"),
        _field("managed", "boolean"),
        _field("created_by_id", "integer"),
        _field("credential_id", "integer"),
        _field("modified_by_id", "integer"),
        _field("organization_id", "integer"),
        _field("name", "string"),
        _field("pull", "string"),
    ),
)

_PLATFORM_FIELDS = (
    _field("dist", "string"),
    _field("release", "string"),
    _field("system", "string"),
    _field("type", "string"),
)

CONFIG = PayloadSchema(
    name="ConfigPayload",
    kind="object",
    description="Controller configuration, license, version, and platform metadata.",
    fields=(
        _field("authentication_backends", "array", items=_field("backend", "string")),
        _field("controller_url_base", "string"),
        _field("external_logger_enabled", "boolean"),
        _field("external_logger_type", "string"),
        _field("install_uuid", "string"),
        _field("instance_uuid", "string"),
        _field("logging_aggregators", "array", items=_field("logger", "string")),
        _field("pendo_tracking", "string"),
        _field("subscription_usage_model", "string"),
        _field("account_number", "string"),
        _field("automated_instances", "integer"),
        _field("automated_since", "datetime"),
        _field("compliant", "boolean"),
        _field("current_instances", "integer"),
        _field("date_expired", "datetime"),
        _field("date_warning", "datetime"),
        _field("free_instances", "integer"),
        _field("grace_period_remaining", "integer"),
        _field("license_date", "datetime"),
        _field("license_expiry", "integer"),
        _field("license_type", "string"),
        _field("pool_id", "string"),
        _field("product_name", "string"),
        _field("satellite", "boolean"),
        _field("sku", "string"),
        _field("subscription_id", "string"),
        _field("subscription_name", "string"),
        _field("support_level", "string"),
        _field("total_licensed_instances", "integer"),
        _field("trial", "boolean"),
        _field("usage", "number"),
        _field("valid_key", "boolean"),
        _object("billing_provider_params"),
        _field("controller_version", "string"),
        _field("metrics_utility_version", "string"),
        _object("platform", _PLATFORM_FIELDS),
    ),
)

CONTROLLER_VERSION = PayloadSchema(
    name="ControllerVersionServicePayload",
    kind="array",
    description="Distinct versions reported by enabled Controller instances.",
    item_fields=(_field("controller_version", "string", nullable=False),),
)

TABLE_METADATA = PayloadSchema(
    name="TableMetadataPayload",
    kind="array",
    description="Estimated row counts and relation sizes for selected Controller tables.",
    item_fields=(
        _field("schemaname", "string"),
        _field("tablename", "string"),
        _field("estimated_row_count", "integer"),
        _field("total_size_bytes", "integer"),
        _field("table_size_bytes", "integer"),
        _field("indexes_size_bytes", "integer"),
    ),
)

FEATURE_FLAGS = PayloadSchema(
    name="FeatureFlagsServicePayload",
    kind="array",
    description="Enabled boolean platform feature flags.",
    item_fields=(
        _field("name", "string", nullable=False),
        _field("condition", "string"),
        _field("value", "string"),
        _field("description", "string"),
        _field("support_level", "string"),
        _field("toggle_type", "string"),
        _field("visibility", "string"),
    ),
)

COUNTS = PayloadSchema(
    name="CountsPayload",
    kind="object",
    description="Controller object, inventory, session, job, and database counts.",
    fields=(
        *(
            _field(name, "integer")
            for name in (
                "organization",
                "team",
                "user",
                "inventory",
                "credential",
                "project",
                "job_template",
                "workflow_job_template",
                "host",
                "schedule",
                "notification_template",
                "unified_job",
                "active_host_count",
                "active_sessions",
                "active_user_sessions",
                "active_anonymous_sessions",
                "running_jobs",
                "pending_jobs",
                "database_connections",
            )
        ),
        _object("inventories", additional_properties=_map_value("InventoryKindCount", "integer")),
    ),
)

CRED_TYPE_FIELDS = (
    _field("name", "string"),
    _field("credential_count", "integer"),
    _field("managed", "boolean"),
)

CRED_TYPE_COUNTS = PayloadSchema(
    name="CredTypeCountsPayload",
    kind="object",
    description="Credential counts keyed by credential type ID.",
    additional_properties=_map_value("CredentialTypeCount", "object", CRED_TYPE_FIELDS),
)

HOST_METRIC_SUMMARY_MONTHLY = PayloadSchema(
    name="HostMetricSummaryMonthlyTablePayload",
    kind="array",
    description="Monthly host capacity and usage summaries.",
    item_fields=(
        _field("id", "integer", nullable=False),
        _field("date", "date"),
        _field("license_capacity", "integer"),
        _field("license_consumed", "integer"),
        _field("hosts_added", "integer"),
        _field("hosts_deleted", "integer"),
        _field("indirectly_managed_hosts", "integer"),
    ),
)

INSTANCE_FIELDS = (
    _field("uuid", "string"),
    _field("version", "string"),
    _field("capacity", "integer"),
    _field("cpu", "integer"),
    _field("memory", "integer"),
    _field("managed_by_policy", "boolean"),
    _field("enabled", "boolean"),
    _field("consumed_capacity", "integer"),
    _field("remaining_capacity", "integer"),
    _field("node_type", "string"),
)

INSTANCE_INFO = PayloadSchema(
    name="InstanceInfoPayload",
    kind="object",
    description="Controller instance topology and consumed capacity keyed by UUID.",
    additional_properties=_map_value("InstanceInfoRecord", "object", INSTANCE_FIELDS),
)

INVENTORY_FIELDS = (
    _field("name", "string"),
    _field("kind", "string"),
    _field("hosts", "integer"),
    _field("sources", "integer"),
    _array(
        "source_list",
        _object(
            "source",
            (
                _field("name", "string"),
                _field("source", "string"),
                _field("num_hosts", "integer"),
            ),
        ),
    ),
)

INVENTORY_COUNTS = PayloadSchema(
    name="InventoryCountsPayload",
    kind="object",
    description="Inventory details keyed by inventory ID.",
    additional_properties=_map_value("InventoryCount", "object", INVENTORY_FIELDS),
)

ORG_COUNTS = PayloadSchema(
    name="OrgCountsPayload",
    kind="object",
    description="Organization user and team counts keyed by organization ID.",
    additional_properties=_map_value(
        "OrganizationCount",
        "object",
        (_field("name", "string"), _field("users", "integer"), _field("teams", "integer")),
    ),
)

PROJECTS_BY_SCM_TYPE = PayloadSchema(
    name="ProjectsByScmTypePayload",
    kind="object",
    description="Project counts keyed by source-control type.",
    additional_properties=_map_value("ProjectScmTypeCount", "integer"),
)

UNIFIED_JOB_TEMPLATE = PayloadSchema(
    name="UnifiedJobTemplateTablePayload",
    kind="array",
    description="Unified job template identity, scheduling, and status records.",
    item_fields=(
        _field("id", "integer", nullable=False),
        _field("polymorphic_ctype_id", "integer"),
        _field("model", "string"),
        _field("execution_environment_image", "string"),
        _field("created", "datetime"),
        _field("modified", "datetime"),
        _field("created_by_id", "integer"),
        _field("modified_by_id", "integer"),
        _field("name", "string"),
        _field("current_job_id", "integer"),
        _field("last_job_id", "integer"),
        _field("last_job_failed", "boolean"),
        _field("last_job_run", "datetime"),
        _field("next_job_run", "datetime"),
        _field("next_schedule_id", "integer"),
        _field("status", "string"),
    ),
)

WORKFLOW_JOB_TEMPLATE_NODE = PayloadSchema(
    name="WorkflowJobTemplateNodeTablePayload",
    kind="array",
    description="Workflow job template node definitions and edge relationships.",
    item_fields=WORKFLOW_NODE_FIELDS[:3]
    + (
        _field("unified_job_template_id", "integer"),
        _field("workflow_job_template_id", "integer"),
        _field("inventory_id", "integer"),
        _array("success_nodes", _field("node_id", "integer")),
        _array("failure_nodes", _field("node_id", "integer")),
        _array("always_nodes", _field("node_id", "integer")),
        _field("all_parents_must_converge", "boolean"),
    ),
)

_HOST_FIELDS = (
    _field("host_name", "string", nullable=False),
    _field("host_id", "integer"),
    _field("inventory_remote_id", "integer"),
    _field("inventory_name", "string"),
    _field("organization_remote_id", "integer"),
    _field("organization_name", "string"),
    _field("last_automation", "datetime"),
    _field("ansible_host_variable", "string"),
    _object("canonical_facts", additional_properties=_map_value("CanonicalFact", "object")),
    _object("facts", additional_properties=_map_value("Fact", "string")),
)

MAIN_HOST = PayloadSchema(
    name="MainHostPayload",
    kind="array",
    description="Enabled inventory hosts and selected host facts.",
    item_fields=_HOST_FIELDS,
)

MAIN_HOSTMETRIC = PayloadSchema(
    name="MainHostmetricPayload",
    kind="array",
    description="Host automation, deletion, and identity metrics.",
    item_fields=(
        _field("hostname", "string", nullable=False),
        _field("host_id", "integer"),
        _field("first_automation", "datetime"),
        _field("last_automation", "datetime"),
        _field("automated_counter", "integer"),
        _field("deleted_counter", "integer"),
        _field("last_deleted", "datetime"),
        _field("deleted", "boolean"),
        _field("id", "integer"),
        _field("used_in_inventories", "integer"),
        _field("ansible_product_serial", "string"),
        _field("ansible_machine_id", "string"),
        _field("ansible_host_variable", "string"),
        _field("ansible_connection_variable", "string"),
    ),
)


PAYLOAD_SCHEMAS = {
    "unified_jobs_dashboard": UNIFIED_JOBS_DASHBOARD,
    "job_host_summary_service": JOB_HOST_SUMMARY,
    "credentials_service": CREDENTIALS,
    "main_jobevent_service": MAIN_JOBEVENT,
    "events_table": EVENTS_TABLE,
    "workflow_job_node_table": WORKFLOW_JOB_NODE,
    "query_info": QUERY_INFO,
    "execution_environments": EXECUTION_ENVIRONMENTS,
    "config": CONFIG,
    "controller_version_service": CONTROLLER_VERSION,
    "table_metadata": TABLE_METADATA,
    "feature_flags_service": FEATURE_FLAGS,
    "counts": COUNTS,
    "cred_type_counts": CRED_TYPE_COUNTS,
    "host_metric_summary_monthly_table": HOST_METRIC_SUMMARY_MONTHLY,
    "instance_info": INSTANCE_INFO,
    "inventory_counts": INVENTORY_COUNTS,
    "org_counts": ORG_COUNTS,
    "projects_by_scm_type": PROJECTS_BY_SCM_TYPE,
    "unified_job_template_table": UNIFIED_JOB_TEMPLATE,
    "workflow_job_template_node_table": WORKFLOW_JOB_TEMPLATE_NODE,
    "main_host": MAIN_HOST,
    "main_host_daily": MAIN_HOST,
    "main_hostmetric": MAIN_HOSTMETRIC,
}
