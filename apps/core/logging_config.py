"""
Logging utilities for container-friendly output.

Provides a JSON formatter for structured logs suitable for aggregation
(Kubernetes, Splunk, ELK, etc.).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """
    Format log records as single-line JSON for container stdout.

    Output is one JSON object per line, suitable for log drivers and
    centralized logging.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        log_obj: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        if getattr(record, "request_id", None):
            log_obj["request_id"] = record.request_id
        return json.dumps(log_obj)
