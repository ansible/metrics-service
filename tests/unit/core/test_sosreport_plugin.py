"""Tests for the sosreport plugin's secret scrubbing.

The plugin is not shipped in the wheel and sos is not a test dependency, so the
module is loaded with a stub ``sos.report.plugins``. What matters here is the
scrub pattern and the collection allow-list, not the sos machinery.
"""

import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PLUGIN_PATH = Path(__file__).resolve().parents[3] / "tools" / "sosreport" / "metrics_service.py"


def _load_plugin():
    sos_module = types.ModuleType("sos")
    sos_report = types.ModuleType("sos.report")
    sos_plugins = types.ModuleType("sos.report.plugins")
    sos_plugins.Plugin = type("Plugin", (), {})
    sos_plugins.RedHatPlugin = type("RedHatPlugin", (), {})
    sos_module.report = sos_report
    sos_report.plugins = sos_plugins
    stubs = {"sos": sos_module, "sos.report": sos_report, "sos.report.plugins": sos_plugins}

    original = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("sosreport_metrics_service", PLUGIN_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, module in original.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


@pytest.fixture(scope="module")
def plugin():
    return _load_plugin()


def _scrub(plugin, content: str) -> str:
    return re.sub(plugin.SECRET_PATTERN, plugin.SECRET_REPLACEMENT, content, flags=re.MULTILINE)


ENV_CONTENT = """\
SECRET_KEY='quoted-secret'
DATABASES__default__PASSWORD = "db-quoted-secret"
SEGMENT_WRITE_KEY=segment-unquoted-secret
AUTH_TOKEN=auth-token-secret
API_KEY=api-key-secret
DB_PASSWORD=db-password-secret
PRIVATE_KEY=private-key-secret
TASK_TIMEOUT=3600
"""

YAML_CONTENT = """\
secret_key: yaml-secret
resource_server__secret_key: dab-yaml-secret
databases:
  default:
    password: yaml-db-password
    host: db.example.com
"""

EXPECTED_SECRETS = {
    "env": (
        "quoted-secret",
        "db-quoted-secret",
        "segment-unquoted-secret",
        "auth-token-secret",
        "api-key-secret",
        "db-password-secret",
        "private-key-secret",
    ),
    "yaml": ("yaml-secret", "dab-yaml-secret", "yaml-db-password"),
}


@pytest.mark.parametrize("fmt,content", [("env", ENV_CONTENT), ("yaml", YAML_CONTENT)])
def test_secret_values_do_not_survive_the_scrubber(plugin, fmt, content):
    scrubbed = _scrub(plugin, content)

    for secret in EXPECTED_SECRETS[fmt]:
        assert secret not in scrubbed
    assert "********" in scrubbed


def test_scrubber_keeps_non_secret_settings(plugin):
    scrubbed = _scrub(plugin, ENV_CONTENT + YAML_CONTENT)

    assert "TASK_TIMEOUT=3600" in scrubbed
    assert "host: db.example.com" in scrubbed


def test_collection_uses_an_allow_list_not_the_whole_directory(plugin):
    """Copy specs must be config files; never the bare override directory."""
    assert plugin.SOSREPORT_METRICS_SERVICE_FILES
    for spec in plugin.SOSREPORT_METRICS_SERVICE_FILES:
        assert spec != plugin.SOSREPORT_METRICS_SERVICE_CONFIG_DIR
        assert spec.startswith(plugin.SOSREPORT_METRICS_SERVICE_CONFIG_DIR)
    joined = " ".join(plugin.SOSREPORT_METRICS_SERVICE_FILES)
    for pattern in (".env", "*.yaml", "*.yml", "*.toml", "*.json"):
        assert pattern in joined


def test_key_material_is_forbidden(plugin):
    forbidden = " ".join(plugin.SOSREPORT_METRICS_SERVICE_FORBIDDEN)

    assert "/etc/ansible-automation-platform/metrics/segment-write-key" in forbidden
    for pattern in ("*.key", "*.pem", "*secret*", "*credential*", "*token*"):
        assert pattern in forbidden
