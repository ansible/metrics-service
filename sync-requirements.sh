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

# Generate build requirements from pinned requirements + build-time deps (pytest-runner, setuptools-scm).
# Build-time deps are needed so Cachi2 prefetches them for hermetic builds (e.g. django-crum needs pytest-runner).
echo "Generating requirements-build.txt..."
uv pip compile --output-file=requirements-build.txt requirements-pinned.txt requirements-build-extra.txt

# Prepend pip no-binary directives (one per line for Cachi2/prefetch compatibility).
# Only force source for crypto/psycopg; binaries allowed for Django, pandas, numpy, etc.
{ echo '--no-binary cryptography'; echo '--no-binary psycopg'; echo '--no-binary psycopg2'; echo '--no-binary psycopg-c'; cat requirements-build.txt; } > requirements-build.txt.tmp && mv requirements-build.txt.tmp requirements-build.txt

# Remove -e . so Hermeto/Cachi2 can parse this file; app is installed separately via "pip install ."
grep -v "^-e \\.$" requirements-build.txt > requirements-build.txt.tmp && mv requirements-build.txt.tmp requirements-build.txt

echo "Requirements files synced successfully!"
