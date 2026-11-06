"""sosreport plugin for Ansible Automation Platform Metrics Service.

Runs the read-only ``metrics-service support-bundle --dry-run`` manifest and
collects the settings override *configuration files*. Logging in metrics-service
goes to stdout rather than a file-based log directory, so
``/var/log/metrics-service`` is deliberately not collected -- the platform
gathers stdout separately.

Only configuration files that dynaconf loads from the override directory are
copied (``settings.*``, ``*.yaml``/``*.yml``/``*.toml``/``*.json``/``*.conf``/
``*.ini`` and ``.env``); everything else in the directory is left alone and key
material is forbidden outright. Their secret values are scrubbed in
``postproc`` before the report is finalised.

Install by copying this file into ``sos/report/plugins/`` on the target host.
The plugin is not shipped in the metrics-service wheel (pyproject only packages
``metrics_service*`` and ``apps*``); distribution into the container/operator
image is an OS packaging step.
"""

try:
    from sos.plugins import Plugin, RedHatPlugin
except ImportError:
    from sos.report.plugins import Plugin, RedHatPlugin

SOSREPORT_METRICS_SERVICE_CONFIG_DIR = "/etc/ansible-automation-platform/metrics_service/"

SOSREPORT_METRICS_SERVICE_COMMANDS = [
    "metrics-service support-bundle --dry-run",
    "pip freeze",
]

#: Explicit allow-list: dynaconf override files only, never the whole directory.
SOSREPORT_METRICS_SERVICE_FILES = [
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}.env",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}settings.*",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}*.yaml",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}*.yml",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}*.toml",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}*.json",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}*.conf",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}*.ini",
]

#: Never collect key material, even if it lives in the override directory.
SOSREPORT_METRICS_SERVICE_FORBIDDEN = [
    "/etc/ansible-automation-platform/metrics/segment-write-key",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}*.key",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}*.pem",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}*secret*",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}*credential*",
    f"{SOSREPORT_METRICS_SERVICE_CONFIG_DIR}*token*",
]

# Match any ``key=value`` or ``key: value`` pair whose *name* looks secret,
# quoted or unquoted, in .env / YAML / INI / TOML override files:
#   SECRET_KEY='...', SECRET_KEY = "...", SECRET_KEY=abc, password: abc,
#   AUTH_TOKEN=abc, API_KEY=abc, DB_PASSWORD=abc, PRIVATE_KEY=abc
SECRET_PATTERN = (  # noqa: S105
    r"(?i)((?:[A-Za-z0-9_.\-]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API[_-]?KEY|[_-]KEY|CREDENTIAL|PRIVATE[_-]?KEY|AUTH)"  # noqa: S105
    r"[A-Za-z0-9_.\-]*)\s*[=:]\s*)[^\n]*"  # noqa: S105
)
SECRET_REPLACEMENT = r"\g<1>********"  # noqa: S105


class MetricsService(Plugin, RedHatPlugin):
    """Collect Ansible Automation Platform Metrics Service information."""

    plugin_name = "metrics_service"
    short_desc = "Ansible Automation Platform Metrics Service information"

    def setup(self):
        for path in SOSREPORT_METRICS_SERVICE_FILES:
            self.add_copy_spec(path)
        for path in SOSREPORT_METRICS_SERVICE_FORBIDDEN:
            self.add_forbidden_path(path)
        self.add_cmd_output(SOSREPORT_METRICS_SERVICE_COMMANDS)

    def postproc(self):
        self.do_path_regex_sub(
            SOSREPORT_METRICS_SERVICE_CONFIG_DIR,
            SECRET_PATTERN,
            SECRET_REPLACEMENT,
        )
