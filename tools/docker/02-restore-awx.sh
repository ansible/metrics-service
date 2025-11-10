#!/bin/bash
set -e
echo "Restoring AWX database from dump..."
psql -v ON_ERROR_STOP=1 --username "awx" --dbname "awx" < /docker-entrypoint-initdb.d/awx_mock_dump.sql
echo "AWX database restored successfully!"
