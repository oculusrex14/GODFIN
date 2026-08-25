"""SQLite-native merchant candidate retrieval with provenance and abstention."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.time import utcnow_naive
from app.models.merchant_enrichment import (
    MerchantAlias,
    MerchantEntity,
    MerchantIdentifier,
    SourceProvenance,
)
from app.models.merchant_memory import MerchantMemory


@dataclass(frozen=True)
class MerchantCandidate:
    entity_id: str
    canonical_name: str
    category: str | None
    subcategory: str | None
    source: str
    score: float
    is_auto_acceptable: bool


def normalize_alias(value: str) -> str:
    return " ".join(re.findall(r"[A-Z0-9]+", (value or "").upper()))[:255]


def _ngrams(value: str, minimum: int = 3, maximum: int = 5) -> set[str]:
    compact = re.sub(r"[^A-Z0-9]", "", value.upper())
    grams: set[str] = set()
    for size in range(minimum, maximum + 1):
        grams.update(compact[index:index + size] for index in range(len(compact) - size + 1))
    return grams


def character_similarity(left: str, right: str) -> float:
    left_grams = _ngrams(left)
    right_grams = _ngrams(right)
    if not left_grams or not right_grams:
        return 1.0 if normalize_alias(left) == normalize_alias(right) else 0.0
    return len(left_grams & right_grams) / len(left_grams | right_grams)


def _candidate(entity: MerchantEntity, *, source: str, score: float, auto: bool) -> MerchantCandidate:
    return MerchantCandidate(
        entity_id=entity.id,
        canonical_name=entity.canonical_name,
        category=entity.category,
        subcategory=entity.subcategory,
        source=source,
        score=max(0.0, min(1.0, score)),
        is_auto_acceptable=auto and entity.is_verified,
    )


def find_merchant_candidates(
    db: Session,
    descriptor: str,
    *,
    source_bank: str | None = None,
    vpa: str | None = None,
    limit: int = 5,
) -> list[MerchantCandidate]:
    """Return verified exact matches first, then review-only lexical matches."""

    normalized = normalize_alias(descriptor)
    bank = (source_bank or "").strip().lower()
    if not normalized:
        return []

    if vpa:
        identifier = (
            db.query(MerchantIdentifier)
            .filter(
                MerchantIdentifier.identifier_type == "vpa",
                MerchantIdentifier.normalized_value == vpa.strip().lower(),
                MerchantIdentifier.source_bank.in_((bank, "")),
                MerchantIdentifier.is_verified.is_(True),
                MerchantIdentifier.is_person.is_(False),
            )
            .order_by(MerchantIdentifier.source_bank.desc())
            .first()
        )
        if identifier:
            entity = db.get(MerchantEntity, identifier.entity_id)
            if entity:
                return [_candidate(entity, source="exact_identifier", score=1.0, auto=True)]

    alias = (
        db.query(MerchantAlias)
        .filter(
            MerchantAlias.normalized_alias == normalized,
            MerchantAlias.source_bank.in_((bank, "")),
            MerchantAlias.is_verified.is_(True),
        )
        .order_by(MerchantAlias.source_bank.desc())
        .first()
    )
    if alias:
        entity = db.get(MerchantEntity, alias.entity_id)
        if entity:
            return [_candidate(entity, source="exact_alias", score=1.0, auto=True)]

    tokens = re.findall(r"[A-Z0-9]{2,}", normalized)
    if not tokens:
        return []
    fts_query = " OR ".join(f'"{token}"' for token in tokens[:12])
    rows = db.execute(
        text(
            "SELECT a.id AS alias_id, a.normalized_alias, a.entity_id, "
            "bm25(merchant_alias_fts) AS rank "
            "FROM merchant_alias_fts "
            "JOIN merchant_aliases a ON a.id = merchant_alias_fts.alias_id "
            "WHERE merchant_alias_fts MATCH :query "
            "AND a.is_verified = 1 AND a.source_bank IN (:bank, '') "
            "ORDER BY rank LIMIT :candidate_limit"
        ),
        {"query": fts_query, "bank": bank, "candidate_limit": max(10, limit * 4)},
    ).mappings().all()

    ranked: list[MerchantCandidate] = []
    seen: set[str] = set()
    for row in rows:
        entity_id = str(row["entity_id"])
        if entity_id in seen:
            continue
        entity = db.get(MerchantEntity, entity_id)
        if not entity:
            continue
        similarity = character_similarity(normalized, str(row["normalized_alias"]))
        if similarity < 0.28:
            continue
        seen.add(entity_id)
        ranked.append(
            _candidate(
                entity,
                source="fts_character",
                score=min(0.84, 0.50 + (0.40 * similarity)),
                auto=False,
            )
        )
    return sorted(ranked, key=lambda item: item.score, reverse=True)[:limit]


def promote_verified_memory(
    db: Session,
    memory: MerchantMemory,
    *,
    source_label: str,
    reviewed_at: datetime | None = None,
) -> MerchantEntity:
    """Explicit compatibility adapter; never called by background ingestion."""

    if memory.times_seen < 2 or memory.avg_confidence < 0.90:
        raise ValueError("Merchant memory needs two confirmed uses at 90% confidence")
    normalized = normalize_alias(memory.normalized_name)
    if not normalized:
        raise ValueError("Merchant memory has no usable alias")
    provenance = SourceProvenance(
        id=str(uuid.uuid4()),
        source_type="user_verified_memory",
        source_uri=None,
        source_label=source_label[:255],
        license_note="Local user-confirmed mapping; never uploaded automatically",
        reviewed_at=reviewed_at or utcnow_naive(),
    )
    db.add(provenance)
    entity = db.query(MerchantEntity).filter_by(canonical_name=normalized.title()).first()
    if not entity:
        entity = MerchantEntity(
            id=str(uuid.uuid4()),
            canonical_name=normalized.title(),
            entity_type="merchant",
            category=memory.category,
            subcategory=memory.subcategory,
            provenance_id=provenance.id,
            is_verified=True,
        )
        db.add(entity)
        db.flush()
    alias = (
        db.query(MerchantAlias)
        .filter_by(normalized_alias=normalized, source_bank="")
        .first()
    )
    if not alias:
        db.add(
            MerchantAlias(
                id=str(uuid.uuid4()),
                entity_id=entity.id,
                normalized_alias=normalized,
                source_bank="",
                alias_kind="descriptor",
                provenance_id=provenance.id,
                is_verified=True,
            )
        )
    return entity
