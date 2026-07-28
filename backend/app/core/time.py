from __future__ import annotations

from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    """UTC timestamp compatible with GODFIN's existing naïve SQLite columns."""

    return datetime.now(timezone.utc).replace(tzinfo=None)
