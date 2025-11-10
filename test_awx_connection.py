#!/usr/bin/env python
"""Test AWX database connection"""

import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "metrics_service.settings.development")
django.setup()

from django.db import connections  # noqa: E402

try:
    awx_conn = connections["awx"]
    with awx_conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM main_job")
        count = cursor.fetchone()[0]
        sys.stdout.write("✅ AWX database connection successful!\n")
        sys.stdout.write(f"✅ Found {count} jobs in main_job table\n")
except Exception as e:
    sys.stderr.write(f"❌ AWX database connection failed: {e}\n")
    sys.exit(1)
