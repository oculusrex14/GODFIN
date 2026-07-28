"""Stable encryption-key management for local secrets.

Resolution order is deliberately fixed:
1. ``ENCRYPTION_KEY`` environment variable
2. macOS Keychain
3. a mode-0600 local key file

If encrypted data already exists, GODFIN never generates a replacement key:
doing so would silently strand the user's Gmail and LLM credentials.
"""
from __future__ import annotations

import base64
import getpass
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

KEYCHAIN_SERVICE = "dev.godfin.encryption-key"
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_KEY_FILE = _BACKEND_ROOT / "data" / ".encryption_key"
_TOKEN_FILE = _BACKEND_ROOT / "data" / "gmail_token.json"

_ENCRYPTION_KEY: Optional[bytes] = None
_KEY_SOURCE: Optional[str] = None


class EncryptionError(RuntimeError):
    """Base class for actionable encryption failures."""


class EncryptionKeyUnavailable(EncryptionError):
    """Raised when encrypted data exists but its key cannot be located."""


class SecretDecryptionError(EncryptionError):
    """Raised when a stored secret cannot be decrypted with the current key."""


def _key_file_path() -> Path:
    configured = os.environ.get("GODFIN_ENCRYPTION_KEY_FILE")
    return Path(configured).expanduser() if configured else _DEFAULT_KEY_FILE


def _normalize_key(value: str | bytes) -> bytes:
    """Accept a normal Fernet key and the legacy double-base64 export format."""
    raw = value.encode("ascii") if isinstance(value, str) else value
    raw = raw.strip()
    candidates = [raw]
    try:
        decoded = base64.urlsafe_b64decode(raw)
        if len(decoded) == 32:
            candidates.append(base64.urlsafe_b64encode(decoded))
        elif decoded:
            candidates.append(decoded)
    except Exception:
        pass

    for candidate in candidates:
        try:
            Fernet(candidate)
            return candidate
        except (TypeError, ValueError):
            continue
    raise EncryptionError("Encryption key is not a valid Fernet key")


def _load_from_env() -> Optional[bytes]:
    value = os.environ.get("ENCRYPTION_KEY")
    return _normalize_key(value) if value else None


def _keychain_enabled() -> bool:
    return (
        sys.platform == "darwin"
        and os.environ.get("GODFIN_DISABLE_KEYCHAIN", "").lower()
        not in {"1", "true", "yes"}
    )


def _load_from_keychain() -> Optional[bytes]:
    if not _keychain_enabled():
        return None
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-a",
            getpass.getuser(),
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if result.returncode != 0:
        return None
    return _normalize_key(result.stdout)


def _save_to_keychain(key: bytes) -> bool:
    if not _keychain_enabled():
        return False
    result = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-a",
            getpass.getuser(),
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
            key.decode("ascii"),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result.returncode == 0


def _load_from_file() -> Optional[bytes]:
    path = _key_file_path()
    if not path.exists():
        return None
    if path.is_symlink():
        raise EncryptionError("Encryption key file must not be a symbolic link")
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise EncryptionError("Encryption key file permissions must be 0600")
    return _normalize_key(path.read_bytes())


def _save_to_file(key: bytes) -> None:
    path = _key_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, key + b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def _database_candidates() -> list[Path]:
    raw_path = os.environ.get("DB_PATH", "godfin.db")
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return [path]
    candidates = [_BACKEND_ROOT / path, Path.cwd() / path]
    return list(dict.fromkeys(candidate.resolve() for candidate in candidates))


def _encrypted_values() -> list[str]:
    values: list[str] = []
    if _TOKEN_FILE.exists():
        try:
            payload = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
            for field in ("token", "refresh_token", "client_secret"):
                value = payload.get(field)
                if isinstance(value, str) and value:
                    values.append(value)
        except (OSError, json.JSONDecodeError):
            # A malformed credential file still counts as sensitive state that
            # should not be overwritten with a newly generated key.
            values.append("<unreadable-gmail-token>")

    for db_path in _database_candidates():
        if not db_path.exists():
            continue
        try:
            connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                table_exists = connection.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name='llm_configurations'"
                ).fetchone()
                if table_exists:
                    rows = connection.execute(
                        "SELECT api_key, oauth_token, oauth_refresh_token "
                        "FROM llm_configurations"
                    ).fetchall()
                    values.extend(
                        value
                        for row in rows
                        for value in row
                        if isinstance(value, str) and value
                    )
                app_settings_exists = connection.execute(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name='app_settings'"
                ).fetchone()
                if app_settings_exists:
                    license_row = connection.execute(
                        "SELECT value FROM app_settings WHERE key='license_key'"
                    ).fetchone()
                    if license_row and isinstance(license_row[0], str) and license_row[0]:
                        values.append(license_row[0])
            finally:
                connection.close()
        except sqlite3.Error:
            continue
    return values


def encrypted_data_exists() -> bool:
    return bool(_encrypted_values())


def _get_encryption_key() -> bytes:
    global _ENCRYPTION_KEY, _KEY_SOURCE
    if _ENCRYPTION_KEY is not None:
        return _ENCRYPTION_KEY

    env_key = _load_from_env()
    if env_key is not None:
        _ENCRYPTION_KEY, _KEY_SOURCE = env_key, "environment"
        return env_key

    keychain_key = _load_from_keychain()
    if keychain_key is not None:
        _ENCRYPTION_KEY, _KEY_SOURCE = keychain_key, "macOS Keychain"
        return keychain_key

    file_key = _load_from_file()
    if file_key is not None:
        _ENCRYPTION_KEY, _KEY_SOURCE = file_key, "protected file"
        return file_key

    if encrypted_data_exists():
        raise EncryptionKeyUnavailable(
            "Encrypted credentials exist but their encryption key is missing. "
            "Restore ENCRYPTION_KEY, the GODFIN Keychain entry, or "
            "backend/data/.encryption_key. Otherwise re-authenticate Gmail "
            "and re-enter LLM keys."
        )

    generated = Fernet.generate_key()
    if _save_to_keychain(generated):
        _KEY_SOURCE = "macOS Keychain"
    else:
        _save_to_file(generated)
        _KEY_SOURCE = "protected file"
    _ENCRYPTION_KEY = generated
    return generated


def initialize_encryption() -> None:
    """Resolve the key during startup so failures happen before serving APIs."""
    _get_encryption_key()


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    encrypted = Fernet(_get_encryption_key()).encrypt(plaintext.encode("utf-8"))
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt(encrypted: str) -> str:
    if not encrypted:
        return ""
    try:
        token = base64.urlsafe_b64decode(encrypted)
        return Fernet(_get_encryption_key()).decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError) as exc:
        raise SecretDecryptionError(
            "Stored credential could not be decrypted. Re-authenticate Gmail "
            "or re-enter the affected LLM key."
        ) from exc


def get_encryption_health() -> dict:
    try:
        _get_encryption_key()
    except EncryptionKeyUnavailable as exc:
        return {
            "status": "missing",
            "source": None,
            "message": str(exc),
        }
    except EncryptionError as exc:
        return {
            "status": "error",
            "source": _KEY_SOURCE,
            "message": str(exc),
        }

    values = [value for value in _encrypted_values() if not value.startswith("<")]
    try:
        for value in values:
            decrypt(value)
    except SecretDecryptionError as exc:
        return {
            "status": "decrypt_failed",
            "source": _KEY_SOURCE,
            "message": str(exc),
        }
    return {
        "status": "ok",
        "source": _KEY_SOURCE,
        "message": "Encryption key is available and stored credentials decrypt.",
    }


def get_encryption_key_for_export() -> str:
    """Return the standard Fernet key representation for secure recovery."""
    return _get_encryption_key().decode("ascii")


def reset_encryption_state_for_tests() -> None:
    """Clear process-local state; tests use this to simulate an app restart."""
    global _ENCRYPTION_KEY, _KEY_SOURCE
    _ENCRYPTION_KEY = None
    _KEY_SOURCE = None
