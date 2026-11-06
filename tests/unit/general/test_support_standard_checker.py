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
        payload = {k: v for k, v in self.COMPLETE.items() if k != "running"}
        results = _as_dict(checker._evaluate_diagnostics_payload(payload))
        assert results["running"] == "FAIL"

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
