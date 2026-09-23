#!/usr/bin/env python3
"""Generate an OpenAPI schema for the final Segment payload.

Usage:
    uv run python tools/generate_segment_schema.py
    uv run python tools/generate_segment_schema.py --output segment-schema.yaml
"""

import argparse
import sys

import yaml
from pydantic import ConfigDict, TypeAdapter, with_config

from apps.tasks.segment_types import FinalAnonymizedPayload

StrictPayload = with_config(ConfigDict(extra="forbid"))(FinalAnonymizedPayload)


def main() -> None:
    """Generate and print or write the final Segment payload schema."""
    parser = argparse.ArgumentParser(description="Generate an OpenAPI schema for the final Segment payload.")
    parser.add_argument("-o", "--output", help="Write the schema to this file instead of stdout")
    args = parser.parse_args()

    schema = TypeAdapter(StrictPayload).json_schema(ref_template="#/components/schemas/{model}")
    definitions = schema.pop("$defs", {})
    openapi = {
        "openapi": "3.1.0",
        "info": {"title": "Metrics Service Segment Anonymized Payload", "version": "1.0.0"},
        "paths": {},
        "components": {"schemas": {"FinalAnonymizedPayload": schema, **definitions}},
    }
    output = yaml.safe_dump(openapi, default_flow_style=False, sort_keys=False)

    if args.output:
        with open(args.output, "w") as schema_file:
            schema_file.write(output)
        sys.stderr.write(f"Schema written to {args.output}\n")
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
