#!/bin/bash

# sync-requirements.sh
# Script to automatically sync requirements-pinned.txt, dev-requirements.txt, and requirements-build.txt from uv.lock

set -e

echo "Syncing requirements files from uv.lock..."

# Generate production requirements (no dev dependencies)
echo "Generating requirements-pinned.txt..."
uv export --format requirements.txt --no-dev -o requirements-pinned.txt

# Generate dev requirements (only dev dependencies)
echo "Generating dev-requirements.txt..."
uv export --format requirements.txt --only-dev -o dev-requirements.txt

# Generate build requirements from pinned requirements
echo "Generating requirements-build.txt..."
uv pip compile --output-file=requirements-build.txt requirements-pinned.txt

# Prepend pip directive so Cachi2/prefetch uses only source distributions (no binary wheels).
# This avoids "hermeto:pip:package:binary" verification violations in Konflux hermetic builds.
{ echo '--no-binary :all:'; cat requirements-build.txt; } > requirements-build.txt.tmp && mv requirements-build.txt.tmp requirements-build.txt

echo "Requirements files synced successfully!"