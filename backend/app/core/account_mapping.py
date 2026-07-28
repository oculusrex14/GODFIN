from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.app_setting import AppSetting

SENDER_MAPPING_KEY = "sender_account_mappings"


def load_sender_mappings(db: Session) -> list[dict[str, str]]:
    setting = db.query(AppSetting).filter_by(key=SENDER_MAPPING_KEY).first()
    if not setting or not setting.value:
        return []
    try:
        value = json.loads(setting.value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []

    mappings: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        pattern = str(item.get("sender_pattern", "")).strip().lower()
        profile = str(item.get("parser_profile", "")).strip().lower()
        account_id = str(item.get("account_id", "")).strip()
        if pattern and profile and account_id:
            mappings.append(
                {
                    "sender_pattern": pattern,
                    "parser_profile": profile,
                    "account_id": account_id,
                }
            )
    return mappings


def save_sender_mappings(
    db: Session,
    mappings: list[dict[str, Any]],
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in mappings:
        pattern = str(item.get("sender_pattern", "")).strip().lower()
        profile = str(item.get("parser_profile", "")).strip().lower()
        account_id = str(item.get("account_id", "")).strip()
        if not pattern or not profile or not account_id or pattern in seen:
            continue
        account = db.query(Account).filter_by(id=account_id, is_active=True).first()
        if not account:
            raise ValueError(f"Active account not found: {account_id}")
        seen.add(pattern)
        normalized.append(
            {
                "sender_pattern": pattern,
                "parser_profile": profile,
                "account_id": account_id,
            }
        )

    setting = db.query(AppSetting).filter_by(key=SENDER_MAPPING_KEY).first()
    encoded = json.dumps(normalized, separators=(",", ":"), sort_keys=True)
    if setting:
        setting.value = encoded
    else:
        db.add(AppSetting(key=SENDER_MAPPING_KEY, value=encoded))
    db.flush()
    return normalized


def resolve_sender_mapping(
    db: Session,
    sender: str,
) -> Optional[dict[str, str]]:
    normalized_sender = sender.strip().lower()
    matches = [
        mapping
        for mapping in load_sender_mappings(db)
        if mapping["sender_pattern"] in normalized_sender
    ]
    matches.sort(key=lambda item: len(item["sender_pattern"]), reverse=True)
    for mapping in matches:
        account = (
            db.query(Account)
            .filter_by(id=mapping["account_id"], is_active=True)
            .first()
        )
        if account:
            return mapping
    return None


def resolve_profile_account(
    db: Session,
    parser_profile: str,
) -> Optional[str]:
    for mapping in load_sender_mappings(db):
        if mapping["parser_profile"] != parser_profile:
            continue
        account = (
            db.query(Account)
            .filter_by(id=mapping["account_id"], is_active=True)
            .first()
        )
        if account:
            return account.id
    return None
