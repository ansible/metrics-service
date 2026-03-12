"""
Unit tests for segment write key loading in metrics_service.settings.

Covers _decode_segment_key and _load_segment_write_key_from_file (single file, base64).
"""

import base64
from pathlib import Path
from unittest import mock

import pytest


@pytest.mark.unit
class TestDecodeSegmentKey:
    """Tests for _decode_segment_key."""

    def test_decodes_valid_base64_utf8(self):
        """Valid base64-encoded UTF-8 string is decoded."""
        from metrics_service.settings import _decode_segment_key

        raw = base64.b64encode(b"my-segment-write-key").decode("ascii")
        assert _decode_segment_key(raw) == "my-segment-write-key"

    def test_returns_raw_on_value_error(self):
        """Invalid base64 raises ValueError; raw string is returned."""
        from metrics_service.settings import _decode_segment_key

        assert _decode_segment_key("not-valid-base64!!!") == "not-valid-base64!!!"

    def test_empty_string_decodes_to_empty(self):
        """Empty string decodes to empty string (valid base64)."""
        from metrics_service.settings import _decode_segment_key

        raw = base64.b64encode(b"").decode("ascii")
        assert _decode_segment_key(raw) == ""


@pytest.mark.unit
class TestLoadSegmentWriteKeyFromFile:
    """Tests for _load_segment_write_key_from_file (single file, base64, and OSError)."""

    def test_path_does_not_exist_does_nothing(self):
        """When path does not exist, SEGMENT_WRITE_KEY is not set."""
        from metrics_service.settings import DYNACONF, _load_segment_write_key_from_file

        before = DYNACONF.get("SEGMENT_WRITE_KEY")
        nonexistent = Path("/nonexistent/segment-key-path")
        dynaconf_mock = mock.MagicMock()
        _load_segment_write_key_from_file(path=nonexistent, dynaconf_instance=dynaconf_mock)
        dynaconf_mock.set.assert_not_called()
        assert DYNACONF.get("SEGMENT_WRITE_KEY") == before

    def test_path_is_file_sets_key_from_decoded_content(self, tmp_path):
        """When path is a file, key is read and set (base64 decoded)."""
        from metrics_service.settings import _load_segment_write_key_from_file

        key_file = tmp_path / "segment-write-key"
        key_file.write_text(base64.b64encode(b"key-from-file").decode("ascii") + "\n")
        dynaconf_mock = mock.MagicMock()
        dynaconf_mock.get.return_value = None
        _load_segment_write_key_from_file(path=key_file, dynaconf_instance=dynaconf_mock)
        dynaconf_mock.set.assert_called_once_with("SEGMENT_WRITE_KEY", "key-from-file")

    def test_path_is_file_plain_text_passed_through(self, tmp_path):
        """When content is not valid base64, raw content is used (ValueError path)."""
        from metrics_service.settings import _load_segment_write_key_from_file

        key_file = tmp_path / "segment-write-key"
        key_file.write_text("plain-write-key")
        dynaconf_mock = mock.MagicMock()
        dynaconf_mock.get.return_value = None
        _load_segment_write_key_from_file(path=key_file, dynaconf_instance=dynaconf_mock)
        dynaconf_mock.set.assert_called_once_with("SEGMENT_WRITE_KEY", "plain-write-key")

    def test_path_is_dir_does_not_set(self, tmp_path):
        """When path is a directory (no single key file), SEGMENT_WRITE_KEY is not set."""
        from metrics_service.settings import _load_segment_write_key_from_file

        dynaconf_mock = mock.MagicMock()
        _load_segment_write_key_from_file(path=tmp_path, dynaconf_instance=dynaconf_mock)
        dynaconf_mock.set.assert_not_called()

    def test_path_is_file_empty_key_not_set(self, tmp_path):
        """When file content is empty after strip, key is not set."""
        from metrics_service.settings import _load_segment_write_key_from_file

        key_file = tmp_path / "segment-write-key"
        key_file.write_text("   \n  ")
        dynaconf_mock = mock.MagicMock()
        _load_segment_write_key_from_file(path=key_file, dynaconf_instance=dynaconf_mock)
        dynaconf_mock.set.assert_not_called()

    def test_os_error_suppressed(self, tmp_path):
        """OSError when reading file is suppressed and key is not set."""
        from metrics_service.settings import _load_segment_write_key_from_file

        dynaconf_mock = mock.MagicMock()
        path_mock = mock.MagicMock(spec=Path)
        path_mock.exists.return_value = True
        path_mock.is_file.return_value = True
        path_mock.read_text.side_effect = OSError
        _load_segment_write_key_from_file(path=path_mock, dynaconf_instance=dynaconf_mock)
        dynaconf_mock.set.assert_not_called()
