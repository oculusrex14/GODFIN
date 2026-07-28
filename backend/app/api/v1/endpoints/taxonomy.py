from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.core.taxonomy import TAXONOMY

router = APIRouter()


@router.get("/taxonomy")
def get_taxonomy(
    _user: bool = Depends(get_current_user),
):
    """Return the canonical category taxonomy used by every client."""
    return {
        "categories": TAXONOMY,
        "category_names": list(TAXONOMY.keys()),
    }
