from __future__ import annotations

from datetime import date, time, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.taxonomy import TAXONOMY

VALID_CATEGORIES = set(TAXONOMY.keys())


class TransactionCreate(BaseModel):
    date: date
    time: Optional[time] = None
    merchant_raw: str = Field(..., min_length=1, max_length=255)
    amount: float = Field(..., gt=0)
    type: str = Field(..., pattern=r"^(debit|credit)$")
    instrument: str = Field(default="manual", max_length=20)
    account_id: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        if v is not None and v not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
            )
        return v


class TransactionUpdate(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        if v is not None and v not in VALID_CATEGORIES:
            raise ValueError("Invalid category")
        return v


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    date: date
    time: Optional[time] = None
    merchant_raw: Optional[str] = None
    merchant_normalized: Optional[str] = None
    amount: float
    type: str
    instrument: str
    account_id: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    confidence: Optional[float] = None
    classification_source: Optional[str] = None
    status: str
    source: str
    is_transfer: bool
    is_recurring: bool
    is_income: bool
    is_locked: bool
    is_split: bool
    tags: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class TransactionListResponse(BaseModel):
    items: List[TransactionResponse]
    total: int
    page: int
    page_size: int
