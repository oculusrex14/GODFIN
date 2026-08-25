from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.merchant_entity_service import (
    find_merchant_candidates,
    normalize_alias,
    promote_verified_memory,
)
from app.core.merchant_seed_catalog import REVIEWED_MERCHANT_CATALOG_V1
from app.core.startup_migrations import apply_additive_schema_updates
from app.models.merchant_enrichment import (
    MerchantEntity,
    MerchantIdentifier,
    SourceProvenance,
)
from app.models.merchant_memory import MerchantMemory
from app.seed import seed_reviewed_merchants


@pytest.fixture
def merchant_db(tmp_path):
    db_path = tmp_path / "merchant-search.db"
    engine = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    apply_additive_schema_updates(str(db_path))
    Session = sessionmaker(bind=engine)
    with Session() as session:
        seed_reviewed_merchants(session)
        yield session
    engine.dispose()


def test_reviewed_catalog_is_exactly_100_public_canonical_entries(merchant_db):
    assert len(REVIEWED_MERCHANT_CATALOG_V1) == 100
    assert merchant_db.query(MerchantEntity).count() == 100
    assert merchant_db.query(SourceProvenance).count() == 1

    seeded_names = {item[0] for item in REVIEWED_MERCHANT_CATALOG_V1}
    assert "Swiggy" in seeded_names
    assert all(item[2] != "INCOME" for item in REVIEWED_MERCHANT_CATALOG_V1)


def test_exact_verified_alias_is_auto_acceptable_but_lexical_match_is_review_only(
    merchant_db,
):
    exact = find_merchant_candidates(merchant_db, "Swiggy")
    lexical = find_merchant_candidates(merchant_db, "Swiggy Food")

    assert exact[0].canonical_name == "Swiggy"
    assert exact[0].source == "exact_alias"
    assert exact[0].is_auto_acceptable is True
    assert lexical[0].canonical_name in {"Swiggy", "Swiggy Instamart"}
    assert lexical[0].source == "fts_character"
    assert lexical[0].score <= 0.84
    assert lexical[0].is_auto_acceptable is False


def test_personal_vpa_is_never_returned_as_a_global_identifier(merchant_db):
    entity = merchant_db.query(MerchantEntity).filter_by(canonical_name="Swiggy").one()
    merchant_db.add(
        MerchantIdentifier(
            id=str(uuid.uuid4()),
            entity_id=entity.id,
            identifier_type="vpa",
            normalized_value="9999999999@upi",
            source_bank="",
            is_person=True,
            is_verified=True,
        )
    )
    merchant_db.commit()

    candidates = find_merchant_candidates(
        merchant_db,
        "UNRELATED PRIVATE TRANSFER",
        vpa="9999999999@upi",
    )

    assert candidates == []


def test_verified_memory_promotion_requires_repeated_high_confidence_confirmation(
    merchant_db,
):
    weak = MerchantMemory(
        raw_string="LOCAL BOOK STORE",
        normalized_name="LOCAL BOOK STORE",
        category="EDUCATION",
        subcategory="Courses/Books",
        times_seen=1,
        avg_confidence=1.0,
    )
    with pytest.raises(ValueError, match="two confirmed uses"):
        promote_verified_memory(merchant_db, weak, source_label="Owner review")

    confirmed = MerchantMemory(
        raw_string="LOCAL BOOK STORE",
        normalized_name="LOCAL BOOK STORE",
        category="EDUCATION",
        subcategory="Courses/Books",
        times_seen=3,
        avg_confidence=0.96,
    )
    entity = promote_verified_memory(
        merchant_db,
        confirmed,
        source_label="Owner review",
        reviewed_at=datetime(2026, 8, 24),
    )
    merchant_db.commit()

    assert entity.is_verified is True
    result = find_merchant_candidates(merchant_db, normalize_alias("LOCAL BOOK STORE"))
    assert result[0].canonical_name == "Local Book Store"
    assert result[0].is_auto_acceptable is True


def test_fts_trigger_tracks_alias_updates_and_deletes(merchant_db):
    alias_row = merchant_db.execute(
        text("SELECT id FROM merchant_aliases WHERE normalized_alias='SWIGGY'")
    ).scalar_one()
    merchant_db.execute(
        text("UPDATE merchant_aliases SET normalized_alias='SWIGGY TEST' WHERE id=:id"),
        {"id": alias_row},
    )
    merchant_db.commit()
    assert merchant_db.execute(
        text(
            "SELECT count(*) FROM merchant_alias_fts "
            "WHERE merchant_alias_fts MATCH 'TEST'"
        )
    ).scalar_one() == 1

    merchant_db.execute(text("DELETE FROM merchant_aliases WHERE id=:id"), {"id": alias_row})
    merchant_db.commit()
    assert merchant_db.execute(
        text(
            "SELECT count(*) FROM merchant_alias_fts "
            "WHERE merchant_alias_fts MATCH 'TEST'"
        )
    ).scalar_one() == 0
