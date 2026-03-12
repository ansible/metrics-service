"""
Unit tests for segment write key loading in metrics_service.settings.

Covers _load_segment_write_key_from_file (single file, plaintext).
"""

from pathlib import Path
from unittest import mock

import pytest


@pytest.mark.unit
class TestLoadSegmentWriteKeyFromFile:
    """Tests for _load_segment_write_key_from_file (single plaintext file)."""

    def test_path_does_not_exist_does_nothing(self):
        """When path does not exist, SEGMENT_WRITE_KEY is not set."""
        from metrics_service.settings import DYNACONF, _load_segment_write_key_from_file

        before = DYNACONF.get("SEGMENT_WRITE_KEY")
        nonexistent = Path("/nonexistent/segment-key-path")
        dynaconf_mock = mock.MagicMock()
        _load_segment_write_key_from_file(path=nonexistent, dynaconf_instance=dynaconf_mock)
        dynaconf_mock.set.assert_not_called()
        assert DYNACONF.get("SEGMENT_WRITE_KEY") == before

    def test_path_is_file_sets_key_from_plaintext(self, tmp_path):
        """When path is a file, the raw plaintext key is read and set as-is."""
        from metrics_service.settings import _load_segment_write_key_from_file

        key_file = tmp_path / "segment-write-key"
        key_file.write_text("my-plaintext-write-key\n")
        dynaconf_mock = mock.MagicMock()
        dynaconf_mock.get.return_value = None
        _load_segment_write_key_from_file(path=key_file, dynaconf_instance=dynaconf_mock)
        dynaconf_mock.set.assert_called_once_with("SEGMENT_WRITE_KEY", "my-plaintext-write-key")

    def test_path_is_file_whitespace_stripped(self, tmp_path):
        """Leading/trailing whitespace and newlines are stripped from the key."""
        from metrics_service.settings import _load_segment_write_key_from_file

        key_file = tmp_path / "segment-write-key"
        key_file.write_text("  key-with-spaces  \n")
        dynaconf_mock = mock.MagicMock()
        dynaconf_mock.get.return_value = None
        _load_segment_write_key_from_file(path=key_file, dynaconf_instance=dynaconf_mock)
        dynaconf_mock.set.assert_called_once_with("SEGMENT_WRITE_KEY", "key-with-spaces")

    def test_path_is_dir_does_not_set(self, tmp_path):
        """When path is a directory (not a file), SEGMENT_WRITE_KEY is not set."""
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
