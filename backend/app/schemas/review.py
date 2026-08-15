from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ReviewResolve(BaseModel):
    category: str = Field(..., min_length=1, max_length=50)
    subcategory: Optional[str] = Field(default=None, max_length=50)


class BatchResolveItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    category: str = Field(..., min_length=1, max_length=50)
    subcategory: Optional[str] = Field(default=None, max_length=50)


class BatchResolveRequest(BaseModel):
    items: list[BatchResolveItem] = Field(min_length=1, max_length=200)


class ReviewStats(BaseModel):
    queue_size: int
    auto_accepted: int
    soft_flagged: int


class ReviewQueueItem(BaseModel):
    id: str
    date: str
    merchant_raw: Optional[str]
    merchant_normalized: Optional[str]
    amount: float
    type: str
    instrument: str
    source: str
    is_income: bool
    semantic_type: str
    confidence: Optional[float]
    classification_source: Optional[str]
    classification_reason: str


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItem]
    total: int
    page: int
    page_size: int


class ReviewResolveResponse(BaseModel):
    status: str
    id: str
    category: str
    learned: bool
    reason: str


class BatchResolveResponse(BaseModel):
    resolved: int
    errors: list[str]
