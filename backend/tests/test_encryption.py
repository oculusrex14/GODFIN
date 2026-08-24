from __future__ import annotations

import json
import os
import sqlite3

import pytest

from app.core import encryption
from app.core.llm_runtime import provider_from_config
from app.models.llm_config import LLMConfiguration


@pytest.fixture(autouse=True)
def isolated_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("GODFIN_DISABLE_KEYCHAIN", "1")
    monkeypatch.setenv("GODFIN_ENCRYPTION_KEY_FILE", str(tmp_path / ".encryption_key"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "empty.db"))
    monkeypatch.setattr(encryption, "_TOKEN_FILE", tmp_path / "gmail_token.json")
    encryption.reset_encryption_state_for_tests()
    yield
    encryption.reset_encryption_state_for_tests()


def test_encryption_key_survives_restart(tmp_path):
    encrypted = encryption.encrypt("local-secret")
    key_file = tmp_path / ".encryption_key"
    assert key_file.exists()
    assert key_file.stat().st_mode & 0o777 == 0o600

    encryption.reset_encryption_state_for_tests()
    assert encryption.decrypt(encrypted) == "local-secret"


def test_keychain_save_uses_stdin_and_an_empty_application_acl(monkeypatch):
    calls = []
    monkeypatch.delenv("GODFIN_DISABLE_KEYCHAIN", raising=False)
    monkeypatch.setattr(encryption.sys, "platform", "darwin")

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(encryption.subprocess, "run", fake_run)
    key = b"private-fernet-key"

    assert encryption._save_to_keychain(key) is True
    arguments, options = calls[0]
    assert key.decode("ascii") not in arguments
    assert arguments[-3:] == ["-T", "", "-w"]
    assert options["input"] == "private-fernet-key\n"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_key_file_save_never_follows_a_symlink(tmp_path):
    target = tmp_path / "outside-key"
    target.write_text("preserve-me", encoding="utf-8")
    key_file = tmp_path / ".encryption_key"
    key_file.symlink_to(target)

    with pytest.raises(encryption.EncryptionError, match="symbolic link"):
        encryption._save_to_file(b"replacement")

    assert target.read_text(encoding="utf-8") == "preserve-me"


def test_missing_key_fails_when_encrypted_credentials_exist(tmp_path):
    token_file = tmp_path / "gmail_token.json"
    token_file.write_text(json.dumps({"refresh_token": "encrypted-value"}))
    encryption.reset_encryption_state_for_tests()

    with pytest.raises(encryption.EncryptionKeyUnavailable):
        encryption.initialize_encryption()
    assert not (tmp_path / ".encryption_key").exists()


def test_pending_gmail_oauth_verifier_counts_as_encrypted_state(tmp_path, monkeypatch):
    database = tmp_path / "oauth-attempt.db"
    monkeypatch.setenv("DB_PATH", str(database))
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE gmail_oauth_attempts ("
            "code_verifier_encrypted TEXT NOT NULL, consumed_at DATETIME)"
        )
        connection.execute(
            "INSERT INTO gmail_oauth_attempts VALUES (?, NULL)",
            ("encrypted-verifier",),
        )
        connection.commit()
    finally:
        connection.close()

    assert encryption.encrypted_data_exists() is True


def test_llm_provider_receives_plaintext_after_restart(monkeypatch):
    config = LLMConfiguration(
        provider="openai",
        auth_method="openapi",
        model="gpt-test",
        api_key=encryption.encrypt("plain-api-key"),
        is_active=True,
    )
    encryption.reset_encryption_state_for_tests()
    received = {}

    class Provider:
        pass

    def fake_create_provider(**kwargs):
        received.update(kwargs)
        return Provider()

    monkeypatch.setattr("app.core.llm_runtime.create_provider", fake_create_provider)
    provider = provider_from_config(config)

    assert isinstance(provider, Provider)
    assert received["api_key"] == "plain-api-key"
    assert config.api_key != "plain-api-key"
