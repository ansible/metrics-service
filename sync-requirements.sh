#!/bin/bash

# sync-requirements.sh
# Script to automatically sync requirements.txt and dev-requirements.txt from uv.lock

set -e

echo "Syncing requirements files from uv.lock..."

# Generate production requirements (no dev dependencies)
echo "Generating requirements.txt..."
uv export --format requirements.txt --no-dev -o requirements.txt

# Generate dev requirements (only dev dependencies)
echo "Generating dev-requirements.txt..."
uv export --format requirements.txt --only-dev -o dev-requirements.txt

echo "Requirements files synced successfully!"
