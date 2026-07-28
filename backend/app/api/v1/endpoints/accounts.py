from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.v1.endpoints.license import enforce_feature
from app.core.account_mapping import load_sender_mappings, save_sender_mappings
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.parsers import supported_parser_profiles
from app.models.account import Account

router = APIRouter()


class AccountCreate(BaseModel):
    bank: str = Field(min_length=2, max_length=50)
    account_type: str = Field(pattern=r"^(savings|credit_card)$")
    last_4_digits: str = Field(pattern=r"^\d{4}$")
    nickname: Optional[str] = Field(default=None, max_length=100)

    @field_validator("bank")
    @classmethod
    def normalize_bank(cls, value: str) -> str:
        return value.strip().upper()


class AccountUpdate(BaseModel):
    bank: Optional[str] = Field(default=None, min_length=2, max_length=50)
    account_type: Optional[str] = Field(
        default=None,
        pattern=r"^(savings|credit_card)$",
    )
    last_4_digits: Optional[str] = Field(default=None, pattern=r"^\d{4}$")
    nickname: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None

    @field_validator("bank")
    @classmethod
    def normalize_bank(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper() if value else value


class SenderMapping(BaseModel):
    sender_pattern: str = Field(min_length=3, max_length=255)
    parser_profile: str = Field(pattern=r"^[a-z0-9_]+$")
    account_id: str = Field(min_length=1, max_length=36)


class SenderMappingsUpdate(BaseModel):
    mappings: list[SenderMapping]


def _account_dict(account: Account) -> dict:
    return {
        "id": account.id,
        "bank": account.bank,
        "account_type": account.account_type,
        "last_4_digits": account.last_4_digits,
        "nickname": account.nickname,
        "is_active": account.is_active,
    }


@router.get("")
def list_accounts(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    query = db.query(Account)
    if not include_inactive:
        query = query.filter_by(is_active=True)
    return [_account_dict(account) for account in query.order_by(Account.created_at).all()]


@router.get("/parser-profiles")
def list_parser_profiles(_user: bool = Depends(get_current_user)):
    return supported_parser_profiles()


@router.get("/sender-mappings")
def list_account_sender_mappings(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return load_sender_mappings(db)


@router.put("/sender-mappings")
def replace_account_sender_mappings(
    body: SenderMappingsUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        mappings = save_sender_mappings(
            db,
            [mapping.model_dump() for mapping in body.mappings],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return mappings


@router.post("", status_code=201)
def create_account(
    body: AccountCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    if body.bank != "HDFC":
        enforce_feature(db, "multi_bank")
    duplicate = (
        db.query(Account)
        .filter_by(
            bank=body.bank,
            account_type=body.account_type,
            last_4_digits=body.last_4_digits,
            is_active=True,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="This account already exists")

    account = Account(
        id=str(uuid.uuid4()),
        bank=body.bank,
        account_type=body.account_type,
        last_4_digits=body.last_4_digits,
        nickname=body.nickname.strip() if body.nickname else None,
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return _account_dict(account)


@router.patch("/{account_id}")
def update_account(
    account_id: str,
    body: AccountUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    account = db.query(Account).filter_by(id=account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    values = body.model_dump(exclude_unset=True)
    next_bank = values.get("bank", account.bank)
    if next_bank != "HDFC":
        enforce_feature(db, "multi_bank")
    if "nickname" in values and values["nickname"]:
        values["nickname"] = values["nickname"].strip()
    for key, value in values.items():
        setattr(account, key, value)
    db.commit()
    db.refresh(account)
    return _account_dict(account)


@router.delete("/{account_id}", status_code=204)
def deactivate_account(
    account_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    account = db.query(Account).filter_by(id=account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.is_active = False
    remaining = [
        mapping
        for mapping in load_sender_mappings(db)
        if mapping["account_id"] != account_id
    ]
    save_sender_mappings(db, remaining)
    db.commit()
    return Response(status_code=204)
