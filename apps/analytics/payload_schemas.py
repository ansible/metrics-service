"""Payload shapes for the metrics-utility collectors exposed by analytics.

Each schema mirrors the output of the metrics-utility collector of the same name
(``metrics_utility/library/collectors/controller/<name>.py``). DataFrame collectors are
arrays of records whose fields follow the SQL ``SELECT`` list; dict collectors are objects.
DataFrame values are stored after ``DataFrame.to_json(orient="records", date_format="iso")``,
so timestamps are ISO 8601 strings and missing values are null.
"""

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
    # What the top-level keys represent, for objects keyed by data (additional_properties).
    key_field: str | None = None

    def __post_init__(self) -> None:
        """Reject shape metadata that contradicts the schema kind."""
        if self.kind not in {"object", "array"}:
            raise ValueError(f"Unsupported payload schema kind for {self.name}: {self.kind}")
        if (self.key_field is not None) != (self.additional_properties is not None):
            raise ValueError(f"key_field must be set exactly for keyed objects: {self.name}")


def _field(name: str, type_: str, description: str, *, nullable: bool = True, **kwargs) -> PayloadField:
    return PayloadField(name, type_, description, nullable, **kwargs)


def _object(name: str, fields: tuple[PayloadField, ...] = (), description: str = "", **kwargs) -> PayloadField:
    return _field(name, "object", description, fields=fields, **kwargs)


def _array(name: str, items: PayloadField, description: str) -> PayloadField:
    return _field(name, "array", description, items=items)


def _map_value(
    name: str,
    type_: str = "object",
    fields: tuple[PayloadField, ...] = (),
    *,
    description: str,
) -> PayloadField:
    return PayloadField(name, type_, description, fields=fields)


def _pick(catalog: dict[str, PayloadField], *names: str) -> tuple[PayloadField, ...]:
    """Select fields from a catalog in collector column order."""
    return tuple(catalog[name] for name in names)


def _catalog(*fields: PayloadField) -> dict[str, PayloadField]:
    return {field.name: field for field in fields}


_INSTALLED_COLLECTIONS = _object(
    "installed_collections",
    description="Ansible collections installed in the job's execution environment, keyed by collection FQCN.",
    additional_properties=_map_value(
        "InstalledCollection",
        "object",
        (_field("version", "string", "Installed collection version."),),
        description="Installed collection record.",
    ),
)

_JOB_FIELDS = (
    _field("id", "integer", "Unified job identifier", nullable=False),
    _field("polymorphic_ctype_id", "integer", "Django content type ID of the concrete job type."),
    _field("model", "string", "Controller content type model name, for example job, projectupdate, or workflowjob."),
    _field("organization_id", "integer", "Controller organization identifier."),
    _field("organization_name", "string", "Controller organization name."),
    _field("execution_environment_image", "string", "Execution environment image used by the job."),
    _field("inventory_id", "integer", "Controller inventory identifier."),
    _field("inventory_name", "string", "Controller inventory name."),
    _field("execution_environment_id", "integer", "Execution environment identifier."),
    _field("created", "datetime", "Job creation time."),
    _field("modified", "datetime", "Job last-modification time."),
    _field("name", "string", "Job name."),
    _field("unified_job_template_id", "integer", "Unified job template identifier."),
    _field("launch_type", "string", "How the job was launched, for example manual, relaunch, scheduled, or workflow."),
    _field("schedule_id", "integer", "Schedule identifier used to launch the job."),
    _field("execution_node", "string", "Node on which the job executed."),
    _field("controller_node", "string", "Controller node that handled the job."),
    _field("cancel_flag", "boolean", "Whether cancellation was requested for the job."),
    _field("status", "string", "Job status."),
    _field("failed", "boolean", "Whether the job failed."),
    _field("started", "datetime", "Job start time."),
    _field("finished", "datetime", "Job finish time."),
    _field("elapsed", "string", 'Job run time in seconds, as a decimal string (for example "120.000").'),
    _field("job_explanation", "string", "Explanation recorded for the job."),
    _field("instance_group_id", "integer", "Instance group identifier used by the job."),
    _INSTALLED_COLLECTIONS,
    _field("ansible_version", "string", "Ansible version used by the job."),
    _field("forks", "integer", "Maximum number of parallel forks configured for the job."),
    _field("job_template_name", "string", "Unified job template name."),
    _field("scm_type", "string", "Source-control type of the job's project."),
)

UNIFIED_JOBS = PayloadSchema(
    name="UnifiedJobsPayload",
    kind="array",
    description="Unified job records returned by unified_jobs, filtered by job finish time.",
    item_fields=tuple(field for field in _JOB_FIELDS if field.name != "modified"),
)

UNIFIED_JOBS_ORG = PayloadSchema(
    name="UnifiedJobsOrgPayload",
    kind="array",
    description="Unified job summaries grouped by organization, job type, and status.",
    item_fields=(
        _field("organization_id", "integer", "Controller organization identifier."),
        _field("organization_name", "string", "Controller organization name."),
        _field("job_type", "string", "Unified job type."),
        _field("status", "string", "Job status."),
        _field("job_count", "integer", "Number of jobs in this group."),
        _field("failure_count", "integer", "Number of failed jobs in this group."),
        _field("elapsed_total", "number", "Total job run time in seconds for this group."),
        _field("elapsed_average", "number", "Average job run time in seconds for this group."),
    ),
)

UNIFIED_JOBS_DASHBOARD = PayloadSchema(
    name="UnifiedJobsDashboardPayload",
    kind="array",
    description="Job execution records returned by unified_jobs_dashboard, filtered by job finish time.",
    item_fields=_JOB_FIELDS
    + (
        _field("project_id", "integer", "Controller project identifier."),
        _field("project_name", "string", "Controller project name."),
        _field(
            "launched_by_id", "integer", "User ID that launched the job; null unless launch_type is manual or relaunch."
        ),
        # The collector also returns launched_by_username, which is deliberately undeclared: it is
        # collected only for the in-service dashboard sync and withheld from everything leaving the
        # service (ANSTRAT-1587 requirement #8, AAP-96704, ansible/metrics-service#495).
        _field("label_ids", "string", "Comma-separated label IDs."),
        _field("num_hosts", "integer", "Number of job host summaries recorded for the job."),
    ),
)

_HOST_SUMMARY = _catalog(
    _field("id", "integer", "Job host summary identifier", nullable=False),
    _field("created", "datetime", "Job host summary creation time."),
    _field("modified", "datetime", "Job host summary last-modification time."),
    _field("host_name", "string", "Inventory host name."),
    _field("host_remote_id", "integer", "Controller host ID."),
    _field("ansible_host_variable", "string", "ansible_host value from the host variables."),
    _field("ansible_connection_variable", "string", "ansible_connection value from the host variables."),
    _field("changed", "integer", "Number of tasks that reported changes on the host."),
    _field("dark", "integer", "Number of tasks for which the host was unreachable."),
    _field("failures", "integer", "Number of failed tasks on the host."),
    _field("ok", "integer", "Number of successful tasks on the host."),
    _field("processed", "integer", "Number of processed tasks on the host."),
    _field("skipped", "integer", "Number of skipped tasks on the host."),
    _field("failed", "boolean", "Whether the host failed in the job."),
    _field("ignored", "integer", "Number of failed tasks ignored on the host."),
    _field("rescued", "integer", "Number of failed tasks rescued on the host."),
    _field("job_created", "datetime", "Creation time of the related job."),
    _field("job_remote_id", "integer", "Controller job ID."),
    _field("job_template_remote_id", "integer", "Controller unified job template ID."),
    _field("job_template_name", "string", "Unified job template name."),
    _field("ansible_version", "string", "Ansible version used by the related job."),
    _field("launch_type", "string", "How the related job was launched."),
    _field("inventory_remote_id", "integer", "Controller inventory ID."),
    _field("inventory_name", "string", "Controller inventory name."),
    _field("organization_remote_id", "integer", "Controller organization ID."),
    _field("organization_name", "string", "Controller organization name."),
    _field("project_remote_id", "integer", "Controller project ID."),
    _field("project_name", "string", "Controller project name."),
    _field("model", "string", "Concrete job type of the related job."),
)

JOB_HOST_SUMMARY = PayloadSchema(
    name="JobHostSummaryPayload",
    kind="array",
    description="Per-job host summary records returned by job_host_summary, filtered by summary modification time.",
    item_fields=_pick(
        _HOST_SUMMARY,
        "id",
        "created",
        "modified",
        "host_name",
        "host_remote_id",
        "ansible_host_variable",
        "ansible_connection_variable",
        "changed",
        "dark",
        "failures",
        "ok",
        "processed",
        "skipped",
        "failed",
        "ignored",
        "rescued",
        "job_created",
        "job_remote_id",
        "job_template_remote_id",
        "job_template_name",
        "inventory_remote_id",
        "inventory_name",
        "organization_remote_id",
        "organization_name",
        "project_remote_id",
        "project_name",
    ),
)

JOB_HOST_SUMMARY_SERVICE = PayloadSchema(
    name="JobHostSummaryServicePayload",
    kind="array",
    description="Per-job host summary records returned by job_host_summary_service, filtered by job finish time.",
    item_fields=_pick(
        _HOST_SUMMARY,
        "id",
        "created",
        "modified",
        "host_name",
        "host_remote_id",
        "changed",
        "dark",
        "failures",
        "ok",
        "processed",
        "skipped",
        "failed",
        "ignored",
        "rescued",
        "job_created",
        "job_remote_id",
        "job_template_remote_id",
        "job_template_name",
        "ansible_version",
        "launch_type",
        "inventory_remote_id",
        "inventory_name",
        "organization_remote_id",
        "organization_name",
        "project_remote_id",
        "project_name",
        "model",
    ),
)

CREDENTIALS = PayloadSchema(
    name="CredentialsServicePayload",
    kind="array",
    description="Managed credential types used by jobs in the collection window.",
    item_fields=(_field("credential_type", "string", "Managed credential type name.", nullable=False),),
)

CREDENTIALS_SERVICE_ORG = PayloadSchema(
    name="CredentialsServiceOrgPayload",
    kind="array",
    description="Managed credential types used by jobs, grouped by job organization.",
    item_fields=(
        _field("organization_id", "integer", "Controller organization identifier."),
        _field("organization_name", "string", "Controller organization name."),
        _field("credential_type", "string", "Managed credential type name.", nullable=False),
    ),
)

_DEPRECATION = _object(
    "deprecation",
    (
        _field("msg", "string", "Deprecation message."),
        _field("version", "string", "Version in which the deprecated feature is removed."),
        _field("date", "string", "Date after which the deprecated feature is removed."),
        _field("collection_name", "string", "Ansible collection containing the deprecated feature."),
    ),
    description="Deprecation details reported by the task result.",
)

_EVENT = _catalog(
    _field("main_jobhostsummary_id", "integer", "Job host summary that selected this event."),
    _field("main_jobhostsummary_created", "datetime", "Creation time of the selected job host summary."),
    _field("id", "integer", "Job event identifier", nullable=False),
    _field("created", "datetime", "Event creation time."),
    _field("modified", "datetime", "Event last-modification time."),
    _field("job_created", "datetime", "Creation time of the event's job; the job event partition key."),
    _field("job_finished", "datetime", "Finish time of the related job."),
    _field("ansible_version", "string", "Ansible version used by the related job."),
    _field("uuid", "string", "Event UUID."),
    _field("parent_uuid", "string", "UUID of the parent event."),
    _field("event", "string", "Ansible callback event name, for example runner_on_ok."),
    _field("task_action", "string", "Module or action name as written in the task."),
    _field("resolved_action", "string", "Fully-qualified module or action name resolved by Ansible."),
    _field("resolved_role", "string", "Role associated with the event."),
    _object(
        "playbook_on_stats",
        description="Event data of playbook_on_stats events (per-host result counts), without artifact_data; null for other events.",
    ),
    _field("duration", "string", "Task duration in seconds, as recorded in the event data."),
    _field("start", "datetime", "Task start time recorded in the event data."),
    _field("end", "datetime", "Task end time recorded in the event data."),
    _field("task_uuid", "string", "UUID of the task recorded in the event data."),
    _field("ignore_errors", "boolean", "Whether the failed task had ignore_errors set; false when unknown."),
    _field("failed", "boolean", "Whether the event reported a failure."),
    _field("changed", "boolean", "Whether the event reported a change."),
    _field("playbook", "string", "Playbook name recorded for the event."),
    _field("play", "string", "Play name recorded for the event."),
    _field("task", "string", "Task name recorded for the event."),
    _field("role", "string", "Role name recorded for the event."),
    _field("job_remote_id", "integer", "Controller job ID."),
    _field("job_id", "integer", "Unified job identifier associated with the event."),
    _field("host_remote_id", "integer", "Controller host ID."),
    _field("host_id", "integer", "Inventory host identifier associated with the event."),
    _field("host_name", "string", "Inventory host name recorded for the event."),
    _array(
        "warnings",
        _field("warning", "string", "Warning reported in the task result."),
        "Warnings reported in the task result.",
    ),
    _array("deprecations", _DEPRECATION, "Deprecations reported in the task result."),
    _field("event_data_length", "integer", "Stored size of the raw event data, in bytes."),
    _field("job_failed", "boolean", "Whether the related job failed."),
    _field("job_started", "datetime", "Start time of the related job."),
)

MAIN_JOBEVENT = PayloadSchema(
    name="MainJobeventPayload",
    kind="array",
    description="Runner events for job hosts whose summaries were modified in the window, returned by main_jobevent.",
    item_fields=_pick(
        _EVENT,
        "main_jobhostsummary_id",
        "main_jobhostsummary_created",
        "id",
        "created",
        "modified",
        "job_created",
        "event",
        "task_action",
        "resolved_action",
        "resolved_role",
        "duration",
        "failed",
        "changed",
        "playbook",
        "play",
        "task",
        "role",
        "job_remote_id",
        "host_remote_id",
        "host_name",
    ),
)

MAIN_JOBEVENT_SERVICE = PayloadSchema(
    name="MainJobeventServicePayload",
    kind="array",
    description="Selected runner and annotation events for jobs finished in the window, returned by main_jobevent_service.",
    item_fields=_pick(
        _EVENT,
        "id",
        "created",
        "modified",
        "job_created",
        "job_finished",
        "ansible_version",
        "uuid",
        "parent_uuid",
        "event",
        "task_action",
        "resolved_action",
        "resolved_role",
        "duration",
        "start",
        "end",
        "task_uuid",
        "ignore_errors",
        "failed",
        "changed",
        "playbook",
        "play",
        "task",
        "role",
        "job_remote_id",
        "job_id",
        "host_remote_id",
        "host_id",
        "host_name",
        "warnings",
        "deprecations",
        "event_data_length",
        "job_failed",
        "job_started",
    ),
)

EVENTS_TABLE = PayloadSchema(
    name="EventsTablePayload",
    kind="array",
    description="Raw job events modified in the window, returned by events_table.",
    item_fields=_pick(
        _EVENT,
        "id",
        "created",
        "modified",
        "job_created",
        "uuid",
        "parent_uuid",
        "event",
        "task_action",
        "resolved_action",
        "resolved_role",
        "playbook_on_stats",
        "failed",
        "changed",
        "playbook",
        "play",
        "task",
        "role",
        "job_id",
        "host_id",
        "host_name",
        "start",
        "end",
        "duration",
        "warnings",
        "deprecations",
    ),
)

_EDGE_FIELDS = (
    _array(
        "success_nodes",
        _field("node_id", "integer", "Workflow node identifier."),
        "Nodes run when this node succeeds.",
    ),
    _array(
        "failure_nodes",
        _field("node_id", "integer", "Workflow node identifier."),
        "Nodes run when this node fails.",
    ),
    _array(
        "always_nodes",
        _field("node_id", "integer", "Workflow node identifier."),
        "Nodes run regardless of this node's result.",
    ),
)

WORKFLOW_JOB_NODE = PayloadSchema(
    name="WorkflowJobNodeTablePayload",
    kind="array",
    description="Workflow job node executions and their edge relationships.",
    item_fields=(
        _field("id", "integer", "Workflow job node identifier", nullable=False),
        _field("created", "datetime", "Workflow job node creation time."),
        _field("modified", "datetime", "Workflow job node last-modification time."),
        _field("job_id", "integer", "Unified job spawned by this node."),
        _field("unified_job_template_id", "integer", "Unified job template identifier."),
        _field("workflow_job_id", "integer", "Workflow job identifier."),
        _field("inventory_id", "integer", "Controller inventory identifier."),
        *_EDGE_FIELDS,
        _field("do_not_run", "boolean", "Whether this workflow node is disabled."),
        _field(
            "all_parents_must_converge",
            "boolean",
            "Whether all parent nodes must converge before this node runs.",
        ),
    ),
)

QUERY_INFO = PayloadSchema(
    name="QueryInfoPayload",
    kind="object",
    description="Collection metadata returned by query_info.",
    fields=(
        _field("last_run", "string", 'String representation of the requested start bound ("None" when unbounded).'),
        _field("current_time", "string", 'String representation of the requested end bound ("None" when unbounded).'),
        _field("collection_type", "string", "Type of collection that produced this metadata."),
    ),
)

EXECUTION_ENVIRONMENTS = PayloadSchema(
    name="ExecutionEnvironmentsPayload",
    kind="array",
    description="Execution environment records.",
    item_fields=(
        _field("id", "integer", "Execution environment identifier", nullable=False),
        _field("created", "datetime", "Execution environment creation time."),
        _field("modified", "datetime", "Execution environment last-modification time."),
        _field("description", "string", "Description of the execution environment."),
        _field("image", "string", "Container image used by the execution environment."),
        _field("managed", "boolean", "Whether the execution environment is managed by the platform."),
        _field("created_by_id", "integer", "Identifier of the user who created the execution environment."),
        _field("credential_id", "integer", "Credential identifier used to access the execution environment."),
        _field("modified_by_id", "integer", "Identifier of the user who last modified the execution environment."),
        _field("organization_id", "integer", "Controller organization owning the execution environment."),
        _field("name", "string", "Execution environment name."),
        _field("pull", "string", "Image pull policy."),
    ),
)

_PLATFORM_FIELDS = (
    _array(
        "dist",
        _field("part", "string", "Linux distribution component."),
        "Linux distribution name, version, and codename.",
    ),
    _field("release", "string", "Operating system release."),
    _field("system", "string", "Operating system name."),
    _field("type", "string", "Install type: openshift, k8s, or traditional."),
)

CONFIG = PayloadSchema(
    name="ConfigPayload",
    kind="object",
    description="Controller configuration, license, version, and platform metadata.",
    fields=(
        _array(
            "authentication_backends",
            _field("backend", "string", "Authentication backend name."),
            "Configured authentication backends.",
        ),
        _field("controller_url_base", "string", "Base URL of the Controller."),
        _field("external_logger_enabled", "boolean", "Whether external logging is enabled."),
        _field("external_logger_type", "string", "External logger type."),
        _field("install_uuid", "string", "Controller installation UUID."),
        _field("instance_uuid", "string", "Controller instance UUID."),
        _array(
            "logging_aggregators",
            _field("logger", "string", "Logging aggregator name."),
            "Configured logging aggregators.",
        ),
        _field("pendo_tracking", "string", "Pendo tracking state."),
        _field("subscription_usage_model", "string", "Subscription usage model."),
        _field("account_number", "string", "Subscription account number."),
        _field("automated_instances", "integer", "Number of automated instances."),
        _field("automated_since", "integer", "Unix timestamp of the first automation."),
        _field("compliant", "boolean", "Whether the subscription is compliant."),
        _field("current_instances", "integer", "Current instance count."),
        _field("date_expired", "boolean", "Whether the subscription has expired."),
        _field("date_warning", "boolean", "Whether the subscription is close to expiring."),
        _field("free_instances", "integer", "Number of free instances."),
        _field("grace_period_remaining", "integer", "Seconds of grace period remaining."),
        _field("license_date", "integer", "Unix timestamp when the subscription ends."),
        _field("license_expiry", "integer", "Seconds until the subscription ends."),
        _field("license_type", "string", "License type."),
        _field("pool_id", "string", "Subscription pool identifier."),
        _field("product_name", "string", "Licensed product name."),
        _field("satellite", "boolean", "Whether the subscription is provided through Satellite."),
        _field("sku", "string", "Subscription SKU."),
        _field("subscription_id", "string", "Subscription identifier."),
        _field("subscription_name", "string", "Subscription name."),
        _field("support_level", "string", "Subscription support level."),
        _field("total_licensed_instances", "integer", "Total number of licensed instances."),
        _field("trial", "boolean", "Whether the subscription is a trial."),
        _field("usage", "string", "Subscription usage, for example Production or Development."),
        _field("valid_key", "boolean", "Whether the license key is valid."),
        _object(
            "billing_provider_params",
            description="Billing provider metadata supplied by the collection environment; keys depend on the provider.",
        ),
        _field("controller_version", "string", "Controller version reported by the collection environment."),
        _field("metrics_utility_version", "string", "Metrics Utility version."),
        _object("platform", _PLATFORM_FIELDS, "Runtime platform metadata."),
    ),
)

CONTROLLER_VERSION = PayloadSchema(
    name="ControllerVersionServicePayload",
    kind="array",
    description="Distinct versions reported by enabled Controller instances.",
    item_fields=(
        _field("controller_version", "string", "Controller version reported by an enabled instance.", nullable=False),
    ),
)

TABLE_METADATA = PayloadSchema(
    name="TableMetadataPayload",
    kind="array",
    description="Estimated row counts and relation sizes for selected Controller tables.",
    item_fields=(
        _field("schemaname", "string", "Database schema name."),
        _field("tablename", "string", "Database table name."),
        _field("estimated_row_count", "integer", "Estimated number of rows in the table."),
        _field("total_size_bytes", "integer", "Total table and index size in bytes."),
        _field("table_size_bytes", "integer", "Table size in bytes."),
        _field("indexes_size_bytes", "integer", "Index size in bytes."),
    ),
)

FEATURE_FLAGS = PayloadSchema(
    name="FeatureFlagsServicePayload",
    kind="array",
    description="Enabled boolean platform feature flags.",
    item_fields=(
        _field("name", "string", "Feature flag name.", nullable=False),
        _field("condition", "string", "Feature flag condition."),
        _field("value", "string", "Feature flag value."),
        _field("description", "string", "Feature flag description."),
        _field("support_level", "string", "Feature flag support level."),
        _field("toggle_type", "string", "Feature flag toggle type."),
        _field("visibility", "boolean", "Whether the feature flag is visible."),
    ),
)

_COUNT_FIELDS = (
    _field("organization", "integer", "Number of organizations."),
    _field("team", "integer", "Number of teams."),
    _field("user", "integer", "Number of users."),
    _field("inventory", "integer", "Number of inventories."),
    _field("credential", "integer", "Number of credentials."),
    _field("project", "integer", "Number of projects."),
    _field("job_template", "integer", "Number of job templates."),
    _field("workflow_job_template", "integer", "Number of workflow job templates."),
    _field("host", "integer", "Number of hosts."),
    _field("schedule", "integer", "Number of schedules."),
    _field("notification_template", "integer", "Number of notification templates."),
)


COUNTS = PayloadSchema(
    name="CountsPayload",
    kind="object",
    description="Controller object, inventory, session, job, and database counts.",
    fields=(
        *_COUNT_FIELDS,
        _object(
            "inventories",
            description="Inventory counts keyed by inventory kind; always includes normal and smart.",
            additional_properties=_map_value(
                "InventoryKindCount", "integer", description="Number of inventories of this kind."
            ),
        ),
        _field("unified_job", "integer", "Unified jobs, excluding project syncs."),
        _field("active_host_count", "integer", "Number of active hosts."),
        _field("active_sessions", "integer", "Number of active sessions."),
        _field("active_user_sessions", "integer", "Number of active user sessions."),
        _field("active_anonymous_sessions", "integer", "Number of active anonymous sessions."),
        _field("running_jobs", "integer", "Number of running jobs."),
        _field("pending_jobs", "integer", "Number of pending jobs."),
        _field("database_connections", "integer", "Number of active database connections."),
    ),
)

CRED_TYPE_COUNTS = PayloadSchema(
    name="CredTypeCountsPayload",
    kind="object",
    description="Credential counts keyed by credential type ID.",
    key_field="credential_type_id",
    additional_properties=_map_value(
        "CredentialTypeCount",
        "object",
        (
            _field("name", "string", "Credential type name."),
            _field("credential_count", "integer", "Number of credentials of this type."),
            _field("managed", "boolean", "Whether the credential type is managed by the platform."),
        ),
        description="Credential count record.",
    ),
)

CRED_TYPE_COUNTS_ORG = PayloadSchema(
    name="CredTypeCountsOrgPayload",
    kind="array",
    description="Credential counts grouped by owning organization and credential type.",
    item_fields=(
        _field("organization_id", "integer", "Controller organization identifier."),
        _field("organization_name", "string", "Controller organization name."),
        _field("credential_type_id", "integer", "Credential type identifier.", nullable=False),
        _field("credential_type", "string", "Credential type name.", nullable=False),
        _field("managed", "boolean", "Whether the credential type is managed by the platform.", nullable=False),
        _field("credential_count", "integer", "Number of credentials of this type."),
    ),
)

HOST_METRIC_SUMMARY_MONTHLY = PayloadSchema(
    name="HostMetricSummaryMonthlyTablePayload",
    kind="array",
    description="Monthly host capacity and usage summaries.",
    item_fields=(
        _field("id", "integer", "Monthly host metric summary identifier.", nullable=False),
        _field("date", "date", "First day of the summarized month."),
        _field("license_capacity", "integer", "Licensed host capacity."),
        _field("license_consumed", "integer", "Consumed licensed host capacity."),
        _field("hosts_added", "integer", "Hosts added during the month."),
        _field("hosts_deleted", "integer", "Hosts deleted during the month."),
        _field("indirectly_managed_hosts", "integer", "Indirectly managed host count."),
    ),
)

INSTANCE_INFO = PayloadSchema(
    name="InstanceInfoPayload",
    kind="object",
    description="Controller instance topology and consumed capacity keyed by UUID.",
    key_field="uuid",
    additional_properties=_map_value(
        "InstanceInfoRecord",
        "object",
        (
            _field("uuid", "string", "Controller instance UUID."),
            _field("version", "string", "Controller instance version."),
            _field("capacity", "integer", "Total instance capacity."),
            _field("cpu", "string", 'CPU count, as a decimal string (for example "1.0").'),
            _field("memory", "integer", "Memory in bytes."),
            _field("managed_by_policy", "boolean", "Whether the instance is managed by policy."),
            _field("enabled", "boolean", "Whether the instance is enabled."),
            _field("consumed_capacity", "integer", "Capacity used by running and waiting jobs."),
            _field("remaining_capacity", "integer", "Capacity remaining for jobs."),
            _field("node_type", "string", "Controller node type."),
        ),
        description="Controller instance information record.",
    ),
)

INVENTORY_COUNTS = PayloadSchema(
    name="InventoryCountsPayload",
    kind="object",
    description="Inventory details keyed by inventory ID.",
    key_field="inventory_id",
    additional_properties=_map_value(
        "InventoryCount",
        "object",
        (
            _field("name", "string", "Inventory name."),
            _field("kind", "string", "Empty for normal inventories, smart for smart inventories."),
            _field("hosts", "integer", "Number of hosts in the inventory."),
            _field("sources", "integer", "Number of sources in the inventory."),
            _array(
                "source_list",
                _object(
                    "source",
                    (
                        _field("name", "string", "Inventory source name."),
                        _field("source", "string", "Inventory source type or URL."),
                        _field("num_hosts", "integer", "Number of hosts associated with the source."),
                    ),
                    "Inventory source record.",
                ),
                "Inventory sources and their host counts.",
            ),
        ),
        description="Inventory count record.",
    ),
)

INVENTORY_COUNTS_ORG = PayloadSchema(
    name="InventoryCountsOrgPayload",
    kind="array",
    description="Inventory, host, and source counts grouped by organization and inventory kind.",
    item_fields=(
        _field("organization_id", "integer", "Controller organization identifier."),
        _field("organization_name", "string", "Controller organization name."),
        _field("inventory_kind", "string", "Inventory kind.", nullable=False),
        _field("inventory_count", "integer", "Number of inventories of this kind."),
        _field("host_count", "integer", "Number of hosts in these inventories."),
        _field("source_count", "integer", "Number of sources in these inventories."),
    ),
)

ORG_COUNTS = PayloadSchema(
    name="OrgCountsPayload",
    kind="object",
    description="Organization user and team counts keyed by organization ID.",
    key_field="organization_id",
    additional_properties=_map_value(
        "OrganizationCount",
        "object",
        (
            _field("name", "string", "Organization name."),
            _field("users", "integer", "Number of users in the organization."),
            _field("teams", "integer", "Number of teams in the organization."),
        ),
        description="Organization count record.",
    ),
)

PROJECTS_BY_SCM_TYPE = PayloadSchema(
    name="ProjectsByScmTypePayload",
    kind="object",
    description="Project counts keyed by source-control type, with manual for projects without one.",
    key_field="scm_type",
    additional_properties=_map_value("ProjectScmTypeCount", "integer", description="Number of projects of this type."),
)

PROJECTS_BY_SCM_TYPE_ORG = PayloadSchema(
    name="ProjectsByScmTypeOrgPayload",
    kind="array",
    description="Project counts grouped by organization and source-control type.",
    item_fields=(
        _field("organization_id", "integer", "Controller organization identifier."),
        _field("organization_name", "string", "Controller organization name."),
        _field("scm_type", "string", "Source-control type.", nullable=False),
        _field("project_count", "integer", "Number of projects."),
    ),
)

UNIFIED_JOB_TEMPLATE = PayloadSchema(
    name="UnifiedJobTemplateTablePayload",
    kind="array",
    description="Unified job template identity, scheduling, and status records.",
    item_fields=(
        _field("id", "integer", "Unified job template identifier.", nullable=False),
        _field("polymorphic_ctype_id", "integer", "Django content type identifier for the concrete template."),
        _field("model", "string", "Concrete template type, for example job_template or project."),
        _field("execution_environment_image", "string", "Execution environment image used by the template."),
        _field("created", "datetime", "Template creation time."),
        _field("modified", "datetime", "Template last-modification time."),
        _field("created_by_id", "integer", "Identifier of the user who created the template."),
        _field("modified_by_id", "integer", "Identifier of the user who last modified the template."),
        _field("name", "string", "Unified job template name."),
        _field("current_job_id", "integer", "Currently running job identifier."),
        _field("last_job_id", "integer", "Most recent job identifier."),
        _field("last_job_failed", "boolean", "Whether the most recent job failed."),
        _field("last_job_run", "datetime", "Most recent job run time."),
        _field("next_job_run", "datetime", "Next scheduled job run time."),
        _field("next_schedule_id", "integer", "Next schedule identifier."),
        _field("status", "string", "Template status."),
    ),
)

WORKFLOW_JOB_TEMPLATE_NODE = PayloadSchema(
    name="WorkflowJobTemplateNodeTablePayload",
    kind="array",
    description="Workflow job template node definitions and edge relationships.",
    item_fields=(
        _field("id", "integer", "Workflow job template node identifier", nullable=False),
        _field("created", "datetime", "Workflow job template node creation time."),
        _field("modified", "datetime", "Workflow job template node last-modification time."),
        _field("unified_job_template_id", "integer", "Unified job template identifier."),
        _field("workflow_job_template_id", "integer", "Workflow job template identifier."),
        _field("inventory_id", "integer", "Controller inventory identifier."),
        *_EDGE_FIELDS,
        _field(
            "all_parents_must_converge",
            "boolean",
            "Whether all parent nodes must converge before this node runs.",
        ),
    ),
)

MAIN_HOST = PayloadSchema(
    name="MainHostPayload",
    kind="array",
    description="Enabled inventory hosts and selected host facts.",
    item_fields=(
        _field("host_name", "string", "Inventory host name.", nullable=False),
        _field("host_id", "integer", "Inventory host identifier."),
        _field("inventory_remote_id", "integer", "Controller inventory ID."),
        _field("inventory_name", "string", "Controller inventory name."),
        _field("organization_remote_id", "integer", "Controller organization ID."),
        _field("organization_name", "string", "Controller organization name."),
        _field("last_automation", "datetime", "Creation time of the host's most recent job."),
        _field("first_automation", "datetime", "First automation time recorded for this host."),
        _field("ansible_host_variable", "string", "ansible_host value from the host variables."),
        _object(
            "canonical_facts",
            (
                _field("ansible_product_serial", "string", "Product serial number reported by Ansible."),
                _field("ansible_machine_id", "string", "Machine identifier reported by Ansible."),
                _field("ansible_host", "string", "Canonical Ansible host value."),
                _field("host_name", "string", "Inventory host name."),
                _field("ansible_port", "integer", "Ansible connection port."),
            ),
            "Host identity facts used for deduplication.",
        ),
        _object(
            "facts",
            (
                _field("ansible_connection_variable", "string", "ansible_connection value from the host variables."),
                _field("ansible_virtualization_type", "string", "Virtualization type reported by Ansible."),
                _field("ansible_virtualization_role", "string", "Virtualization role reported by Ansible."),
                _field("ansible_system_vendor", "string", "System vendor reported by Ansible."),
                _field("ansible_product_name", "string", "Product name reported by Ansible."),
                _field("ansible_architecture", "string", "System architecture reported by Ansible."),
                _field("ansible_processor", "string", "Processor facts as JSON text."),
                _field("ansible_form_factor", "string", "System form factor reported by Ansible."),
                _field("ansible_bios_vendor", "string", "BIOS vendor reported by Ansible."),
                _field("ansible_bios_version", "string", "BIOS version reported by Ansible."),
                _field("ansible_board_serial", "string", "Board serial number reported by Ansible."),
            ),
            "Selected hardware and system facts.",
        ),
    ),
)

MAIN_HOSTMETRIC = PayloadSchema(
    name="MainHostmetricPayload",
    kind="array",
    description="Host automation, deletion, and identity metrics.",
    item_fields=(
        _field("hostname", "string", "Host name used as the host-metric key.", nullable=False),
        _field("host_id", "integer", "Matching inventory host ID, or 0 when the host no longer exists."),
        _field("first_automation", "datetime", "First automation time recorded for this host."),
        _field("last_automation", "datetime", "Creation time of the host's most recent job."),
        _field("automated_counter", "integer", "Number of automation runs for the host."),
        _field("deleted_counter", "integer", "Number of deletion events for the host."),
        _field("last_deleted", "datetime", "Time the host was last deleted."),
        _field("deleted", "boolean", "Whether the host has been deleted."),
        _field("id", "integer", "Host metric identifier"),
        _field("used_in_inventories", "integer", "Number of inventories using the host."),
        _field("ansible_product_serial", "string", "Product serial number reported by Ansible."),
        _field("ansible_machine_id", "string", "Machine identifier reported by Ansible."),
        _field("ansible_host_variable", "string", "ansible_host value from the host variables."),
        _field("ansible_connection_variable", "string", "ansible_connection value from the host variables."),
    ),
)

INDIRECT_MANAGED_NODES = PayloadSchema(
    name="IndirectManagedNodeAuditPayload",
    kind="array",
    description="Indirect managed node audit records for jobs finished in the window.",
    item_fields=(
        _field("id", "integer", "Audit record identifier", nullable=False),
        _field("created", "datetime", "Audit record creation time."),
        _field("host_name", "string", "Ansible name of the indirectly managed node."),
        _field("host_remote_id", "integer", "Controller host ID, when the node matches an inventory host."),
        _object("canonical_facts", description="Facts used for managed node deduplication; keys depend on the query."),
        _object("facts", description="Additional non-canonical facts about the managed node."),
        _array(
            "events",
            _field("module", "string", "Fully-qualified module name."),
            "Fully-qualified names of modules that ran against the node.",
        ),
        _field("task_runs", "integer", "How many times registered modules were invoked on the node."),
        _field("job_created", "datetime", "Creation time of the related job."),
        _field("job_remote_id", "integer", "Controller job ID."),
        _field("job_template_remote_id", "integer", "Controller unified job template ID."),
        _field("job_template_name", "string", "Unified job template name."),
        _field("inventory_remote_id", "integer", "Controller inventory ID."),
        _field("inventory_name", "string", "Controller inventory name."),
        _field("organization_remote_id", "integer", "Controller organization ID."),
        _field("organization_name", "string", "Controller organization name."),
        _field("project_remote_id", "integer", "Controller project ID."),
        _field("project_name", "string", "Controller project name."),
    ),
)


# Keyed by metrics-utility collector function name (the second half of the public name).
PAYLOAD_SCHEMAS = {
    "unified_jobs_dashboard": UNIFIED_JOBS_DASHBOARD,
    "unified_jobs": UNIFIED_JOBS,
    "unified_jobs_org": UNIFIED_JOBS_ORG,
    "job_host_summary_service": JOB_HOST_SUMMARY_SERVICE,
    "job_host_summary": JOB_HOST_SUMMARY,
    "credentials_service": CREDENTIALS,
    "credentials_service_org": CREDENTIALS_SERVICE_ORG,
    "main_jobevent_service": MAIN_JOBEVENT_SERVICE,
    "main_jobevent": MAIN_JOBEVENT,
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
    "cred_type_counts_org": CRED_TYPE_COUNTS_ORG,
    "host_metric_summary_monthly_table": HOST_METRIC_SUMMARY_MONTHLY,
    "instance_info": INSTANCE_INFO,
    "inventory_counts": INVENTORY_COUNTS,
    "inventory_counts_org": INVENTORY_COUNTS_ORG,
    "org_counts": ORG_COUNTS,
    "projects_by_scm_type": PROJECTS_BY_SCM_TYPE,
    "projects_by_scm_type_org": PROJECTS_BY_SCM_TYPE_ORG,
    "unified_job_template_table": UNIFIED_JOB_TEMPLATE,
    "workflow_job_template_node_table": WORKFLOW_JOB_TEMPLATE_NODE,
    "main_host": MAIN_HOST,
    "main_host_daily": MAIN_HOST,
    "main_hostmetric": MAIN_HOSTMETRIC,
    "main_indirectmanagednodeaudit": INDIRECT_MANAGED_NODES,
}
