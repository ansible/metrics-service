#!/bin/sh
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

# Explicitly create/refresh DAB managed RBAC role definitions (Platform Auditor, Organization
# Admin, Organization Member, Team Admin, Team Member). This supplements the post_migrate signal
# that normally creates these, but which can silently fail in some deployment environments.
echo "Initializing managed RBAC role definitions..."
python manage.py metrics_service init-managed-roles

# puts defaults in the Setting DB table
echo "Initializing default settings..."
python manage.py metrics_service init-default-settings

# Initialize ServiceID for django-ansible-base
echo "Initializing django-ansible-base ServiceID..."
python manage.py metrics_service init-service-id

# puts TASK_GROUPS in the Task DB table
echo "Initializing system tasks..."
python manage.py metrics_service init-system-tasks
