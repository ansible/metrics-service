# CSV Conversion Fix - Always Store Database Entries

## Issue Reported

**Problem**: CSV collectors were running successfully, but no database entries were being created for collectors that returned CSV file paths (job_host_summary, main_host, main_jobevent).

**Expected**: Every collector should create a database entry, even if:
- Data is empty
- CSV files can't be read
- Collection fails

**Actual**: Only collectors returning JSON directly were saved to database.

---

## Root Cause

### Before the Fix

The `collect_and_store_metrics` task had two issues:

1. **CSV Processing Logic** (lines 893-920):
   ```python
   if csv_files_processed > 0:
       # Store the converted data
       data_to_store = {...}
   # If csv_files_processed == 0, data_to_store was NEVER updated
   # Then tried to save the raw list of CSV paths (which could fail)
   ```

2. **Silent Failures**:
   - CSV files in temp directories (`/var/folders/.../T/awx_analytics-...`) were cleaned up by metrics-utility
   - When code tried to read them, files didn't exist
   - Exceptions were caught silently, no database entry created

3. **Skipped Collectors**:
   - If a collector wasn't found (ValueError), it was skipped entirely
   - No entry added to `all_results`
   - No database entry created

---

## The Fix

### Changes Made to `apps/tasks/tasks_collector.py`

#### 1. Ensure ALL Requested Collectors Get Entries (lines 850-856)

```python
# BEFORE: Only collectors that ran successfully were in all_results

# AFTER: Add placeholder for any missing collectors
for collector_name in collectors_list:
    if collector_name not in all_results:
        all_results[collector_name] = {
            "error": "Collector not found or failed to execute",
            "collector_skipped": True,
        }
```

#### 2. ALWAYS Save Data, Even If Empty (lines 937-947)

```python
# ALWAYS store data, even if no CSV files were successfully processed
data_to_store = {
    "collector": collector_name,
    "original_format": "csv",
    "csv_files_expected": csv_files_expected,
    "csv_files_processed": csv_files_processed,
    "csv_files_missing": csv_files_missing,  # Track missing files
    "rows_converted": len(csv_data),
    "data": csv_data,  # Empty array if no data
    "original_paths": collector_result,  # Keep for debugging
}
```

#### 3. Track Missing CSV Files (lines 869, 934-935)

```python
csv_files_missing = []

# When CSV file doesn't exist:
if os.path.exists(csv_file_path):
    # Read it
else:
    logger.warning(f"CSV file not found: {csv_file_path}")
    csv_files_missing.append(csv_file_path)
```

#### 4. Mark as Unsuccessful When Appropriate (lines 949-952)

```python
# Mark as unsuccessful if no CSV files were processed
if csv_files_processed == 0 and csv_files_expected > 0:
    was_successful = False
    error_message = f"No CSV files accessible: {csv_files_expected} expected, 0 processed"
```

#### 5. Fallback Error Entry (lines 974-987)

```python
except Exception as e:
    logger.error(f"Error saving metric data for {collector_name}: {str(e)}")
    # Even if there's an error, try to save a minimal entry
    try:
        MetricData.objects.using("metrics_storage").create(
            collection_run=collection_run,
            metric_type=metric_type,
            data={"collector": collector_name, "collection_error": str(e)},
            was_successful=False,
            error_message=f"Failed to save: {str(e)}",
        )
        metrics_saved += 1
    except Exception as save_error:
        logger.error(f"Could not create fallback entry for {collector_name}: {str(save_error)}")
```

---

## Results After Fix

### Test Collection Run

**Collectors requested**: 5 (anonymized_rollups, config, job_host_summary, main_host, main_jobevent)

**Database entries created**: 5 ✅ (ALL collectors now have entries)

```
Collector            Success    Data Size    Details
--------------------------------------------------------------------------------
anonymized_rollups   ✓ Yes      421 bytes    JSON format (native)
config               ✓ Yes      1039 bytes   JSON format (native)
job_host_summary     ✓ Yes      299 bytes    CSV: 0 rows converted
main_host            ✓ Yes      29190 bytes  CSV: 32 rows converted
main_jobevent        ✓ Yes      290 bytes    CSV: 0 rows converted
```

### Data Structure Examples

#### Empty CSV Collection (job_host_summary)

```json
{
    "collector": "job_host_summary",
    "original_format": "csv",
    "csv_files_expected": 1,
    "csv_files_processed": 1,
    "csv_files_missing": [],
    "rows_converted": 0,
    "data": [],
    "original_paths": [
        "/var/folders/.../main_jobhostsummary_table.csv"
    ]
}
```

**Key points**:
- ✅ Entry created even though data is empty
- ✅ Tracks that 1 CSV file was expected and processed
- ✅ Shows 0 rows converted
- ✅ Includes original file path for debugging

#### CSV Collection with Data (main_host)

```json
{
    "collector": "main_host",
    "original_format": "csv",
    "csv_files_expected": 1,
    "csv_files_processed": 1,
    "csv_files_missing": [],
    "rows_converted": 32,
    "data": [
        {
            "host_name": "default_host_hostmetric_1_2025-06-13",
            "host_id": "1",
            "inventory_remote_id": "1",
            "inventory_name": "default_inventory_hostmetric_1_2025-06-13",
            ...
        },
        // ... 31 more rows
    ],
    "original_paths": [...]
}
```

**Key points**:
- ✅ CSV successfully converted to JSON array
- ✅ 32 rows of data preserved
- ✅ All column names and values properly extracted

#### Failed Collector (if one fails)

```json
{
    "collector": "unknown_collector",
    "collection_error": "Collector not found or failed to execute",
    "collector_skipped": true
}
```

**Key points**:
- ✅ Entry created even for failed/unknown collectors
- ✅ Error message recorded
- ✅ Marked as unsuccessful

---

## Benefits of the Fix

### 1. Complete Audit Trail

- **Before**: Only successful collections visible in database
- **After**: ALL collectors tracked, including failures and empty results

### 2. Better Debugging

```json
{
    "csv_files_expected": 1,
    "csv_files_processed": 0,
    "csv_files_missing": ["/path/to/missing.csv"],
    "original_paths": ["/path/to/missing.csv"]
}
```

- Can see exactly which CSV files couldn't be read
- Can debug temp file cleanup issues
- Can verify collector behavior

### 3. Data Integrity

- **Guaranteed entry** for every requested collector
- No silent failures
- Clear success/failure status
- Error messages preserved

### 4. Consistent Behavior

```python
# Every collector gets an entry
collectors_requested = 5
database_entries_created = 5  # Always matches!
```

---

## Testing

### Manual Test

```bash
# Run collection
python manage.py shell

from apps.tasks.tasks_collector import collect_and_store_metrics
result = collect_and_store_metrics(
    collectors=['anonymized_rollups', 'config', 'job_host_summary', 'main_host', 'main_jobevent']
)

# Check database
sqlite3 metricsStorage.sqlite
SELECT mt.name, md.was_successful, length(md.data), md.error_message
FROM metric_data md
JOIN metric_types mt ON md.metric_type_id = mt.id
WHERE md.collection_run_id = (SELECT MAX(id) FROM collection_runs);
```

### Expected Output

- 5 rows returned (one for each collector)
- Some with `was_successful = 1` (worked)
- Some with `was_successful = 0` (empty CSV or errors)
- All have data (even if `data = []`)

---

## Migration Guide

### No Migration Needed!

This is a **code-only fix** - no database schema changes required.

### Existing Data

- Old entries remain unchanged
- New collections will have improved metadata
- Both formats coexist peacefully

---

## Summary

### Problem
❌ CSV collectors not creating database entries when data was empty or CSV files were inaccessible

### Solution
✅ **ALWAYS create a database entry** for every collector, with:
- Proper metadata (expected/processed/missing counts)
- Error messages when failures occur
- Empty data arrays when no data collected
- Original file paths for debugging

### Result
🎯 **Complete visibility** into all collection attempts, successful or not!

---

## Files Modified

- `apps/tasks/tasks_collector.py` (lines 847-987)
  - Added check to ensure all requested collectors get entries
  - Track CSV files missing/processed/expected
  - Always save data, even if empty
  - Fallback error entry creation

---

## Related Documentation

- **METRICS_SQLITE_POC_SUMMARY.md** - Overview of SQLite storage implementation
- **docs/using-views-with-bi-tools.md** - How to query the data
- **apps/metrics_storage/sql/create_views.sql** - Database views for BI tools
