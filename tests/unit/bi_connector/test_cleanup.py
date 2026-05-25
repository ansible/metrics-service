"""
Tests for apps/bi_connector/collectors/cleanup.py
"""

from datetime import timedelta

import pytest
from django.utils.timezone import now

from apps.bi_connector.collectors.cleanup import (
    cleanup_bi_collection_batches,
    cleanup_bi_stored_host_metrics,
)
from apps.bi_connector.models import CollectionBatch, StoredHostMetric


@pytest.mark.unit
@pytest.mark.django_db
class TestCleanupBiCollectionBatches:
    """Tests for cleanup_bi_collection_batches()."""

    def _create_batch(self, age_days: int, **kwargs) -> CollectionBatch:
        batch = CollectionBatch.objects.create(
            collector_type="unified_jobs",
            batch_type="scheduled",
            status="completed",
            **kwargs,
        )
        old_date = now() - timedelta(days=age_days)
        CollectionBatch.objects.filter(pk=batch.pk).update(created=old_date)
        return batch

    def test_deletes_old_batches(self):
        old_batch = self._create_batch(age_days=100)
        result = cleanup_bi_collection_batches()
        assert result["status"] == "success"
        assert result["deleted"] == 1
        assert not CollectionBatch.objects.filter(pk=old_batch.pk).exists()

    def test_keeps_recent_batches(self):
        recent_batch = self._create_batch(age_days=10)
        result = cleanup_bi_collection_batches()
        assert result["status"] == "success"
        assert result["deleted"] == 0
        assert CollectionBatch.objects.filter(pk=recent_batch.pk).exists()

    def test_custom_retention_days_deletes_within_window(self):
        # 2 days old — older than custom 1-day retention, should be deleted
        old_batch = self._create_batch(age_days=2)
        result = cleanup_bi_collection_batches({"retention_days": 1})
        assert result["status"] == "success"
        assert result["deleted"] == 1
        assert not CollectionBatch.objects.filter(pk=old_batch.pk).exists()

    def test_custom_retention_days_keeps_newer_batch(self):
        # Within the custom retention window
        recent_batch = self._create_batch(age_days=1)
        result = cleanup_bi_collection_batches({"retention_days": 30})
        assert result["status"] == "success"
        assert result["deleted"] == 0
        assert CollectionBatch.objects.filter(pk=recent_batch.pk).exists()

    def test_returns_correct_count_for_multiple_old_batches(self):
        self._create_batch(age_days=200)
        self._create_batch(age_days=150)
        self._create_batch(age_days=5)  # should be kept
        result = cleanup_bi_collection_batches()
        assert result["deleted"] == 2

    def test_empty_table_returns_zero(self):
        result = cleanup_bi_collection_batches()
        assert result["status"] == "success"
        assert result["deleted"] == 0

    def test_default_retention_is_90_days(self):
        # A batch 89 days old should be kept with default 90-day retention
        batch_89 = self._create_batch(age_days=89)
        result = cleanup_bi_collection_batches()
        assert result["deleted"] == 0
        assert CollectionBatch.objects.filter(pk=batch_89.pk).exists()

        # A batch 91 days old should be deleted with default 90-day retention
        batch_91 = self._create_batch(age_days=91)
        result = cleanup_bi_collection_batches()
        assert result["deleted"] == 1
        assert not CollectionBatch.objects.filter(pk=batch_91.pk).exists()


@pytest.mark.unit
@pytest.mark.django_db
class TestCleanupBiStoredHostMetrics:
    """Tests for cleanup_bi_stored_host_metrics()."""

    def _create_host(self, hostname: str, deleted: bool, age_days: int) -> StoredHostMetric:
        metric = StoredHostMetric.objects.create(hostname=hostname, deleted=deleted)
        old_date = now() - timedelta(days=age_days)
        StoredHostMetric.objects.filter(pk=metric.pk).update(last_automation=old_date)
        return metric

    def test_deletes_stale_deleted_hosts(self):
        old_host = self._create_host("old-deleted-host", deleted=True, age_days=400)
        result = cleanup_bi_stored_host_metrics()
        assert result["status"] == "success"
        assert result["deleted"] == 1
        assert not StoredHostMetric.objects.filter(pk=old_host.pk).exists()

    def test_keeps_active_hosts_even_if_old(self):
        active_host = self._create_host("active-host", deleted=False, age_days=400)
        result = cleanup_bi_stored_host_metrics()
        assert result["status"] == "success"
        assert result["deleted"] == 0
        assert StoredHostMetric.objects.filter(pk=active_host.pk).exists()

    def test_keeps_recently_deleted_hosts(self):
        recent_deleted = self._create_host("recent-deleted-host", deleted=True, age_days=10)
        result = cleanup_bi_stored_host_metrics()
        assert result["status"] == "success"
        assert result["deleted"] == 0
        assert StoredHostMetric.objects.filter(pk=recent_deleted.pk).exists()

    def test_custom_stale_days_deletes_within_window(self):
        # 2-day-old deleted host, with stale_days=1 should be removed
        old_host = self._create_host("stale-host", deleted=True, age_days=2)
        result = cleanup_bi_stored_host_metrics({"stale_days": 1})
        assert result["status"] == "success"
        assert result["deleted"] == 1
        assert not StoredHostMetric.objects.filter(pk=old_host.pk).exists()

    def test_custom_stale_days_keeps_host_in_window(self):
        host = self._create_host("fresh-deleted-host", deleted=True, age_days=1)
        result = cleanup_bi_stored_host_metrics({"stale_days": 30})
        assert result["status"] == "success"
        assert result["deleted"] == 0
        assert StoredHostMetric.objects.filter(pk=host.pk).exists()

    def test_returns_correct_count(self):
        self._create_host("stale-host-1", deleted=True, age_days=500)
        self._create_host("stale-host-2", deleted=True, age_days=400)
        self._create_host("active-host", deleted=False, age_days=500)
        self._create_host("recent-host", deleted=True, age_days=10)
        result = cleanup_bi_stored_host_metrics()
        assert result["deleted"] == 2

    def test_empty_table_returns_zero(self):
        result = cleanup_bi_stored_host_metrics()
        assert result["status"] == "success"
        assert result["deleted"] == 0

    def test_both_conditions_must_be_met_for_deletion(self):
        """Only hosts that are BOTH deleted=True AND older than stale_days get removed."""
        active_old = self._create_host("active-old", deleted=False, age_days=500)
        deleted_recent = self._create_host("deleted-recent", deleted=True, age_days=10)
        deleted_old = self._create_host("deleted-old", deleted=True, age_days=500)

        result = cleanup_bi_stored_host_metrics()

        assert result["deleted"] == 1
        assert StoredHostMetric.objects.filter(pk=active_old.pk).exists()
        assert StoredHostMetric.objects.filter(pk=deleted_recent.pk).exists()
        assert not StoredHostMetric.objects.filter(pk=deleted_old.pk).exists()
