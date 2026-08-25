#!/bin/sh
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

# puts defaults in the Setting DB table
echo "Initializing default settings..."
python manage.py metrics_service init-default-settings

# Initialize ServiceID for django-ansible-base
echo "Initializing django-ansible-base ServiceID..."
python manage.py metrics_service init-service-id

# Load service ingest schemas from YAML files
echo "Loading service ingest schemas..."
python manage.py load_ingest_schemas

# puts TASK_GROUPS in the Task DB table
echo "Initializing system tasks..."
python manage.py metrics_service init-system-tasks
