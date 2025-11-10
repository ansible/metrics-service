#!/usr/bin/env python
"""Test AWX database connection"""

import subprocess
import sys

try:
    result = subprocess.run(
        [  # noqa: S607
            "docker",
            "exec",
            "metrics-service-postgres",
            "psql",
            "-U",
            "metrics_service",
            "-d",
            "awx",
            "-c",
            "SELECT COUNT(*) FROM main_job",
        ],
        capture_output=True,
        text=True,
        check=True,
        shell=False,
    )

    # Parse the count from psql output
    lines = result.stdout.strip().split("\n")
    count_line = [line for line in lines if line.strip().isdigit()]
    if count_line:
        count = count_line[0].strip()
        sys.stdout.write("AWX database connection successful!\n")
        sys.stdout.write(f"Found {count} jobs in main_job table\n")
    else:
        sys.stdout.write("Could not parse job count\n")
        sys.stdout.write(result.stdout)

except subprocess.CalledProcessError as e:
    sys.stderr.write(f"AWX database connection failed: {e}\n")
    sys.stderr.write(e.stderr)
    sys.exit(1)
except Exception as e:
    sys.stderr.write(f"Error: {e}\n")
    sys.exit(1)
