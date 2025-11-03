#!/bin/bash

# sync-requirements.sh
# Script to automatically sync requirements-pinned.txt, dev-requirements.txt, and requirements-build.txt from uv.lock

set -e

# Use uv from virtual environment
UV_BIN=".venv/bin/uv"

# Check if uv exists in .venv
if [ ! -f "$UV_BIN" ]; then
    echo "Error: uv not found in .venv. Please run 'uv sync' first."
    exit 1
fi

echo "Syncing requirements files from uv.lock..."

# Generate production requirements (no dev dependencies)
echo "Generating requirements-pinned.txt..."
$UV_BIN export --format requirements.txt --no-dev -o requirements-pinned.txt

# Generate dev requirements (only dev dependencies)
echo "Generating dev-requirements.txt..."
$UV_BIN export --format requirements.txt --only-dev -o dev-requirements.txt

# Generate build requirements from pinned requirements
# Note: This may fail with git dependencies that have conflicting URLs
echo "Generating requirements-build.txt..."
if ! $UV_BIN pip compile --output-file=requirements-build.txt requirements-pinned.txt 2>&1; then
    echo "Warning: requirements-build.txt generation failed (likely due to git dependency conflicts)."
    echo "Skipping requirements-build.txt generation."
fi

echo "Requirements files synced successfully!"