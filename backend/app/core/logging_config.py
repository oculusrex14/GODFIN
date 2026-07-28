from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'module': record.module,
            'message': record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging(log_dir: str = 'logs') -> None:
    """Configure structured JSON logging with rotation."""
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'godfin.log')

    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
    )
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # Also keep console output for dev
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    root.addHandler(console)
