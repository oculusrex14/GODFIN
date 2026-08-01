"""
Reconciliation Service
Matches parsed statement transactions with existing database records
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.core.transaction_semantics import (
    TransactionSemantic,
    VALID_SEMANTICS,
    infer_semantic_type,
)
from app.models.account import Account
from app.core.statement_parser import ParsedTransaction, ParsedStatement, StatementTransaction, StatementMetadata


@dataclass
class ReconciliationMatch:
    """Represents a potential match between parsed and existing transaction"""
    parsed_txn: ParsedTransaction
    existing_txn: Optional[Transaction]
    match_type: str  # 'exact', 'high', 'medium', 'low', 'none'
    match_score: float  # 0.0 to 1.0
    match_reasons: List[str]


@dataclass
class ReconciliationResult:
    """Result of reconciling a statement"""
    matches: List[ReconciliationMatch]
    new_transactions: List[ParsedTransaction]
    duplicate_transactions: List[ParsedTransaction]
    potential_duplicates: List[Tuple[ParsedTransaction, Transaction]]
    total_parsed: int
    total_matched: int
    total_new: int


class ReconciliationService:
    """
    Service for reconciling parsed statement transactions
    with existing database records
    """

    # Thresholds for matching
    EXACT_THRESHOLD = 0.95
    HIGH_THRESHOLD = 0.80
    MEDIUM_THRESHOLD = 0.60
    LOW_THRESHOLD = 0.40

    # Amount tolerance for matching (percentage)
    AMOUNT_TOLERANCE = 0.01  # 1% tolerance

    # Date tolerance for matching (days)
    DATE_TOLERANCE = 3

    @staticmethod
    def reconcile(
        db: Session,
        statement: ParsedStatement,
        account_id: str,
        user_id: str = None,
    ) -> ReconciliationResult:
        """
        Reconcile parsed statement with existing transactions

        Args:
            db: Database session
            statement: Parsed statement
            account_id: Account ID to reconcile against
            user_id: Optional user ID for audit

        Returns:
            ReconciliationResult with matches and new transactions
        """
        matches = []
        new_transactions = []
        duplicate_transactions = []
        potential_duplicates = []

        # Get existing transactions for the statement period
        existing_txns = ReconciliationService._get_existing_transactions(
            db, account_id, statement
        )

        # Track which existing transactions have been matched
        matched_existing_ids = set()

        for parsed_txn in statement.transactions:
            # Find best match among existing transactions
            match = ReconciliationService._find_best_match(
                parsed_txn, existing_txns, matched_existing_ids
            )

            if match:
                matches.append(match)

                if match.match_type == 'exact':
                    duplicate_transactions.append(parsed_txn)
                    matched_existing_ids.add(match.existing_txn.id)
                elif match.match_type in ('high', 'medium'):
                    potential_duplicates.append((parsed_txn, match.existing_txn))
                    matched_existing_ids.add(match.existing_txn.id)
                else:
                    # Low match - likely new transaction
                    new_transactions.append(parsed_txn)
            else:
                # No match found - new transaction
                new_transactions.append(parsed_txn)

        return ReconciliationResult(
            matches=matches,
            new_transactions=new_transactions,
            duplicate_transactions=duplicate_transactions,
            potential_duplicates=potential_duplicates,
            total_parsed=len(statement.transactions),
            total_matched=len(matches),
            total_new=len(new_transactions),
        )

    @staticmethod
    def _get_existing_transactions(
        db: Session,
        account_id: str,
        statement: ParsedStatement,
    ) -> List[Transaction]:
        """Get existing transactions that might overlap with statement period"""
        # Find date range from parsed transactions
        if not statement.transactions:
            return []

        dates = [t.date for t in statement.transactions]
        min_date = min(dates) - timedelta(days=7)
        max_date = max(dates) + timedelta(days=7)

        return db.query(Transaction).filter(
            Transaction.account_id == account_id,
            Transaction.date >= min_date,
            Transaction.date <= max_date,
            Transaction.status != 'deleted',
        ).all()

    @staticmethod
    def _find_best_match(
        parsed_txn: ParsedTransaction,
        existing_txns: List[Transaction],
        exclude_ids: set,
    ) -> Optional[ReconciliationMatch]:
        """Find the best matching existing transaction"""
        best_match = None
        best_score = 0.0

        for existing in existing_txns:
            if existing.id in exclude_ids:
                continue

            score, reasons = ReconciliationService._calculate_match_score(
                parsed_txn, existing
            )

            if score > best_score:
                best_score = score
                best_match = existing

        if best_match is None:
            return None

        # Determine match type based on score
        if best_score >= ReconciliationService.EXACT_THRESHOLD:
            match_type = 'exact'
        elif best_score >= ReconciliationService.HIGH_THRESHOLD:
            match_type = 'high'
        elif best_score >= ReconciliationService.MEDIUM_THRESHOLD:
            match_type = 'medium'
        elif best_score >= ReconciliationService.LOW_THRESHOLD:
            match_type = 'low'
        else:
            match_type = 'none'

        return ReconciliationMatch(
            parsed_txn=parsed_txn,
            existing_txn=best_match,
            match_type=match_type,
            match_score=best_score,
            match_reasons=[],
        )

    @staticmethod
    def _calculate_match_score(
        parsed_txn: ParsedTransaction,
        existing: Transaction,
    ) -> Tuple[float, List[str]]:
        """
        Calculate match score between parsed and existing transaction

        Returns:
            Tuple of (score, list of match reasons)
        """
        reasons = []
        scores = []

        # Reference number exact match (highest priority — guaranteed match)
        parsed_ref = getattr(parsed_txn, 'reference', None) or getattr(parsed_txn, 'upi_ref_number', None)
        if parsed_ref and hasattr(existing, 'upi_ref_number') and existing.upi_ref_number:
            if parsed_ref == existing.upi_ref_number:
                return 1.0, ['Exact reference number match']

        # Fast-path: exact amount + same date + same type = almost certain duplicate
        exact_amount = (float(parsed_txn.amount) == float(existing.amount))
        same_type = (parsed_txn.type == existing.type)
        date_diff = abs((parsed_txn.date - existing.date).days)

        if exact_amount and same_type and date_diff == 0:
            return 0.95, ['Exact amount + date + type match']
        if exact_amount and same_type and date_diff <= 1:
            return 0.90, ['Exact amount + near date + type match']

        # Amount matching (most important — 50% weight)
        amount_score = ReconciliationService._match_amount(
            parsed_txn.amount, existing.amount
        )
        if amount_score > 0:
            reasons.append(f"Amount match: {amount_score:.2f}")
        scores.append(amount_score * 0.50)  # 50% weight

        # Date matching
        date_score = ReconciliationService._match_date(
            parsed_txn.date, existing.date
        )
        if date_score > 0:
            reasons.append(f"Date match: {date_score:.2f}")
        scores.append(date_score * 0.20)  # 20% weight

        # Type matching
        type_score = 1.0 if same_type else 0.0
        if type_score > 0:
            reasons.append("Type match")
        scores.append(type_score * 0.10)  # 10% weight

        # Description matching
        desc_score = ReconciliationService._match_description(
            parsed_txn.description, existing.merchant_raw or existing.merchant_normalized or ''
        )
        if desc_score > 0:
            reasons.append(f"Description match: {desc_score:.2f}")
        scores.append(desc_score * 0.20)  # 20% weight

        total_score = sum(scores)
        return total_score, reasons

    @staticmethod
    def _match_amount(parsed_amount: float, existing_amount: float) -> float:
        """Calculate amount match score"""
        if parsed_amount == existing_amount:
            return 1.0

        # Allow small tolerance for floating point differences
        diff_pct = abs(parsed_amount - existing_amount) / max(parsed_amount, existing_amount, 1)
        if diff_pct <= ReconciliationService.AMOUNT_TOLERANCE:
            return 0.95

        # Partial score for close amounts
        if diff_pct <= 0.05:  # Within 5%
            return 0.7

        return 0.0

    @staticmethod
    def _match_date(parsed_date: date, existing_date: date) -> float:
        """Calculate date match score"""
        diff_days = abs((parsed_date - existing_date).days)

        if diff_days == 0:
            return 1.0
        elif diff_days <= ReconciliationService.DATE_TOLERANCE:
            # Linear decay within tolerance
            return 1.0 - (diff_days / (ReconciliationService.DATE_TOLERANCE + 1))
        else:
            return 0.0

    @staticmethod
    def _match_description(parsed_desc: str, existing_desc: str) -> float:
        """Calculate description similarity score"""
        # Normalize descriptions
        parsed_norm = parsed_desc.upper().strip()
        existing_norm = existing_desc.upper().strip()

        # Exact match
        if parsed_norm == existing_norm:
            return 1.0

        # Check if one contains the other
        if parsed_norm in existing_norm or existing_norm in parsed_norm:
            return 0.9

        # Fuzzy match using SequenceMatcher
        ratio = SequenceMatcher(None, parsed_norm, existing_norm).ratio()

        # Boost score for common keywords
        keywords = ['UPI', 'ATM', 'NEFT', 'IMPS', 'POS', 'SWIGGY', 'ZOMATO', 'AMAZON', 'FLIPKART']
        for kw in keywords:
            if kw in parsed_norm and kw in existing_norm:
                ratio = min(1.0, ratio + 0.2)
                break

        return ratio

    @staticmethod
    def create_transaction_from_parsed(
        parsed_txn: ParsedTransaction,
        account_id: str,
        source: str = 'statement_upload',
    ) -> Transaction:
        """Create a Transaction object from a parsed transaction"""
        # Generate checksum for deduplication
        checksum_data = f"{parsed_txn.date}|{parsed_txn.amount}|{parsed_txn.description}|{account_id}"
        checksum = hashlib.sha256(checksum_data.encode()).hexdigest()[:32]

        # Use parsed merchant_name if available, otherwise raw description
        merchant_raw = getattr(parsed_txn, 'merchant_name', None) or parsed_txn.description
        instrument = getattr(parsed_txn, 'instrument', None) or 'statement'
        is_transfer = getattr(parsed_txn, 'is_transfer', False)
        semantic_type = getattr(parsed_txn, 'semantic_type', None)
        if semantic_type not in VALID_SEMANTICS or semantic_type == TransactionSemantic.UNKNOWN.value:
            if getattr(parsed_txn, 'is_income', False):
                semantic_type = TransactionSemantic.INCOME.value
            else:
                semantic_type = infer_semantic_type(
                    transaction_type=parsed_txn.type,
                    category=getattr(parsed_txn, 'category_hint', None),
                    subcategory=getattr(parsed_txn, 'subcategory_hint', None),
                    is_transfer=is_transfer,
                    text_parts=(parsed_txn.description,),
                )
        is_income = semantic_type == TransactionSemantic.INCOME.value
        is_transfer = semantic_type == TransactionSemantic.INTERNAL_TRANSFER.value
        vpa_handle = getattr(parsed_txn, 'vpa_handle', None)
        upi_ref = getattr(parsed_txn, 'upi_ref_number', None) or parsed_txn.reference

        return Transaction(
            id=str(uuid.uuid4()),
            date=parsed_txn.date,
            raw_text=f"Statement: {parsed_txn.description} {parsed_txn.amount}",
            merchant_raw=merchant_raw,
            merchant_normalized=merchant_raw.upper().strip() if merchant_raw else parsed_txn.description.upper().strip(),
            amount=parsed_txn.amount,
            type=parsed_txn.type,
            instrument=instrument,
            account_id=account_id,
            source=source,
            is_income=is_income,
            is_transfer=is_transfer,
            semantic_type=semantic_type,
            vpa_handle=vpa_handle,
            upi_ref_number=upi_ref,
            confidence=0.8,
            classification_source='statement',
            checksum_source=checksum,
            reconciled=True,
        )

    @staticmethod
    def detect_income_sources(
        db: Session,
        statement: ParsedStatement,
    ) -> List[ParsedTransaction]:
        """
        Detect only verified income transactions from statement credits.

        Refunds, cashback, reimbursements, reversals, transfers and generic
        credits remain non-income and available for explicit user review.
        """
        subcategory_keywords = {
            'Salary': ['SALARY', 'WAGES'],
            'Interest': ['INTEREST', 'INT DIV', 'DIVIDEND'],
            'Other Income': ['BONUS', 'INCENTIVE'],
        }

        income_transactions = []

        for txn in statement.transactions:
            if txn.type != 'credit':
                continue

            desc_upper = txn.description.upper()

            semantic_type = getattr(txn, 'semantic_type', None)
            if semantic_type not in VALID_SEMANTICS or semantic_type == TransactionSemantic.UNKNOWN.value:
                if getattr(txn, 'is_income', False):
                    semantic_type = TransactionSemantic.INCOME.value
                else:
                    semantic_type = infer_semantic_type(
                        transaction_type=txn.type,
                        category=txn.category_hint,
                        subcategory=txn.subcategory_hint,
                        is_transfer=getattr(txn, 'is_transfer', False),
                        text_parts=(txn.description,),
                    )
            txn.semantic_type = semantic_type
            txn.is_income = semantic_type == TransactionSemantic.INCOME.value
            txn.is_transfer = semantic_type == TransactionSemantic.INTERNAL_TRANSFER.value

            if not txn.is_income:
                if semantic_type == TransactionSemantic.REFUND.value:
                    txn.category_hint = 'INCOME'
                    txn.subcategory_hint = 'Refund'
                elif semantic_type == TransactionSemantic.CASHBACK.value:
                    txn.category_hint = 'INCOME'
                    txn.subcategory_hint = 'Cashback'
                continue

            txn.category_hint = 'INCOME'

            # Try to assign a subcategory hint based on keywords
            matched_sub = None
            for sub, keywords in subcategory_keywords.items():
                if any(kw in desc_upper for kw in keywords):
                    matched_sub = sub
                    break

            txn.subcategory_hint = matched_sub
            income_transactions.append(txn)

        return income_transactions


# Module-level convenience functions for API endpoints

def reconcile_statement(
    db: Session,
    statement,
    account_id: str,
    user_id: str = None,
) -> ReconciliationResult:
    """
    Reconcile parsed statement with existing transactions.
    Convenience wrapper for ReconciliationService.reconcile().

    Accepts either a ParsedStatement or a raw list of StatementTransaction/
    ParsedTransaction objects (auto-wrapped for backward compatibility).
    """
    if isinstance(statement, list):
        # Auto-convert StatementTransaction → ParsedTransaction
        parsed_txns = []
        for t in statement:
            if isinstance(t, StatementTransaction):
                parsed_txns.append(ParsedTransaction.from_statement_transaction(t))
            elif isinstance(t, ParsedTransaction):
                parsed_txns.append(t)
            else:
                parsed_txns.append(t)
        statement = ParsedStatement(
            metadata=StatementMetadata(statement_type=''),
            transactions=parsed_txns,
        )
    return ReconciliationService.reconcile(db, statement, account_id, user_id)


def import_new_transactions(
    db: Session,
    transactions: List[ParsedTransaction],
    account_id: str,
    source: str = 'statement_upload',
) -> List[Transaction]:
    """
    Import new transactions from parsed statement.
    Creates Transaction records and adds them to the database.
    Skips duplicates using checksum deduplication.
    """
    from app.core.audit import assert_period_writable

    # Validate the complete batch before adding anything. A mixed statement
    # must not partially import writable months while silently omitting a
    # finalized one.
    checked_periods: set[tuple[int, int]] = set()
    for parsed_txn in transactions:
        period = (parsed_txn.date.year, parsed_txn.date.month)
        if period in checked_periods:
            continue
        assert_period_writable(db, parsed_txn.date)
        checked_periods.add(period)

    imported = []
    for parsed_txn in transactions:
        txn = ReconciliationService.create_transaction_from_parsed(
            parsed_txn, account_id, source
        )
        # Checksum-based dedup: skip if identical transaction already exists
        if txn.checksum_source:
            existing = db.query(Transaction).filter_by(
                checksum_source=txn.checksum_source
            ).first()
            if existing:
                continue
        # Also check for exact date+amount+account match to catch re-uploads
        exact_dup = db.query(Transaction).filter(
            Transaction.account_id == account_id,
            Transaction.date == txn.date,
            Transaction.amount == txn.amount,
            Transaction.type == txn.type,
            Transaction.merchant_normalized == txn.merchant_normalized,
        ).first()
        if exact_dup:
            continue
        db.add(txn)
        imported.append(txn)
    db.flush()
    return imported
