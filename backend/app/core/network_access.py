"""Resolve whether GODFIN may listen beyond the local machine."""
from __future__ import annotations

import os
import sqlite3
from enum import Enum
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


class NetworkAccessMode(str, Enum):
    LOCAL = "local"
    LAN = "lan"


def _database_path() -> Path:
    configured = Path(os.environ.get("DB_PATH", "godfin.db")).expanduser()
    return configured if configured.is_absolute() else _BACKEND_ROOT / configured


def network_access_mode() -> NetworkAccessMode:
    override = os.environ.get("GODFIN_ALLOW_NETWORK_ACCESS")
    if override is not None:
        normalized = override.strip().lower()
        if normalized in _TRUE_VALUES | {NetworkAccessMode.LAN.value}:
            return NetworkAccessMode.LAN
        if normalized in _FALSE_VALUES | {NetworkAccessMode.LOCAL.value}:
            return NetworkAccessMode.LOCAL
        return NetworkAccessMode.LOCAL

    db_path = _database_path()
    if not db_path.exists():
        return NetworkAccessMode.LOCAL
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='app_settings'"
            ).fetchone()
            if not table_exists:
                return NetworkAccessMode.LOCAL
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key='allow_network_access'"
            ).fetchone()
            value = str(row[0]).strip().lower() if row else ""
            return (
                NetworkAccessMode.LAN
                if value in _TRUE_VALUES | {NetworkAccessMode.LAN.value}
                else NetworkAccessMode.LOCAL
            )
        finally:
            connection.close()
    except sqlite3.Error:
        return NetworkAccessMode.LOCAL


def network_access_enabled() -> bool:
    return network_access_mode() is NetworkAccessMode.LAN


def bind_host() -> str:
    return "0.0.0.0" if network_access_enabled() else "127.0.0.1"


if __name__ == "__main__":
    print(bind_host())
