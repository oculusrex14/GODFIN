from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.v1.entitlements import conditional_entitlement, enforce_feature
from app.core.account_mapping import load_sender_mappings, save_sender_mappings
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.errors import InvalidOperationError
from app.core.parsers import supported_parser_profiles
from app.models.account import Account

router = APIRouter()


class AccountRouting(BaseModel):
    sender_pattern: str = Field(min_length=3, max_length=255)
    parser_profile: str = Field(pattern=r"^[a-z0-9_]+$")


class AccountCreate(BaseModel):
    bank: str = Field(min_length=2, max_length=50)
    account_type: str = Field(pattern=r"^(savings|credit_card)$")
    last_4_digits: str = Field(pattern=r"^\d{4}$")
    nickname: Optional[str] = Field(default=None, max_length=100)
    routing: Optional[AccountRouting] = None

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
    routing: Optional[AccountRouting] = None

    @field_validator("bank")
    @classmethod
    def normalize_bank(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper() if value else value


class SenderMapping(BaseModel):
    sender_pattern: str = Field(min_length=3, max_length=255)
    parser_profile: str = Field(pattern=r"^[a-z0-9_]+$")
    account_id: str = Field(min_length=1, max_length=36)


class SenderMappingsUpdate(BaseModel):
    mappings: list[SenderMapping] = Field(max_length=100)


class AccountResponse(BaseModel):
    id: str
    bank: str
    account_type: str
    last_4_digits: str
    nickname: Optional[str] = None
    is_active: bool


class ParserProfileResponse(BaseModel):
    profile: str
    bank: str
    account_type: str
    statement_type: str
    formats: list[str]


def _account_dict(account: Account) -> dict:
    return {
        "id": account.id,
        "bank": account.bank,
        "account_type": account.account_type,
        "last_4_digits": account.last_4_digits,
        "nickname": account.nickname,
        "is_active": account.is_active,
    }


def _apply_account_routing(
    db: Session,
    account: Account,
    routing: AccountRouting | None,
) -> None:
    mappings = [
        mapping
        for mapping in load_sender_mappings(db)
        if mapping["account_id"] != account.id
    ]
    if routing is None:
        save_sender_mappings(db, mappings)
        return

    profile = next(
        (
            item
            for item in supported_parser_profiles()
            if item["profile"] == routing.parser_profile
        ),
        None,
    )
    if not profile:
        raise ValueError("The selected parser profile is not available.")
    if (
        profile["bank"] != account.bank
        or profile["account_type"] != account.account_type
    ):
        raise ValueError(
            "The parser profile must match the account bank and account type."
        )
    mappings.append(
        {
            "sender_pattern": routing.sender_pattern,
            "parser_profile": routing.parser_profile,
            "account_id": account.id,
        }
    )
    save_sender_mappings(db, mappings)


@router.get("", response_model=list[AccountResponse])
def list_accounts(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    query = db.query(Account)
    if not include_inactive:
        query = query.filter_by(is_active=True)
    return [_account_dict(account) for account in query.order_by(Account.created_at).all()]


@router.get("/parser-profiles", response_model=list[ParserProfileResponse])
def list_parser_profiles(_user: bool = Depends(get_current_user)):
    return supported_parser_profiles()


@router.get("/sender-mappings", response_model=list[SenderMapping])
def list_account_sender_mappings(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    return load_sender_mappings(db)


@router.put("/sender-mappings", response_model=list[SenderMapping])
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
        raise InvalidOperationError(
            code="ACCOUNT_ROUTING_INVALID",
            message="One or more sender-routing values are invalid.",
            hint="Check the selected account, sender pattern, and parser profile.",
        ) from exc
    db.commit()
    return mappings


@router.post("", response_model=AccountResponse, status_code=201)
@conditional_entitlement("multi_bank")
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
    try:
        db.flush()
        if body.routing is not None:
            _apply_account_routing(db, account, body.routing)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise InvalidOperationError(
            code="ACCOUNT_ROUTING_INVALID",
            message="The account could not be saved because its routing is invalid.",
            hint="Check the sender pattern and parser profile, then try again.",
        ) from exc
    db.refresh(account)
    return _account_dict(account)


@router.patch("/{account_id}", response_model=AccountResponse)
@conditional_entitlement("multi_bank")
def update_account(
    account_id: str,
    body: AccountUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    account = db.query(Account).filter_by(id=account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    values = body.model_dump(exclude_unset=True, exclude={"routing"})
    next_bank = values.get("bank", account.bank)
    if next_bank != "HDFC":
        enforce_feature(db, "multi_bank")
    if "nickname" in values and values["nickname"]:
        values["nickname"] = values["nickname"].strip()
    for key, value in values.items():
        setattr(account, key, value)
    try:
        db.flush()
        if "routing" in body.model_fields_set:
            _apply_account_routing(db, account, body.routing)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise InvalidOperationError(
            code="ACCOUNT_ROUTING_INVALID",
            message="The account could not be updated because its routing is invalid.",
            hint="Check the sender pattern and parser profile, then try again.",
        ) from exc
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
