#!/usr/bin/env python3
"""Validate a final metrics-service Segment payload.

Usage:
    uv run python tools/validate_segment_contract.py path/to/payload.json
"""

import json
import sys
from pathlib import Path

from pydantic import ConfigDict, TypeAdapter, ValidationError, with_config

from apps.tasks.segment_types import FinalAnonymizedPayload

StrictPayload = with_config(ConfigDict(extra="forbid"))(FinalAnonymizedPayload)


def main() -> None:
    """Validate the JSON payload supplied on the command line."""
    if len(sys.argv) < 2:
        sys.stdout.write(f"Usage: {sys.argv[0]} path/to/payload.json\n")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    with json_path.open() as payload_file:
        data = json.load(payload_file)

    try:
        TypeAdapter(StrictPayload).validate_python(data, strict=True)
    except ValidationError as error:
        sys.stdout.write(f"Data: {json_path}\n\n")
        sys.stdout.write(f"ISSUES: {error.error_count()}\n")
        for item in error.errors():
            location = ".".join(str(part) for part in item["loc"])
            sys.stdout.write(f"  {location}: {item['msg']}\n")
        sys.exit(1)

    sys.stdout.write(f"Data: {json_path}\n")
    sys.stdout.write(f"Keys: {sorted(data.keys())}\n\n")
    sys.stdout.write("ALL CHECKS PASSED\n")


if __name__ == "__main__":
    main()
