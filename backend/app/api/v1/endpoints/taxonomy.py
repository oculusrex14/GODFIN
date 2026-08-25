from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.taxonomy import TAXONOMY

router = APIRouter()


class TaxonomyCategoryResponse(BaseModel):
    elasticity: Literal["fixed", "semi_flexible", "flexible", "none"]
    subcategories: list[str]
    confidence_threshold: float
    exclude_from_spend: Optional[bool] = None
    is_income: Optional[bool] = None


class TaxonomyResponse(BaseModel):
    categories: dict[str, TaxonomyCategoryResponse]
    category_names: list[str]


@router.get(
    "/taxonomy",
    response_model=TaxonomyResponse,
    response_model_exclude_unset=True,
)
def get_taxonomy(
    _user: bool = Depends(get_current_user),
):
    """Return the canonical category taxonomy used by every client."""
    return {
        "categories": TAXONOMY,
        "category_names": list(TAXONOMY.keys()),
    }
