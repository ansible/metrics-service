"""Unit tests for the Emerging Services conformance checker.

The checker is a standalone stdlib script, so it is loaded by path rather than
imported as a package module.
"""

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

CHECKER_PATH = Path(__file__).resolve().parents[3] / "tools" / "emerging-services" / "check_support_standard.py"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("check_support_standard", CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _as_dict(results):
    return {result.check: result.result for result in results}


class TestHealthPayloadChecks:
    """ES-SUP-1 payload validation (offline, no HTTP)."""

    def test_good_payload_passes(self, checker):
        results = _as_dict(checker._evaluate_health_payload({"status": "good", "checks": {"database": "ok"}}))
        assert results["JSON contract"] == "PASS"

    def test_bad_status_vocabulary_fails(self, checker):
        results = _as_dict(checker._evaluate_health_payload({"status": "healthy", "checks": {"database": "ok"}}))
        assert results["JSON contract"] == "FAIL"

    def test_empty_checks_fails(self, checker):
        results = _as_dict(checker._evaluate_health_payload({"status": "good", "checks": {}}))
        assert results["JSON contract"] == "FAIL"

    def test_non_dict_fails(self, checker):
        results = _as_dict(checker._evaluate_health_payload("not-a-dict"))
        assert results["JSON contract"] == "FAIL"

    def test_results_are_tagged_with_requirement(self, checker):
        results = checker._evaluate_health_payload({"status": "good", "checks": {"database": "ok"}})
        assert {result.requirement for result in results} == {"ES-SUP-1"}
        assert all(result.required for result in results)


class TestDiagnosticsPayloadChecks:
    """ES-SUP-3 validates all five mandated concepts."""

    COMPLETE = {
        "running": [{"name": "collect", "elapsed_seconds": 3}],
        "stuck_tasks": [],
        "last_success": {"collect": "2026-11-06T00:00:00Z"},
        "failures_last_24h": {},
        "queue_depth": 0,
    }

    def test_complete_payload_passes_all_concepts(self, checker):
        results = checker._evaluate_diagnostics_payload(self.COMPLETE)
        assert [r.check for r in results] == ["running", "stuck", "last_success", "failures", "queue_depth"]
        assert {r.result for r in results} == {"PASS"}

    def test_running_jobs_concept_is_mandated(self, checker):
        payload = {k: v for k, v in self.COMPLETE.items() if k not in ("running", "stuck_tasks")}
        payload["queue_depth"] = {"queues": []}
        results = _as_dict(checker._evaluate_diagnostics_payload(payload))
        assert results["running"] == "FAIL"

    def test_running_is_evidenced_by_the_stuck_task_scan(self, checker):
        """AAP-79585 exposes running+elapsed through ``stuck_tasks``, not ``running``."""
        payload = {k: v for k, v in self.COMPLETE.items() if k != "running"}
        assert _as_dict(checker._evaluate_diagnostics_payload(payload))["running"] == "PASS"

    def test_running_is_evidenced_by_live_worker_state(self, checker):
        payload = {"stuck_tasks": [], "queue_depth": {"dispatcherd_workers": [{"worker-0": {"status": "idle"}}]}}
        assert _as_dict(checker._evaluate_diagnostics_payload(payload))["running"] == "PASS"

    def test_real_reference_payload_passes_every_concept(self, checker):
        """Verbatim shape of ``metrics-service tasks diagnose --format json`` (AAP-79585).

        There is no ``running`` key and the failure section is
        ``failures_in_window``: the two names the checker originally rejected.
        """
        payload = {
            "schema_version": 2,
            "generated_at": "2026-11-06T13:40:00+00:00",
            "task_timeout_seconds": 3600,
            "window_hours": 24,
            "stuck_tasks": [
                {
                    "task_id": 1142,
                    "name": "support-demo-stuck",
                    "function_name": "collect_hourly_metrics",
                    "started_at": "2026-11-06T11:34:27.129894+00:00",
                    "duration_seconds": 7563.640496,
                    "attempts": 1,
                    "worker_id": None,
                    "execution_id": None,
                    "reported_by": [],
                }
            ],
            "last_success": [
                {"function_name": "collect_hourly_metrics", "last_success_at": "2026-11-06T12:00:00+00:00"}
            ],
            "failures_in_window": [
                {
                    "function_name": "collect_hourly_metrics",
                    "failure_count": 3,
                    "legacy_task_failures": 0,
                    "last_failure_at": "2026-11-06T12:37:40.361912+00:00",
                    "last_error": "OperationalError: could not connect to server",
                }
            ],
            "queue_depth": {
                "live_available": False,
                "error": "disabled",
                "warnings": [],
                "query_errors": {},
                "queues": [{"queue": "metrics", "pending_in_db": 0, "queued_live": 0}],
                "dispatcherd_workers": [],
                "dispatcherd_producers": [],
            },
        }
        results = checker._evaluate_diagnostics_payload(payload)
        assert [r.check for r in results] == ["running", "stuck", "last_success", "failures", "queue_depth"]
        assert {r.result for r in results} == {"PASS"}

    def test_failures_accepts_the_historical_window_name(self, checker):
        results = _as_dict(checker._evaluate_diagnostics_payload({"failures_last_24h": []}))
        assert results["failures"] == "PASS"

    def test_failures_prefix_glob_matches_a_versioned_section(self, checker):
        results = _as_dict(checker._evaluate_diagnostics_payload({"failures_in_window_seconds": []}))
        assert results["failures"] == "PASS"

    def test_empty_sections_are_present_evidence(self, checker):
        """Zero running/failed jobs is a legitimate result, not missing coverage."""
        payload = {"stuck_tasks": [], "last_success": [], "failures_in_window": [], "queue_depth": {"queues": []}}
        assert {r.result for r in checker._evaluate_diagnostics_payload(payload)} == {"PASS"}

    def test_missing_keys_fail(self, checker):
        results = _as_dict(checker._evaluate_diagnostics_payload({"stuck_tasks": []}))
        assert results["stuck"] == "PASS"
        assert results["queue_depth"] == "FAIL"

    def test_custom_key_names_via_map(self, checker):
        """The standard allows other services to use different key names."""
        payload = {
            "jobs": {"running": [], "stuck": []},
            "last_ok": {},
            "failure_counts_168h": {},
            "backlog": 4,
        }
        key_map = checker.diagnostics_key_map(
            {
                "running": ["jobs.running"],
                "stuck": ["jobs.stuck"],
                "last_success": ["last_ok"],
                "failures": ["failure_counts_{window}h"],
                "queue_depth": ["backlog"],
            }
        )
        results = _as_dict(checker._evaluate_diagnostics_payload(payload, key_map, window_hours=168))
        assert set(results.values()) == {"PASS"}

    def test_failure_window_is_substituted(self, checker):
        key_map = checker.diagnostics_key_map({"failures": ["failures_last_{window}h"]})
        assert (
            _as_dict(checker._evaluate_diagnostics_payload({"failures_last_168h": {}}, key_map, 168))["failures"]
            == "PASS"
        )
        assert (
            _as_dict(checker._evaluate_diagnostics_payload({"failures_last_24h": {}}, key_map, 168))["failures"]
            == "FAIL"
        )

    def test_invalid_concept_in_map_raises(self, checker):
        with pytest.raises(ValueError, match="unknown diagnostics concept"):
            checker.diagnostics_key_map({"not_a_concept": ["x"]})

    def test_empty_override_raises(self, checker):
        with pytest.raises(ValueError, match="non-empty list"):
            checker.diagnostics_key_map({"running": []})


class TestSecretScan:
    """ES-SUP-4 redaction heuristics."""

    @pytest.mark.parametrize(
        "text",
        [
            '{"DB_PASSWORD": "hunter2"}',
            "token=abc123",
            "AWS_SECRET_ACCESS_KEY: wJalrXUtnFEMI/K7MDENG",
            "api_key = 1234567890",
            "postgresql://metrics_service:hunter2@db.prod:5432/metrics",
        ],
    )
    def test_unredacted_secret_is_detected(self, checker, text):
        assert checker.scan_text_for_secrets(text)

    @pytest.mark.parametrize(
        "text",
        [
            '{"DB_PASSWORD": "<redacted>"}',
            '{"api_token": "***"}',
            '{"secret_key": ""}',
            '{"admin_password": null}',
            '{"db_password": "$METRICS_SERVICE_DB_PASSWORD"}',
            '{"database": "ok", "status": "good"}',
            '{"monkey": "banana"}',
        ],
    )
    def test_redacted_or_benign_values_pass(self, checker, text):
        assert checker.scan_text_for_secrets(text) == []

    @pytest.mark.parametrize(
        "text",
        [
            "AKIAIOSFODNN7EXAMPLE",
            "ghp_" + "a" * 36,
            "-----BEGIN RSA PRIVATE KEY-----",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        ],
    )
    def test_known_token_patterns_are_detected(self, checker, text):
        assert checker.scan_text_for_secrets(text)

    def test_findings_never_include_the_secret(self, checker):
        hits = checker.scan_text_for_secrets('{"DB_PASSWORD": "hunter2"}')
        assert hits and "hunter2" not in " ".join(hits)

    @pytest.mark.parametrize(
        "text",
        [
            # AAP-79583 allow-list: counters, budgets and durations are metadata.
            '{"redacted_key_count": 9}',
            '{"key_count": 12, "api_key_count": 12}',
            '{"token_budget": 4096, "secret_scan_duration_ms": 12}',
            '{"password_policy": "min_length_12", "payload_bytes": 2048}',
            # Configuration shapes that carry no credential value.
            '{"AUTH_USER_MODEL": "django.contrib.auth.models.User"}',
            '{"LOGGING_AUTH_LOGGER": "ansible_base.jwt_consumer.common.auth"}',
            '{"DB_PASSWORD": "$METRICS_SERVICE_DB_PASSWORD"}',
            '{"AUTH_MODE": "enabled"}',
        ],
    )
    def test_metadata_and_configuration_values_pass(self, checker, text):
        assert checker.scan_text_for_secrets(text) == []

    @pytest.mark.parametrize(
        "key,value",
        [
            ("api_key", "s3cr3t-value"),
            ("db_password", "hunter2"),
            ("client_secret", "abcd1234efgh"),
            ("auth_token", "0123456789abcdef"),
        ],
    )
    def test_allow_list_does_not_exempt_real_credentials(self, checker, key, value):
        """Narrow allow-list: a bare ``api_key``/``auth_token`` is still a secret."""
        assert checker.scan_text_for_secrets(json.dumps({key: value}))

    @pytest.mark.parametrize("value", ["HUNTER2", "ABCD1234", "PRODKEY99"])
    def test_bare_uppercase_values_are_not_treated_as_env_var_names(self, checker, value):
        """Only an underscored ENV-VAR *reference* is exempt from the key-name rule."""
        assert checker.scan_text_for_secrets(json.dumps({"DB_PASSWORD": value}))

    def test_underscored_env_var_reference_stays_benign(self, checker):
        assert checker.scan_text_for_secrets('{"DB_PASSWORD": "METRICS_SERVICE_DB_PASSWORD"}') == []

    @pytest.mark.parametrize(
        "text",
        [
            "Authorization: Bearer abcdef1234567890",
            '{"Authorization": "Basic dXNlcjpwYXNzd29yZA=="}',
            "authorization = token 0123456789abcdef",
        ],
    )
    def test_authorization_headers_are_detected(self, checker, text):
        assert "credential pattern 'authorization-header'" in checker.scan_text_for_secrets(text)

    def test_redacted_authorization_header_passes(self, checker):
        """AAP-79583 rewrites the credential, keeping the scheme word."""
        assert checker.scan_text_for_secrets("Authorization: Bearer **REDACTED**") == []


class TestDocsCheck:
    """ES-SUP-5 documentation check."""

    def test_missing_path_is_skip(self, checker):
        assert {r.result for r in checker.check_docs("")} == {"SKIP"}

    def test_nonexistent_file_fails(self, checker, tmp_path):
        assert checker.check_docs(str(tmp_path / "nope.md"))[0].result == "FAIL"

    def test_guide_covering_all_requirements_passes(self, checker, tmp_path):
        guide = tmp_path / "support-tooling.md"
        guide.write_text("# Guide\nES-SUP-1\nES-SUP-2\nES-SUP-3\n")
        assert {r.result for r in checker.check_docs(str(guide))} == {"PASS"}

    def test_guide_missing_a_requirement_fails(self, checker, tmp_path):
        guide = tmp_path / "support-tooling.md"
        guide.write_text("# Guide\nES-SUP-1\n")
        assert _as_dict(checker.check_docs(str(guide)))["guide coverage"] == "FAIL"

    def test_guide_linking_the_standard_passes(self, checker, tmp_path):
        """AAP-79586 maps tools to the standard by name and links it (no ES-SUP ids)."""
        guide = tmp_path / "support-tooling.md"
        guide.write_text(
            "# Support and Diagnostics\n\n"
            "## Emerging Services conformance\n\n"
            "These tools satisfy the health-endpoint, log-level, task-state and\n"
            "diagnostic-bundle rules of the\n"
            "[Emerging Services support standard](emerging-services-support-standard.md).\n"
        )
        assert {r.result for r in checker.check_docs(str(guide))} == {"PASS"}

    def test_standard_link_without_the_section_fails(self, checker, tmp_path):
        guide = tmp_path / "support-tooling.md"
        guide.write_text("# Guide\nSee emerging-services-support-standard.md\n")
        assert _as_dict(checker.check_docs(str(guide)))["guide coverage"] == "FAIL"

    def test_section_without_the_standard_link_fails(self, checker, tmp_path):
        guide = tmp_path / "support-tooling.md"
        guide.write_text("# Guide\n## Emerging Services conformance\nwe comply\n")
        assert _as_dict(checker.check_docs(str(guide)))["guide coverage"] == "FAIL"


class TestExitCodeContract:
    """Required-but-unverified requirements must never exit 0."""

    def _results(self, checker, specs):
        return [checker.Result(req, check, status, "detail") for req, check, status in specs]

    def test_all_required_pass(self, checker):
        results = self._results(
            checker,
            [
                ("ES-SUP-1", "endpoint", "PASS"),
                ("ES-SUP-2", "docs", "PASS"),
                ("ES-SUP-3", "command", "PASS"),
                ("ES-SUP-5", "guide", "PASS"),
                ("ES-SUP-4", "bundle", "SKIP"),
            ],
        )
        assert checker.exit_code(results) == 0

    def test_any_failure_wins(self, checker):
        results = self._results(checker, [("ES-SUP-1", "endpoint", "FAIL")])
        assert checker.exit_code(results) == 1

    @pytest.mark.parametrize("status", ["SKIP", "MANUAL"])
    def test_required_skip_or_manual_is_incomplete(self, checker, status):
        results = self._results(
            checker,
            [
                ("ES-SUP-1", "endpoint", "PASS"),
                ("ES-SUP-2", "docs", "PASS"),
                ("ES-SUP-3", "command", status),
                ("ES-SUP-5", "guide", "PASS"),
            ],
        )
        assert checker.exit_code(results) == 3

    def test_missing_required_requirement_is_incomplete(self, checker):
        results = self._results(checker, [("ES-SUP-1", "endpoint", "PASS")])
        assert checker.exit_code(results) == 3

    def test_mixed_pass_and_skip_for_same_requirement_is_incomplete(self, checker):
        results = self._results(
            checker,
            [
                ("ES-SUP-1", "endpoint", "PASS"),
                ("ES-SUP-2", "docs", "PASS"),
                ("ES-SUP-2", "observed", "MANUAL"),
                ("ES-SUP-3", "command", "PASS"),
                ("ES-SUP-5", "guide", "PASS"),
            ],
        )
        assert checker.exit_code(results) == 3


class TestLogLevelContract:
    """ES-SUP-2 must never PASS from the caller's environment."""

    def test_no_env_read(self, checker, monkeypatch, tmp_path):
        monkeypatch.setenv("SERVICE_LOG_LEVEL", "DEBUG")
        results = checker.check_log_level_contract("SERVICE_LOG_LEVEL", "", "")
        # Documented variable: SKIP (no --docs-path). Effect: MANUAL (needs evidence).
        # Crucially: nothing is PASS, even though the caller's env says DEBUG.
        assert {r.result for r in results} == {"SKIP", "MANUAL"}
        assert not any(r.result == "PASS" for r in results)

    def test_observed_level_is_reported(self, checker):
        results = _as_dict(checker.check_log_level_contract("SERVICE_LOG_LEVEL", "debug", ""))
        assert results["log level effect observed"] == "PASS"

    def test_invalid_observed_level_fails(self, checker):
        results = _as_dict(checker.check_log_level_contract("SERVICE_LOG_LEVEL", "LOUD", ""))
        assert results["log level effect observed"] == "FAIL"

    def test_documented_variable_passes_with_docs(self, checker, tmp_path):
        docs = tmp_path / "guide.md"
        docs.write_text("Set METRICS_SERVICE_LOG_LEVEL (default INFO).")
        results = _as_dict(checker.check_log_level_contract("METRICS_SERVICE_LOG_LEVEL", "", str(docs)))
        assert results["log level env var documented"] == "PASS"

    def test_undocumented_variable_fails(self, checker, tmp_path):
        docs = tmp_path / "guide.md"
        docs.write_text("no mention here")
        results = _as_dict(checker.check_log_level_contract("METRICS_SERVICE_LOG_LEVEL", "", str(docs)))
        assert results["log level env var documented"] == "FAIL"


class TestBundleRedaction:
    """ES-SUP-4 scans the produced bundle, not just the exit code."""

    def test_exit_zero_with_clean_bundle_passes(self, checker, tmp_path):
        bundle = tmp_path / "bundle.txt"
        bundle.write_text("status: ok\nqueue_depth: 0\n")
        command = f"cat {bundle}"
        results = _as_dict(checker.check_bundle_command(command, str(bundle)))
        assert results["diagnostic bundle"] == "PASS"
        assert results["bundle redaction"] == "PASS"

    def test_exit_zero_with_leaked_secret_fails(self, checker, tmp_path):
        bundle = tmp_path / "bundle.txt"
        bundle.write_text('{"DB_PASSWORD": "hunter2"}\n')
        command = f"cat {bundle}"
        results = _as_dict(checker.check_bundle_command(command, str(bundle)))
        assert results["diagnostic bundle"] == "PASS"
        assert results["bundle redaction"] == "FAIL"

    def test_without_bundle_path_is_manual(self, checker):
        results = _as_dict(checker.check_bundle_command("true"))
        assert results["diagnostic bundle"] == "PASS"
        assert results["bundle redaction"] == "MANUAL"

    def test_failing_command_fails(self, checker):
        assert _as_dict(checker.check_bundle_command("false"))["diagnostic bundle"] == "FAIL"


class TestJsonContract:
    """The --json shape is frozen so other teams can consume it."""

    def test_json_output_shape(self, checker, capsys, tmp_path):
        code = checker.main(["--base-url", "http://127.0.0.1:1", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["version"] == 1
        assert payload["exit_code"] == code
        assert payload["overall"] in {"pass", "fail", "incomplete"}
        assert {"requirement", "check", "result", "detail", "required"} <= set(payload["results"][0])
