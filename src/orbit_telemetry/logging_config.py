"""Structured JSON logs: one JSON object per line on stdout.

Containers should log to stdout and let the platform collect it (Twelve-Factor). In
Phase 7, Grafana Alloy ships these lines to Loki, where fields like `status` and
`request_id` can be queried with LogQL instead of grepping free text.
"""

import json
import logging
import sys
from datetime import UTC, datetime

# Attributes every LogRecord has; anything else was passed via `extra=` and is a field.
_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update({k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
