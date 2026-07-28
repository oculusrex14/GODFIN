from __future__ import annotations

import pytest

from app.core.merchant_memory_service import upsert_merchant_memory
from app.models.merchant_memory import MerchantMemory


def test_shared_upsert_updates_one_row_on_conflict(db_session):
    upsert_merchant_memory(
        db_session,
        "Swiggy Food Order",
        "FOOD & DINING",
        "Food Delivery",
        0.8,
    )
    upsert_merchant_memory(
        db_session,
        "SWIGGY FOOD ORDER",
        "FOOD & DINING",
        "Restaurants",
        1.0,
    )
    db_session.commit()

    rows = db_session.query(MerchantMemory).all()
    assert len(rows) == 1
    assert rows[0].normalized_name == "SWIGGY FOOD ORDER"
    assert rows[0].times_seen == 2
    assert rows[0].subcategory == "Restaurants"
    assert rows[0].avg_confidence == pytest.approx(0.9)
