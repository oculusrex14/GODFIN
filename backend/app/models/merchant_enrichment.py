from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow_naive


class SourceProvenance(Base):
    __tablename__ = "source_provenance"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_uri: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_label: Mapped[str] = mapped_column(String(255), nullable=False)
    license_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class MerchantEntity(Base):
    __tablename__ = "merchant_entities"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('merchant', 'processor', 'government', 'financial')",
            name="ck_merchant_entities_type",
        ),
        Index("ix_merchant_entities_category", "category"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    canonical_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default="merchant"
    )
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    provenance_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("source_provenance.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive
    )


class MerchantAlias(Base):
    __tablename__ = "merchant_aliases"
    __table_args__ = (
        UniqueConstraint(
            "normalized_alias",
            "source_bank",
            name="uq_merchant_alias_bank",
        ),
        CheckConstraint(
            "alias_kind IN ('canonical', 'descriptor', 'vpa_name', 'domain')",
            name="ck_merchant_aliases_kind",
        ),
        Index("ix_merchant_aliases_entity", "entity_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    entity_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("merchant_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    source_bank: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    alias_kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default="descriptor"
    )
    provenance_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("source_provenance.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class MerchantIdentifier(Base):
    __tablename__ = "merchant_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "identifier_type",
            "normalized_value",
            "source_bank",
            name="uq_merchant_identifier_bank",
        ),
        CheckConstraint(
            "identifier_type IN ('vpa', 'domain', 'mcc', 'processor_account')",
            name="ck_merchant_identifiers_type",
        ),
        Index("ix_merchant_identifiers_entity", "entity_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    entity_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("merchant_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(255), nullable=False)
    source_bank: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    provenance_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("source_provenance.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_person: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class ProcessorPattern(Base):
    __tablename__ = "processor_patterns"
    __table_args__ = (
        UniqueConstraint(
            "processor_name",
            "pattern_type",
            "pattern",
            "source_bank",
            name="uq_processor_pattern_bank",
        ),
        CheckConstraint(
            "pattern_type IN ('exact_prefix', 'contains', 'regex')",
            name="ck_processor_patterns_type",
        ),
        Index("ix_processor_patterns_enabled_priority", "is_enabled", "priority"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    processor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(24), nullable=False)
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    source_bank: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    provenance_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("source_provenance.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class TransactionRelationship(Base):
    __tablename__ = "transaction_relationships"
    __table_args__ = (
        UniqueConstraint(
            "from_transaction_id",
            "to_transaction_id",
            "relationship_type",
            name="uq_transaction_relationship_type",
        ),
        CheckConstraint(
            "from_transaction_id <> to_transaction_id",
            name="ck_transaction_relationship_not_self",
        ),
        CheckConstraint(
            "relationship_type IN ('refund_of', 'reversal_of', "
            "'internal_transfer_pair', 'credit_card_payment_pair', "
            "'wallet_topup_pair', 'duplicate_of')",
            name="ck_transaction_relationship_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'dismissed', 'voided')",
            name="ck_transaction_relationship_status",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_transaction_relationship_confidence",
        ),
        Index("ix_transaction_relationships_status", "status"),
        Index("ix_transaction_relationships_from", "from_transaction_id"),
        Index("ix_transaction_relationships_to", "to_transaction_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    from_transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    date_gap_days: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_match: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    detector_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive
    )
