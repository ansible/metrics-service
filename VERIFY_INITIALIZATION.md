# Verifying Feature Flag Auto-Initialization

This document explains how to verify that feature flags are automatically initialized in the database on application startup.

## What Gets Initialized

On application startup, the following settings are automatically created in the `dynamic_settings_setting` table if they don't exist:

1. **METRICS_COLLECTION_ENABLED** - Default: `false`
2. **ANONYMIZED_DATA_COLLECTION** - Default: `true`

## How to Verify

### Option 1: Check via Django Shell

```bash
.venv/bin/python manage.py shell
```

```python
from apps.dynamic_settings.models import Setting

# Check if settings exist
settings = Setting.objects.all()
for setting in settings:
    print(f"{setting.setting_key}: {setting.current_value}")

# Should output:
# METRICS_COLLECTION_ENABLED: false
# ANONYMIZED_DATA_COLLECTION: true
```

### Option 2: Check via SQL

```bash
psql -U myuser -d awx
```

```sql
SELECT setting_key, current_value, modified, last_modified_by_id
FROM dynamic_settings_setting
ORDER BY setting_key;
```

### Option 3: Check Server Logs

Start the server and look for initialization messages:

```bash
.venv/bin/python manage.py runserver
```

You should see log messages like:
```
INFO apps.dynamic_settings.utils Initialized setting 'METRICS_COLLECTION_ENABLED' with default value: False (Enable hourly metrics collection with daily rollup and anonymization)
INFO apps.dynamic_settings.utils Initialized setting 'ANONYMIZED_DATA_COLLECTION' with default value: True (Enable anonymous data collection for Red Hat)
INFO apps.dynamic_settings.utils Initialized 2 default settings in database
```

## Modifying Settings

### Via Django Shell

```python
from apps.dynamic_settings.models import Setting

# Enable hourly collection
setting = Setting.objects.get(setting_key='METRICS_COLLECTION_ENABLED')
setting.current_value = 'true'
setting.save()

# Verify
print(f"Updated: {setting.setting_key} = {setting.current_value}")
```

### Via SQL

```sql
-- Enable hourly collection
UPDATE dynamic_settings_setting
SET current_value = 'true', previous_value = current_value, modified = NOW()
WHERE setting_key = 'METRICS_COLLECTION_ENABLED';

-- Verify
SELECT setting_key, current_value FROM dynamic_settings_setting;
```

## Testing Runtime Behavior

After modifying a setting, tasks will automatically respond on their next scheduled run:

1. **Enable** `METRICS_COLLECTION_ENABLED` → Hourly collection tasks will run
2. **Disable** `METRICS_COLLECTION_ENABLED` → Hourly collection tasks will be skipped

Check logs to see tasks being skipped:
```
INFO: Skipping task hourly_job_host_summary (collect_job_host_summary_hourly): feature flag METRICS_COLLECTION_ENABLED is disabled
```

## Troubleshooting

### Settings Not Created

If settings aren't created on startup:

1. Check that migrations have been run: `.venv/bin/python manage.py migrate`
2. Check logs for errors during initialization
3. Verify the `dynamic_settings_setting` table exists
4. Ensure database connection is working

### Settings Not Updating

If task behavior doesn't change after updating settings:

1. Verify the setting was actually updated in the database
2. Check that the cron scheduler is running
3. Wait for the next scheduled run of the task
4. Check logs for "Skipping task" messages

## Implementation Details

- **File**: `apps/dynamic_settings/apps.py` - Calls initialization in `ready()` method
- **File**: `apps/dynamic_settings/utils.py` - Contains `initialize_default_settings()` function
- **Behavior**: Settings are only created if they don't exist (idempotent)
- **Defaults**: Come from `FEATURE_ENABLED` Django setting, with hardcoded fallbacks
