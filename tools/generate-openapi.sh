#!/usr/bin/env bash
# Regenerate OpenAPI schema files and apply known manual patches.
#
# CI (pr-checks.yml) runs spectacular on Linux; local macOS generates slightly
# different output for untyped path params and some DAB-provided endpoints.
# This script regenerates both files and applies the patches needed to match CI.
#
# Usage (from repo root): bash tools/generate-openapi.sh
set -euo pipefail

YAML_OUT="tools/openapi-schema/metrics-service.yaml"
JSON_OUT="tools/openapi-schema/metrics-service.json"

mkdir -p tools/openapi-schema

echo "→ Generating YAML schema..."
uv run --frozen python manage.py spectacular --file "$YAML_OUT"

echo "→ Generating JSON schema..."
uv run --frozen python manage.py spectacular --format openapi-json --file "$JSON_OUT"

echo "→ Applying known manual patches to YAML..."
# 1. Path param type: integer → string (spectacular defaults to string on CI Linux)
sed -i '' \
    -e '/A unique integer value identifying this Job Data\./{ N; s/\n.*required: true/\n        required: true/ }' \
    "$YAML_OUT" 2>/dev/null || true
# Use Python for the reliable multi-line YAML + JSON patches
uv run --frozen python - <<'PYEOF'
import re, pathlib

yaml_path = pathlib.Path("tools/openapi-schema/metrics-service.yaml")
content = yaml_path.read_text()

# Fix path param types: change integer+description to string (no description)
# Pattern: schema:\n          type: integer\n        description: A unique integer value...
for desc in [
    "A unique integer value identifying this Job Data.",
    "A unique integer value identifying this Subscription Cost.",
]:
    pattern = (
        r"(        schema:\n          type: )integer\n"
        r"        description: " + re.escape(desc) + r"\n"
    )
    replacement = r"\1string\n"
    content = re.sub(pattern, replacement, content)

yaml_path.write_text(content)
print("  YAML path param types fixed")
PYEOF

echo "→ Applying known manual patches to JSON..."
uv run --frozen python - <<'PYEOF'
import json, pathlib

p = pathlib.Path("tools/openapi-schema/metrics-service.json")
data = json.loads(p.read_text())
paths = data["paths"]

# 1. Fix path param types: integer → string for unresolvable path params
target_ops = [
    ("/api/v1/dashboard_reports/report/{id}/", "get"),
    ("/api/v1/dashboard_reports/subscription_costs/{id}/", "put"),
    ("/api/v1/dashboard_reports/subscription_costs/{id}/", "patch"),
]
for path, method in target_ops:
    if path in paths and method in paths[path]:
        for param in paths[path][method].get("parameters", []):
            if param.get("name") == "id" and param.get("schema", {}).get("type") == "integer":
                param["schema"]["type"] = "string"
                param.pop("description", None)

# 2. Add /api/v1/feature_flags_state/ endpoint if missing
flag_state_path = "/api/v1/feature_flags_state/"
if flag_state_path not in paths:
    entry = {
        "get": {
            "operationId": "feature_flags_state_retrieve",
            "description": "A view class for displaying feature flags",
            "tags": ["feature_flags_state"],
            "security": [{"cookieAuth": []}, {"basicAuth": []}],
            "responses": {
                "200": {
                    "content": {
                        "application/json": {
                            "schema": {"type": "object", "additionalProperties": {}},
                            "examples": {
                                "Featureflags": {
                                    "value": {"FLAG1": True, "FLAG2": False},
                                    "summary": "featureflags"
                                }
                            }
                        }
                    },
                    "description": ""
                }
            },
            "x-ai-description": "Retrieve single feature flags state"
        }
    }
    new_paths = {}
    for k, v in paths.items():
        new_paths[k] = v
        if k == "/api/v1/feature_flags/{id}/":
            new_paths[flag_state_path] = entry
    data["paths"] = paths = new_paths

# 3. Fix org disassociation: remove requestBody, simplify 200 response
disassoc_path = "/api/v1/teams/{id}/organization/disassociate/"
if disassoc_path in paths:
    for method in ("post", "put", "patch"):
        if method in paths[disassoc_path]:
            op = paths[disassoc_path][method]
            op.pop("requestBody", None)
            if "200" in op.get("responses", {}):
                op["responses"]["200"] = {"description": "No response body"}

# 4. Remove OrganizationDisassociate component schemas
for key in ["OrganizationDisassociate", "OrganizationDisassociateRequest"]:
    data["components"]["schemas"].pop(key, None)

p.write_text(json.dumps(data, indent=2) + "\n")
print("  JSON patches applied")
PYEOF

echo ""
echo "Done. Review:"
echo "  git diff $YAML_OUT"
echo "  git diff $JSON_OUT"
echo ""
echo "Commit both files if the diff looks correct."
