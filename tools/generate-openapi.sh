#!/usr/bin/env bash
# Regenerate OpenAPI schema files using the same commands as CI (pr-checks.yml).
#
# Run from the repo root. After running, check the diff and apply any known
# manual patches before committing (see the "Manual patches" section below).
#
# Usage: bash tools/generate-openapi.sh
set -euo pipefail

YAML_OUT="tools/openapi-schema/metrics-service.yaml"
JSON_OUT="tools/openapi-schema/metrics-service.json"

mkdir -p tools/openapi-schema

echo "→ Generating YAML schema..."
uv run --frozen python manage.py spectacular --file "$YAML_OUT"

echo "→ Generating JSON schema..."
uv run --frozen python manage.py spectacular --format openapi-json --file "$JSON_OUT"

echo ""
echo "Done. Review the diff:"
echo "  git diff $YAML_OUT"
echo "  git diff $JSON_OUT"
echo ""
echo "──────────────────────────────────────────────────────────────"
echo "Known manual patches (apply if git diff shows these changes):"
echo ""
echo "1. Path parameter types: spectacular cannot resolve the type of"
echo "   untyped URL path params on some environments and defaults to"
echo "   'type: string'. If CI shows integer→string diffs for the 'id'"
echo "   params on DashboardReportViewSet or SubscriptionCostViewSet,"
echo "   match whichever type CI generates (currently: string)."
echo ""
echo "2. feature_flags_state endpoint: may appear/disappear depending"
echo "   on DAB version installed. Match whatever CI generates."
echo ""
echo "3. OrganizationDisassociate components: removed in DAB updates."
echo "   If CI removes them, remove from the committed schema too."
echo "──────────────────────────────────────────────────────────────"
