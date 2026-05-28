#!/bin/sh
# Demo environment initialisation.
# Extends the standard init.sh with demo-specific setup:
#   - Creates a demo superuser (demo_admin / demo_password)
#   - Creates a DRF token for the BI connector
#   - Enables the BI_CONNECTOR feature flag
set -e

export PATH="/app/.venv/bin:$PATH"

echo "=== Running database migrations ==="
# DAB's post_migrate signal raises Resource.DoesNotExist on first boot before the
# resource registry is seeded. Migrations are applied correctly regardless.
# Suppress the non-zero exit so the init container is marked successful.
python manage.py migrate --noinput || true

echo "=== Initialising default settings ==="
python manage.py metrics_service init-default-settings

echo "=== Initialising django-ansible-base ServiceID ==="
python manage.py metrics_service init-service-id

echo "=== Initialising system tasks ==="
python manage.py metrics_service init-system-tasks

echo "=== Creating demo superuser (demo_admin) ==="
python manage.py shell -c "
from apps.core.models import User
if not User.objects.filter(username='demo_admin').exists():
    User.objects.create_superuser('demo_admin', 'demo@example.com', 'demo_password')
    print('Created demo_admin superuser')
else:
    print('demo_admin already exists')
"

echo "=== Creating BI connector API token (fixed key: demo-bi-connector-token) ==="
python manage.py shell -c "
from rest_framework.authtoken.models import Token
from apps.core.models import User
user = User.objects.get(username='demo_admin')
Token.objects.filter(user=user).delete()
Token.objects.create(user=user, key='demo-bi-connector-token')
print('BI connector token: demo-bi-connector-token')
"

echo "=== Enabling BI_CONNECTOR feature flag in the database ==="
python manage.py shell -c "
from apps.dynamic_settings.models import Setting
Setting.objects.update_or_create(
    setting_key='BI_CONNECTOR',
    defaults={'current_value': 'true'}
)
print('BI_CONNECTOR feature flag enabled')
"

echo "=== Seeding BI connector demo data ==="
python manage.py seed_bi_demo_data

echo "=== Demo initialisation complete ==="
echo "   Metrics Service: http://localhost:8000"
echo "   API docs:        http://localhost:8000/api/docs/"
echo "   Grafana:         http://localhost:3000  (admin / admin)"
echo ""
echo "   Demo credentials:"
echo "     API login:          demo_admin / demo_password"
echo "     BI connector token: demo-bi-connector-token"
echo "     Grafana:            admin / admin"
