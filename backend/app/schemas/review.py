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
