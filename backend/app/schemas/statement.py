from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


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
    expected_amount: Optional[float] = None
    frequency: str = Field(default='monthly', pattern=r'^(monthly|biweekly|irregular)$')


class IncomeSourceUpdate(BaseModel):
    source_name: Optional[str] = Field(None, min_length=1, max_length=100)
    expected_amount: Optional[float] = None
    frequency: Optional[str] = Field(None, pattern=r'^(monthly|biweekly|irregular)$')
    is_active: Optional[bool] = None
