"""Unit tests for the Emerging Services conformance checker's pure functions."""

import importlib.util
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
    return {name: result for name, result, _ in results}


class TestHealthPayloadChecks:
    """ES-SUP-1 payload validation (offline, no HTTP)."""

    def test_good_payload_passes(self, checker):
        results = _as_dict(checker._evaluate_health_payload({"status": "good", "checks": {"database": "ok"}}))
        assert results["ES-SUP-1 JSON contract"] == "PASS"

    def test_bad_status_vocabulary_fails(self, checker):
        results = _as_dict(checker._evaluate_health_payload({"status": "healthy", "checks": {"database": "ok"}}))
        assert results["ES-SUP-1 JSON contract"] == "FAIL"

    def test_empty_checks_fails(self, checker):
        results = _as_dict(checker._evaluate_health_payload({"status": "good", "checks": {}}))
        assert results["ES-SUP-1 JSON contract"] == "FAIL"

    def test_non_dict_fails(self, checker):
        results = _as_dict(checker._evaluate_health_payload("not-a-dict"))
        assert results["ES-SUP-1 JSON contract"] == "FAIL"


class TestDiagnosticsPayloadChecks:
    """ES-SUP-3 JSON validation."""

    def test_complete_payload_passes(self, checker):
        payload = {"stuck_tasks": [], "last_success": {}, "failures_last_24h": {}, "queue_depth": 0}
        results = _as_dict(checker._evaluate_diagnostics_payload(payload))
        assert results["ES-SUP-3 diagnostics JSON"] == "PASS"

    def test_missing_keys_fail(self, checker):
        results = _as_dict(checker._evaluate_diagnostics_payload({"stuck_tasks": []}))
        assert results["ES-SUP-3 diagnostics JSON"] == "FAIL"
