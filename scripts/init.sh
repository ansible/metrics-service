#!/bin/sh
set -e

# AAPFlag has AnsibleResourceField but is not registered in the resource
# registry, so no Resource rows are ever created for feature flags. On a fresh
# (unsaved) instance full_clean skips the resource check; on an existing row it
# queries the DB and raises Resource.DoesNotExist, crashing post_migrate.
# Truncating before migrate keeps us in the "fresh instance" path on every run.
# The post_migrate signal always recreates flags from the YAML definitions.
echo "Resetting feature flags for clean re-initialization..."
python manage.py shell -c "
from django.db import connection
with connection.cursor() as c:
    c.execute(\"SELECT to_regclass('public.dab_feature_flags_aapflag')\")
    if c.fetchone()[0]:
        c.execute('TRUNCATE TABLE dab_feature_flags_aapflag CASCADE')
        print('Cleared stale feature flags')
" || true

echo "Running database migrations..."
python manage.py migrate --noinput

# puts defaults in the Setting DB table
echo "Initializing default settings..."
python manage.py metrics_service init-default-settings

# Initialize ServiceID for django-ansible-base
echo "Initializing django-ansible-base ServiceID..."
python manage.py metrics_service init-service-id

# puts TASK_GROUPS in the Task DB table
echo "Initializing system tasks..."
python manage.py metrics_service init-system-tasks
