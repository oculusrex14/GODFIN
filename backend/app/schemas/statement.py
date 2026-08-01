from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.financial import LegacyIncomeFrequency, PositiveMoney


class ReconcilePreview(BaseModel):
    matched: int
    possible: int
    new: int
    income_detected: int
    details: dict


class ImportRequest(BaseModel):
    import_new: bool = True
    import_possible: bool = False


class IncomeSourceCreate(BaseModel):
    source_name: str = Field(..., min_length=1, max_length=100)
    expected_amount: Optional[PositiveMoney] = None
    frequency: LegacyIncomeFrequency = 'monthly'


class IncomeSourceUpdate(BaseModel):
    source_name: Optional[str] = Field(None, min_length=1, max_length=100)
    expected_amount: Optional[PositiveMoney] = None
    frequency: Optional[LegacyIncomeFrequency] = None
    is_active: Optional[bool] = None
