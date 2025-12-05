# JSON vs Normalized Metrics Storage - Decision Guide

## TL;DR

**Current (JSON)**: Keep data in JSON field ✅ **Best for POC/MVP**
**Hybrid**: JSON + extracted key columns → **Best for most production use cases**
**Fully Normalized**: Separate tables for each metric type → **Best for complex analytics**

---

## Comparison Table

| Feature | JSON Only | Hybrid (JSON + Columns) | Fully Normalized |
|---------|-----------|------------------------|------------------|
| **Flexibility** | ✅ Excellent | ✅ Good | ⚠️ Limited |
| **Queryability** | ⚠️ Limited | ✅ Good | ✅ Excellent |
| **Performance** | ⚠️ Slower for filters | ✅ Good | ✅ Fast |
| **Schema Changes** | ✅ None needed | ⚠️ Minimal | ❌ Migration required |
| **Storage Size** | ✅ Compact | ⚠️ Some duplication | ⚠️ More rows |
| **Maintenance** | ✅ Low | ⚠️ Medium | ❌ High |
| **BI Tool Support** | ⚠️ Limited | ✅ Good | ✅ Excellent |
| **Setup Complexity** | ✅ Simple | ⚠️ Medium | ❌ Complex |

---

## Option 1: JSON Only (Current Implementation)

### What It Is
Store all collector data in the `MetricData.data` JSONField.

```python
MetricData(
    metric_type="config",
    data={
        "controller_version": "4.7.2",
        "install_uuid": "...",
        "total_licensed_instances": 100,
        # ... everything in JSON
    }
)
```

### Query Examples

```python
# Django ORM - limited querying
MetricData.objects.filter(
    metric_type__name='config',
    data__controller_version='4.7.2'  # JSON field lookup
)

# Raw SQL with json_extract (SQLite)
MetricData.objects.raw("""
    SELECT * FROM metric_data
    WHERE json_extract(data, '$.controller_version') >= '4.7'
""")
```

### When to Use
- ✅ POC/MVP (current stage)
- ✅ Rapidly changing collector schemas
- ✅ Don't need complex queries on metrics content
- ✅ Storage/export is main use case

### Limitations
- ❌ Can't index JSON fields efficiently
- ❌ Limited Django ORM support for JSON queries
- ❌ Some BI tools struggle with JSON
- ❌ Slower for filtering on nested fields

---

## Option 2: Hybrid (JSON + Key Columns) ⭐ RECOMMENDED

### What It Is
Keep full JSON but extract important searchable fields to dedicated columns.

```python
class MetricData(models.Model):
    data = models.JSONField()  # Full data

    # Extracted searchable fields
    extracted_version = models.CharField(max_length=50, db_index=True)
    extracted_hosts = models.IntegerField(db_index=True, null=True)
    extracted_jobs = models.IntegerField(db_index=True, null=True)

    def save(self, *args, **kwargs):
        # Auto-extract based on metric_type
        if self.metric_type.name == 'config':
            self.extracted_version = self.data.get('controller_version')
        elif self.metric_type.name == 'anonymized_rollups':
            stats = self.data.get('statistics', {})
            self.extracted_hosts = stats.get('hosts_automated_total')
            self.extracted_jobs = stats.get('jobs_total')
        super().save(*args, **kwargs)
```

### Query Examples

```python
# Fast indexed queries
MetricData.objects.filter(
    extracted_version__gte='4.7',
    extracted_hosts__gt=100
)

# Still have full JSON for detailed analysis
for metric in metrics:
    full_data = metric.data  # All original data available
```

### When to Use
- ✅ Need to query on specific fields frequently
- ✅ Want flexibility + performance
- ✅ Using BI tools that need indexed columns
- ✅ **Best for production after POC** ⭐

### Implementation Steps

```python
# 1. Add extracted fields to MetricData model
class MetricData(models.Model):
    # ... existing fields ...
    extracted_controller_version = models.CharField(max_length=50, null=True, db_index=True)
    extracted_install_uuid = models.UUIDField(null=True, db_index=True)
    extracted_hosts_total = models.IntegerField(null=True, db_index=True)
    extracted_jobs_total = models.IntegerField(null=True, db_index=True)
    extracted_modules_total = models.IntegerField(null=True, db_index=True)

# 2. Update collect_and_store_metrics to populate
def _extract_key_fields(metric_type_name, data):
    """Extract searchable fields from JSON data."""
    extracted = {}

    if metric_type_name == 'config':
        extracted['extracted_controller_version'] = data.get('controller_version')
        extracted['extracted_install_uuid'] = data.get('install_uuid')

    elif metric_type_name == 'anonymized_rollups':
        stats = data.get('statistics', {})
        extracted['extracted_hosts_total'] = stats.get('hosts_automated_total')
        extracted['extracted_jobs_total'] = stats.get('jobs_total')
        extracted['extracted_modules_total'] = stats.get('modules_used_to_automate_total')

    return extracted

# 3. Use in task
metric_data = MetricData.objects.using("metrics_storage").create(
    collection_run=collection_run,
    metric_type=metric_type,
    data=data_to_store,
    was_successful=was_successful,
    **_extract_key_fields(collector_name, data_to_store)  # Add extracted fields
)
```

---

## Option 3: Fully Normalized

### What It Is
Create separate models for each metric type's structure.

```python
# Separate model for each collector
class ConfigMetric(models.Model):
    metric_data = models.OneToOneField(MetricData, on_delete=models.CASCADE)
    controller_version = models.CharField(max_length=50, db_index=True)
    install_uuid = models.UUIDField(db_index=True)
    total_licensed_instances = models.IntegerField()
    # ... all fields explicitly defined

class AnonymizedRollupsMetric(models.Model):
    metric_data = models.OneToOneField(MetricData, on_delete=models.CASCADE)
    hosts_automated_total = models.IntegerField(db_index=True)
    jobs_total = models.IntegerField(db_index=True)
    # ... all fields
```

### Query Examples

```python
# Full Django ORM power
ConfigMetric.objects.filter(
    controller_version__gte='4.7',
    total_licensed_instances__gt=50
).select_related('metric_data__collection_run')

# Complex joins
from django.db.models import Avg, Count
AnonymizedRollupsMetric.objects.values(
    'metric_data__collection_run__started_at__date'
).annotate(
    avg_hosts=Avg('hosts_automated_total'),
    total_jobs=Count('jobs_total')
)
```

### When to Use
- ✅ Need complex analytics and reporting
- ✅ BI tools are primary consumers
- ✅ Schema is stable and well-defined
- ✅ Performance is critical

### Limitations
- ❌ Requires migration for every collector schema change
- ❌ More models to maintain
- ❌ Higher complexity

---

## Migration Path

### Phase 1: Current (JSON Only) ✅ DONE
- Store everything in JSON
- Get POC working
- Understand query patterns

### Phase 2: Add Hybrid Extraction (Recommended Next Step)
1. Identify 5-10 most-queried fields across all collectors
2. Add `extracted_*` columns to `MetricData`
3. Update `collect_and_store_metrics` to populate them
4. Update API endpoints to use extracted fields for filtering
5. Keep JSON for full data access

Example extracted fields:
- `extracted_controller_version` (from config)
- `extracted_install_uuid` (from config)
- `extracted_hosts_total` (from anonymized_rollups)
- `extracted_jobs_total` (from anonymized_rollups)
- `extracted_modules_total` (from anonymized_rollups)

### Phase 3: Consider Full Normalization (If Needed)
- Only if hybrid approach isn't sufficient
- When you have stable, well-understood schemas
- When complex analytics are required

---

## Real-World Example Queries

### JSON Only (Current)
```python
# Slow - can't use index
MetricData.objects.raw("""
    SELECT * FROM metric_data
    WHERE json_extract(data, '$.controller_version') >= '4.7'
    AND json_extract(data, '$.statistics.hosts_automated_total') > 100
""")
```

### Hybrid Approach
```python
# Fast - uses indexes
MetricData.objects.filter(
    extracted_controller_version__gte='4.7',
    extracted_hosts_total__gt=100
).select_related('metric_type', 'collection_run')

# Still have full data
for metric in metrics:
    detailed_stats = metric.data.get('statistics')  # Full JSON available
```

### Fully Normalized
```python
# Very fast - fully indexed joins
ConfigMetric.objects.filter(
    controller_version__gte='4.7'
).annotate(
    collection_date=F('metric_data__collected_at')
).values('controller_version').annotate(
    count=Count('id')
)
```

---

## Recommendation for Your Use Case

### Immediate (POC) ✅
**Keep JSON-only** - You're already there, it's working!

### Short-term (Production MVP)
**Implement Hybrid** - Add 5-10 extracted columns:
```python
# Migration to add columns
python manage.py makemigrations metrics_storage --name add_extracted_fields

# Update collect_and_store_metrics to populate them
# Update API filters to use them
```

### Long-term (If Needed)
**Consider normalization** only if:
- You need complex multi-table joins
- BI tools require it
- Query performance isn't sufficient with hybrid

---

## SQLite-Specific Considerations

### JSON Support in SQLite
SQLite has good JSON support (3.38+):
- `json_extract()` for querying
- `json_each()` for array iteration
- JSON indexes (virtual columns)

### Virtual Columns Alternative (SQLite)
Instead of hybrid approach, use virtual columns:

```sql
ALTER TABLE metric_data
ADD COLUMN extracted_version TEXT GENERATED ALWAYS AS (
    json_extract(data, '$.controller_version')
) VIRTUAL;

CREATE INDEX idx_extracted_version ON metric_data(extracted_version);
```

This gives you indexed columns without storing duplicates!

**Django support**: Limited - requires raw SQL or custom migrations.

---

## Summary Recommendation

1. **POC (Now)**: Keep JSON-only ✅
2. **Production MVP**: Add hybrid extracted columns ⭐
3. **Future**: Consider full normalization only if needed

The hybrid approach gives you 80% of the benefits of normalization with 20% of the complexity!
