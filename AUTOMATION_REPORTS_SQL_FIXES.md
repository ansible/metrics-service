# Automation Reports SQL Fixes

## Summary of Issues and Fixes

After analyzing the AWX database schema (columns.csv), I identified and fixed SQL query issues in the metrics-utility automation reports collectors.

---

## Issues Fixed

### 1. **Users Table Name** ✅ FIXED

**Problem**: Querying `main_user` table which doesn't exist in AWX

**Root Cause**: AWX uses Django's built-in authentication, so users are stored in `auth_user`, not `main_user`

**Fix**: Updated `automation_reports_entities.py`
```sql
-- Before (INCORRECT)
FROM main_user u

-- After (CORRECT)
FROM auth_user u
```

**File**: `/Users/cshiels/Documents/Repos/Forked/metrics-utility/metrics_utility/library/collectors/controller/automation_reports_entities.py`

**Also Removed**: `is_system_auditor` field check (doesn't exist in standard Django auth_user table)

---

### 2. **Job Templates Missing JOIN** ✅ FIXED

**Problem**: Querying columns directly from `main_jobtemplate` that don't exist there

**Root Cause**: AWX uses Django's multi-table inheritance pattern where:
- `main_jobtemplate` contains job-template-specific fields
- `main_unifiedjobtemplate` contains base fields (name, description, organization_id, execution_environment_id, created, modified)

**Columns in wrong table**:
- ❌ `main_jobtemplate.name` - doesn't exist
- ❌ `main_jobtemplate.description` - doesn't exist
- ❌ `main_jobtemplate.organization_id` - doesn't exist
- ❌ `main_jobtemplate.execution_environment_id` - doesn't exist
- ❌ `main_jobtemplate.created` - doesn't exist
- ❌ `main_jobtemplate.modified` - doesn't exist

**Columns in correct table**:
- ✅ `main_unifiedjobtemplate.name` - exists
- ✅ `main_unifiedjobtemplate.description` - exists
- ✅ `main_unifiedjobtemplate.organization_id` - exists
- ✅ `main_unifiedjobtemplate.execution_environment_id` - exists
- ✅ `main_unifiedjobtemplate.created` - exists
- ✅ `main_unifiedjobtemplate.modified` - exists

**Fix**: Updated `automation_reports_job_templates.py` to JOIN with `main_unifiedjobtemplate`

```sql
-- Before (INCORRECT)
SELECT
    jt.id AS external_id,
    jt.name,                      -- ❌ doesn't exist
    jt.description,               -- ❌ doesn't exist
    jt.organization_id,           -- ❌ doesn't exist
    jt.project_id,
    jt.inventory_id,
    jt.execution_environment_id,  -- ❌ doesn't exist
    jt.created,                   -- ❌ doesn't exist
    jt.modified,                  -- ❌ doesn't exist
    60 AS time_taken_manually_execute_minutes,
    240 AS time_taken_create_automation_minutes
FROM main_jobtemplate jt

-- After (CORRECT)
SELECT
    jt.id AS external_id,
    ujt.name,                     -- ✅ correct
    ujt.description,              -- ✅ correct
    ujt.organization_id,          -- ✅ correct
    jt.project_id,
    jt.inventory_id,
    ujt.execution_environment_id, -- ✅ correct
    ujt.created,                  -- ✅ correct
    ujt.modified,                 -- ✅ correct
    60 AS time_taken_manually_execute_minutes,
    240 AS time_taken_create_automation_minutes
FROM main_jobtemplate jt
JOIN main_unifiedjobtemplate ujt ON jt.unifiedjobtemplate_ptr_id = ujt.id
```

**Also Fixed**: Date filtering in daily collector now uses `ujt.created` and `ujt.modified` instead of `jt.created` and `jt.modified`

**File**: `/Users/cshiels/Documents/Repos/Forked/metrics-utility/metrics_utility/library/collectors/controller/automation_reports_job_templates.py`

---

## AWX Database Schema Pattern

AWX uses **Django multi-table inheritance** (polymorphism) where:

```
main_unifiedjobtemplate (base table)
    ├─ name, description, organization_id
    ├─ execution_environment_id
    ├─ created, modified
    └─ id (primary key)
         │
         └─ main_jobtemplate (child table)
             ├─ project_id, inventory_id
             ├─ job_type, playbook
             └─ unifiedjobtemplate_ptr_id (foreign key to parent)
```

Similar pattern exists for jobs:

```
main_unifiedjob (base table)
    ├─ name, description, organization_id
    ├─ status, started, finished, elapsed
    ├─ execution_environment_id, instance_group_id
    ├─ launch_type, created_by_id
    └─ id (primary key)
         │
         └─ main_job (child table)
             ├─ job_template_id, inventory_id, project_id
             ├─ job_type, playbook
             └─ unifiedjob_ptr_id (foreign key to parent)
```

---

## Verified Correct Collectors

These collectors were already correct and didn't need changes:

### ✅ Organizations (`automation_reports_organizations.py`)
- All columns exist directly in `main_organization` table
- No JOIN required

### ✅ Jobs (`automation_reports_jobs.py`)
- Already correctly JOINs `main_job` with `main_unifiedjob`
- All column references are correct

### ✅ Job Host Summaries (`automation_reports_job_host_summaries.py`)
- All columns exist directly in `main_jobhostsummary` table
- No JOIN required

### ✅ Inventories, Projects, Hosts, etc. (`automation_reports_entities.py`)
- All columns exist directly in their respective tables
- Only `users` collector needed fixing (table name)

---

## Testing the Fixes

### Method 1: Using provided test script

```bash
cd /Users/cshiels/Documents/Repos/Forked/metrics-service
python test_awx_collectors.py
```

**Note**: Edit the `DB_CONFIG` dictionary in the script to match your AWX database credentials.

### Method 2: Using collect_automation_reports task

```python
from apps.tasks.tasks_automation_reports import collect_automation_reports

# Test basic collection
result = collect_automation_reports(
    database='awx',
    collectors=['organizations', 'job_templates']
)

print(result)
```

### Method 3: Via Dashboard

1. Go to http://localhost:8000/dashboard/
2. Login with admin/admin
3. Select `collect_automation_reports` function
4. Use task data: `{"database": "awx"}`
5. Click "Create Task"

---

## Changes Summary

| File | Change | Reason |
|------|--------|--------|
| `automation_reports_entities.py` | Changed `main_user` → `auth_user` | AWX uses Django auth table |
| `automation_reports_entities.py` | Removed `is_system_auditor` check | Field doesn't exist in auth_user |
| `automation_reports_job_templates.py` | Added JOIN with `main_unifiedjobtemplate` | Inheritance pattern |
| `automation_reports_job_templates.py` | Changed column references to use `ujt.*` | Columns in parent table |
| `automation_reports_job_templates.py` | Updated daily WHERE clause | Use `ujt.created` and `ujt.modified` |

---

## Verified Against AWX Schema

All SQL queries were verified against the actual AWX database schema provided in:
`/Users/cshiels/Documents/Repos/Forked/metrics-utility/metrics_utility/library/collectors/controller/columns.csv`

The fixes ensure that:
1. All table names are correct
2. All column names exist in the correct tables
3. JOINs are used where multi-table inheritance patterns exist
4. Column references use the correct table aliases

---

## Status

✅ **All fixes applied and metrics-utility reinstalled**

The automation reports collectors should now work correctly with the AWX database schema.

Next step: Test the collectors by running the `collect_automation_reports` task in metrics-service.
