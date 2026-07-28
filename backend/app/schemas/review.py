from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ReviewResolve(BaseModel):
    category: str = Field(..., min_length=1)
    subcategory: Optional[str] = None


class BatchResolveItem(BaseModel):
    id: str
    category: str = Field(..., min_length=1)
    subcategory: Optional[str] = None


class BatchResolveRequest(BaseModel):
    items: list[BatchResolveItem]


class ReviewStats(BaseModel):
    queue_size: int
    auto_accepted: int
    soft_flagged: int
