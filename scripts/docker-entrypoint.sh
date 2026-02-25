#!/bin/sh
set -e

# FIXME: should happen during prod web container build instead
# Collect static files (into staticfiles/)
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear || echo "Static files collection failed (continuing...)" 1>&2

exec "$@"
