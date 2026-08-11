from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
from datetime import datetime, timezone
from pathlib import Path


_BEARER = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+\-/=]{8,}")
_SECRET_FIELD = re.compile(
    r"(?i)(\b(?:access[_-]?token|refresh[_-]?token|api[_-]?key|password|"
    r"secret|authorization|code_verifier)\b\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_SECRET_QUERY = re.compile(
    r"(?i)([?&](?:code|token|secret|key|state|password)=)[^&#\s]+"
)
_EMAIL = re.compile(r"(?i)\b[a-z0-9._%+\-]{1,64}@[a-z0-9.\-]{2,80}\.[a-z]{2,20}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s\-]?)?[6-9]\d{9}(?!\d)")
_LONG_NUMBER = re.compile(r"(?<!\d)\d{8,19}(?!\d)")
_UNIX_PATH = re.compile(
    r"(?<![a-zA-Z0-9])/(?:Users|home|private|var/folders|tmp)/[^\s\"']+"
)
_WINDOWS_PATH = re.compile(r"(?i)\b[a-z]:\\(?:[^\s\"']+\\)*[^\s\"']+")


def redact_log_text(value: object) -> str:
    """Remove credentials, direct identifiers, and private filesystem paths."""
    text = str(value or "")
    text = _BEARER.sub("Bearer <redacted>", text)
    text = _SECRET_FIELD.sub(r"\1<redacted>", text)
    text = _SECRET_QUERY.sub(r"\1<redacted>", text)
    text = _EMAIL.sub("<email-redacted>", text)
    text = _PHONE.sub("<phone-redacted>", text)
    text = _LONG_NUMBER.sub("<number-redacted>", text)
    text = _UNIX_PATH.sub("<local-path>", text)
    text = _WINDOWS_PATH.sub("<local-path>", text)
    return text


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'module': record.module,
            'message': redact_log_text(record.getMessage()),
        }
        for key in ("request_id", "operation_id", "error_code", "cause_type"):
            value = getattr(record, key, None)
            if value:
                log_entry[key] = redact_log_text(value)
        if record.exc_info and record.exc_info[0]:
            log_entry['exception_type'] = record.exc_info[0].__name__
            log_entry['exception'] = redact_log_text(
                self.formatException(record.exc_info)
            )
        return json.dumps(log_entry)


class RedactingTextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_log_text(super().format(record))


def _default_log_directory() -> Path:
    configured = os.environ.get("GODFIN_LOG_DIR")
    if configured:
        return Path(configured).expanduser()
    from app.core.config import settings

    return settings.database_path.parent / "logs"


def setup_logging(log_dir: str | Path | None = None) -> None:
    """Configure structured JSON logging with rotation."""
    directory = Path(log_dir).expanduser() if log_dir else _default_log_directory()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    log_path = directory / 'godfin.log'

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_godfin_handler", False):
            root.removeHandler(existing)
            existing.close()

    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
    )
    handler._godfin_handler = True
    handler.setFormatter(JSONFormatter())
    try:
        log_path.chmod(0o600)
    except OSError:
        pass

    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # Also keep console output for dev
    console = logging.StreamHandler()
    console._godfin_handler = True
    console.setLevel(logging.WARNING)
    console.setFormatter(RedactingTextFormatter('%(levelname)s: %(message)s'))
    root.addHandler(console)
