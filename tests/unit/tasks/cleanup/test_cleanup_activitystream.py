"""
Unit tests for apps/tasks/cleanup/cleanup_activitystream.py

Tests cover:
- Dry-run mode (count without deleting)
- Deletion of entries older than the threshold
- Preservation of recent entries
- Default 7-day threshold
- Custom days_old parameter
- Cutoff date returned in result
- Error result returned for invalid days_old values
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.tasks.cleanup.cleanup_activitystream import cleanup_activitystream


def _create_entry(days_ago: int):
    """Create an ActivityStream Entry with a backdated created timestamp."""
    from ansible_base.activitystream.models import Entry
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.first()
    entry = Entry.objects.create(
        content_type=ct,
        object_id="1",
        operation="create",
    )
    # Backdate the immutable created field via queryset update
    Entry.objects.filter(pk=entry.pk).update(created=timezone.now() - timedelta(days=days_ago))
    return Entry.objects.get(pk=entry.pk)


@pytest.mark.unit
@pytest.mark.django_db
class TestCleanupActivityStream:
    """Test the standalone cleanup_activitystream task."""

    def test_dry_run_counts_old_entries_without_deleting(self):
        """dry_run=True reports old entries without deleting them."""
        old_entry = _create_entry(days_ago=10)

        result = cleanup_activitystream(days_old=7, dry_run=True)

        assert result["found"] >= 1
        assert result["deleted"] == 0

        from ansible_base.activitystream.models import Entry

        assert Entry.objects.filter(pk=old_entry.pk).exists()

    def test_deletes_entries_older_than_threshold(self):
        """Entries older than days_old are deleted when dry_run=False."""
        old_entry = _create_entry(days_ago=10)

        result = cleanup_activitystream(days_old=7, dry_run=False)

        assert result["deleted"] >= 1

        from ansible_base.activitystream.models import Entry

        assert not Entry.objects.filter(pk=old_entry.pk).exists()

    def test_preserves_recent_entries(self):
        """Entries newer than the threshold are not deleted."""
        recent_entry = _create_entry(days_ago=3)

        result = cleanup_activitystream(days_old=7, dry_run=False)

        assert result["deleted"] == 0

        from ansible_base.activitystream.models import Entry

        assert Entry.objects.filter(pk=recent_entry.pk).exists()

    def test_default_threshold_is_7_days(self):
        """The default days_old threshold is 7."""
        result = cleanup_activitystream(dry_run=True)

        assert result["days_old"] == 7

    def test_custom_days_old_parameter(self):
        """Custom days_old parameter is respected."""
        old_entry = _create_entry(days_ago=4)

        # Entry is within the 7-day window — should not be found
        result_7 = cleanup_activitystream(days_old=7, dry_run=True)
        assert result_7["found"] == 0

        # Entry is outside the 3-day window — should be found
        result_3 = cleanup_activitystream(days_old=3, dry_run=True)
        assert result_3["found"] >= 1

        from ansible_base.activitystream.models import Entry

        assert Entry.objects.filter(pk=old_entry.pk).exists()

    def test_cutoff_date_in_result(self):
        """The cutoff date returned in the result matches the expected range."""
        before = timezone.now()
        result = cleanup_activitystream(days_old=7, dry_run=True)
        after = timezone.now()

        cutoff = timezone.datetime.fromisoformat(result["cutoff_date"])
        expected_min = before - timedelta(days=7)
        expected_max = after - timedelta(days=7)

        assert expected_min <= cutoff <= expected_max

    def test_result_contains_expected_keys(self):
        """Result dict always contains the required keys."""
        result = cleanup_activitystream(dry_run=True)

        assert "days_old" in result
        assert "cutoff_date" in result
        assert "dry_run" in result
        assert "found" in result
        assert "deleted" in result

    def test_status_is_success(self):
        """Task result status is 'success' on a normal run."""
        result = cleanup_activitystream(dry_run=True)

        assert result["status"] == "success"

    def test_returns_error_for_zero_days_old(self):
        """days_old=0 returns an error result dict (wrapper catches all exceptions)."""
        result = cleanup_activitystream(days_old=0)

        assert result["status"] == "error"
        assert "days_old must be a positive integer" in result["error"]

    def test_returns_error_for_negative_days_old(self):
        """Negative days_old returns an error result dict."""
        result = cleanup_activitystream(days_old=-1)

        assert result["status"] == "error"
        assert "days_old must be a positive integer" in result["error"]

    def test_returns_error_for_non_integer_days_old(self):
        """Non-integer days_old returns an error result dict."""
        result = cleanup_activitystream(days_old="seven")

        assert result["status"] == "error"
        assert "days_old must be a positive integer" in result["error"]
