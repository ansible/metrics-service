"""sosreport plugin for Ansible Automation Platform Metrics Service.

Runs the read-only ``metrics-service support-bundle --dry-run`` manifest and
collects settings overrides. Logging in metrics-service goes to stdout rather
than a file-based log directory, so ``/var/log/metrics-service`` is deliberately
not collected -- the platform gathers stdout separately.

Install by copying this file into ``sos/report/plugins/`` on the target host.
The plugin is not shipped in the metrics-service wheel (pyproject only packages
``metrics_service*`` and ``apps*``); distribution into the container/operator
image is an OS packaging step.
"""

try:
    from sos.plugins import Plugin, RedHatPlugin
except ImportError:
    from sos.report.plugins import Plugin, RedHatPlugin

SOSREPORT_METRICS_SERVICE_COMMANDS = [
    "metrics-service support-bundle --dry-run",
    "pip freeze",
]

SOSREPORT_METRICS_SERVICE_DIRS = [
    "/etc/ansible-automation-platform/metrics_service/",
]

SOSREPORT_METRICS_SERVICE_FORBIDDEN = [
    "/etc/ansible-automation-platform/metrics/segment-write-key",
]

# Match Python/INI-style assignments regardless of spacing and quote style:
#   KEY='...', KEY = "...", KEY = '''...'''
SECRET_PATTERN = (
    r"((?:SECRET_KEY|PASSWORD|RESOURCE_SERVER__SECRET_KEY|SEGMENT_WRITE_KEY)\s*=\s*)"  # noqa: S105
    r"((?:'''|\"\"\"|'|\")[^\n]*?(?:'''|\"\"\"|'|\"))"
)
SECRET_REPLACEMENT = r"\g<1>********"  # noqa: S105


class MetricsService(Plugin, RedHatPlugin):
    """Collect Ansible Automation Platform Metrics Service information."""

    plugin_name = "metrics_service"
    short_desc = "Ansible Automation Platform Metrics Service information"

    def setup(self):
        for path in SOSREPORT_METRICS_SERVICE_DIRS:
            self.add_copy_spec(path)
        for path in SOSREPORT_METRICS_SERVICE_FORBIDDEN:
            self.add_forbidden_path(path)
        self.add_cmd_output(SOSREPORT_METRICS_SERVICE_COMMANDS)

    def postproc(self):
        self.do_path_regex_sub(
            "/etc/ansible-automation-platform/metrics_service/",
            SECRET_PATTERN,
            SECRET_REPLACEMENT,
        )
