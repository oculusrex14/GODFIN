from __future__ import annotations

import logging
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.account_mapping import (
    resolve_profile_account,
    resolve_sender_mapping,
)
from app.core.classifier import classify_transaction, get_review_status
from app.core.audit import FinalizedPeriodError, assert_period_writable
from app.core.email_parser import (
    ParsedTransaction,
    compute_canonical_checksum,
    compute_source_checksum,
    is_blacklisted_subject,
    is_whitelisted_sender,
    parse_email_body,
)
from app.core.gmail_service import GmailFetchResult, GmailSyncError, fetch_messages
from app.core.merchant_memory_service import upsert_merchant_memory
from app.core.transaction_semantics import (
    TransactionSemantic,
    infer_semantic_type,
)
from app.models.app_setting import AppSetting
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


class IngestionResult:
    def __init__(self):
        self.processed = 0
        self.created = 0
        self.skipped_blacklist = 0
        self.skipped_no_match = 0
        self.skipped_duplicate = 0
        self.skipped_finalized_period = 0
        self.errors = 0
        self.error_details = []
        self.merchant_keys: set[tuple[str, str | None]] = set()
        self.source_status = "complete"
        self.retryable = False
        self.full_resync = False

    def to_dict(self):
        return {
            'processed': self.processed,
            'created': self.created,
            'skipped_blacklist': self.skipped_blacklist,
            'skipped_no_match': self.skipped_no_match,
            'skipped_duplicate': self.skipped_duplicate,
            'skipped_finalized_period': self.skipped_finalized_period,
            'errors': self.errors,
            'error_details': self.error_details[:10],
            'source_status': self.source_status,
            'retryable': self.retryable,
            'full_resync': self.full_resync,
        }


def _record_fetch_status(
    result: IngestionResult,
    fetched: GmailFetchResult,
) -> None:
    if result.source_status != "partial":
        result.source_status = fetched.status
    result.retryable = result.retryable or fetched.retryable
    if fetched.errors:
        result.errors += len(fetched.errors)
        result.error_details.extend(fetched.errors)


def _is_email_identity_conflict(exc: IntegrityError) -> bool:
    """Return whether SQLite rejected a duplicate Gmail message identity."""
    detail = str(exc.orig).lower()
    return (
        "unique constraint failed: transactions.email_message_id" in detail
        or "uq_transactions_email_message_id" in detail
    )


def _process_message_with_savepoint(
    db: Session,
    message: dict,
    result: IngestionResult,
) -> None:
    result.processed += 1
    try:
        with db.begin_nested():
            _process_message(db, message, result)
    except FinalizedPeriodError as exc:
        result.skipped_finalized_period += 1
        result.source_status = "partial"
        result.retryable = True
        result.error_details.append(
            f"Message {message.get('id', '?')}: {str(exc)}"
        )
        logger.info(
            "A Gmail transaction was held because its accounting period is finalized"
        )
    except IntegrityError as exc:
        if not _is_email_identity_conflict(exc):
            result.errors += 1
            result.error_details.append(
                f"Message {message.get('id', '?')}: database validation failed"
            )
            logger.warning(
                "A Gmail message failed database validation; "
                "the rest of the batch will continue"
            )
            return
        result.skipped_duplicate += 1
        logger.info(
            "A concurrently imported Gmail message was safely deduplicated"
        )
    except Exception as exc:
        result.errors += 1
        result.error_details.append(
            f"Message {message.get('id', '?')}: {str(exc)}"
        )
        logger.warning(
            "A Gmail message could not be imported; the rest of the batch will continue"
        )


def _run_post_ingestion_detection(
    db: Session,
    result: IngestionResult,
) -> None:
    if not result.merchant_keys:
        return
    from app.core.goal_contributions import (
        detect_goal_contribution_suggestions,
    )
    from app.core.license import has_feature
    from app.core.product_depth import sync_subscription_suggestions
    from app.core.recurring import detect_recurring_patterns

    try:
        detect_recurring_patterns(db, merchant_keys=result.merchant_keys)
        sync_subscription_suggestions(db, run_detection=False)
        if has_feature(db, "fd_rd_goal_detection"):
            transactions = (
                db.query(Transaction)
                .filter(
                    Transaction.merchant_normalized.in_(
                        {key[0] for key in result.merchant_keys}
                    )
                )
                .all()
            )
            detect_goal_contribution_suggestions(
                db, transactions=transactions
            )
    except Exception as exc:
        logger.warning("Post-ingestion detection could not complete: %s", exc)


def run_ingestion(db: Session, mock_messages: Optional[list] = None) -> IngestionResult:
    result = IngestionResult()

    if mock_messages is not None:
        messages = mock_messages
        new_history_id = None
    else:
        history_setting = db.query(AppSetting).filter_by(key='last_gmail_history_id').first()
        history_id = history_setting.value if history_setting and history_setting.value else None

        try:
            fetched = fetch_messages(history_id=history_id)
        except GmailSyncError as exc:
            if exc.code != "history_expired":
                raise
            last_run_setting = db.query(AppSetting).filter_by(
                key='last_ingestion_run'
            ).first()
            fallback_start = date(date.today().year, 1, 1)
            if last_run_setting and last_run_setting.value:
                try:
                    fallback_start = (
                        datetime.fromisoformat(last_run_setting.value).date()
                        - timedelta(days=1)
                    )
                except ValueError:
                    pass
            fetched = fetch_messages(
                after_date=fallback_start.isoformat(),
                before_date=(date.today() + timedelta(days=1)).isoformat(),
                max_results=1000,
            )
            result.full_resync = True
        messages, new_history_id = fetched
        _record_fetch_status(result, fetched)

    for msg in messages:
        _process_message_with_savepoint(db, msg, result)

    completed = result.source_status in {"complete", "empty"}
    if new_history_id and mock_messages is None and completed:
        _update_setting(db, 'last_gmail_history_id', new_history_id)

    _run_post_ingestion_detection(db, result)
    if completed:
        _update_setting(db, 'last_ingestion_run', datetime.now(timezone.utc).isoformat())
    db.commit()

    return result


def _process_message(db: Session, msg: dict, result: IngestionResult) -> None:
    sender = msg.get('sender', '')
    subject = msg.get('subject', '')
    body = msg.get('body', '')
    message_id = msg.get('id', '')

    mapping = resolve_sender_mapping(db, sender)
    parser_profile = (
        mapping["parser_profile"]
        if mapping
        else is_whitelisted_sender(sender)
    )
    if not parser_profile:
        result.skipped_no_match += 1
        return
    account_id = (
        mapping["account_id"]
        if mapping
        else resolve_profile_account(db, parser_profile)
    )

    # Check subject blacklist
    if is_blacklisted_subject(subject):
        result.skipped_blacklist += 1
        return

    # Check email_message_id dedup
    if message_id:
        existing = db.query(Transaction).filter_by(email_message_id=message_id).first()
        if existing:
            result.skipped_duplicate += 1
            return

    # Parse the email body
    try:
        parsed = parse_email_body(body, parser_profile)
    except Exception as e:
        logger.warning(f"Email parsing failed for message {message_id}: {e}")
        result.skipped_no_match += 1
        return

    if not parsed:
        # Log first few examples for debugging (message_id, subject, sender for issue tracking)
        if result.skipped_no_match < 5:
            logger.warning(
                f"Email parsing failed (no pattern match): "
                f"message_id={message_id}, subject='{subject[:80] if subject else 'None'}', "
                f"sender='{sender[:50] if sender else 'None'}', "
                f"parser_profile={parser_profile}"
            )
        result.skipped_no_match += 1
        return

    # Special handling for RuPay Credit UPI - comes from savings sender but is credit card tx
    if parsed.instrument == 'rupay_credit_upi':
        account_id = resolve_profile_account(db, "hdfc_credit")

    if not account_id:
        result.skipped_no_match += 1
        return

    # Compute checksums
    checksum_source = compute_source_checksum(parsed.raw_text, 'gmail')
    checksum_canonical = compute_canonical_checksum(
        parsed.txn_date, parsed.amount, parsed.merchant_normalized,
        parsed.instrument, account_id,
    )

    # Check source checksum dedup
    existing = db.query(Transaction).filter_by(checksum_source=checksum_source).first()
    if existing:
        result.skipped_duplicate += 1
        return

    # Check canonical checksum dedup
    existing = db.query(Transaction).filter_by(checksum_canonical=checksum_canonical).first()
    if existing:
        result.skipped_duplicate += 1
        return

    assert_period_writable(db, parsed.txn_date)

    # Classify the transaction
    classification = classify_transaction(
        db,
        merchant_normalized=parsed.merchant_normalized,
        amount=parsed.amount,
        instrument=parsed.instrument,
        vpa_handle=parsed.vpa_handle,
    )

    trusted_income_sources = {"exact_match", "confirmed_pattern", "rule"}
    semantic_type = infer_semantic_type(
        transaction_type=parsed.txn_type,
        category=classification.category,
        subcategory=classification.subcategory,
        is_transfer=classification.is_transfer,
        text_parts=(parsed.raw_text, parsed.merchant_raw, parsed.merchant_normalized),
        explicitly_classified=classification.source in trusted_income_sources,
    )

    # Create transaction
    txn = Transaction(
        id=str(uuid.uuid4()),
        date=parsed.txn_date,
        raw_text=parsed.raw_text,
        merchant_raw=parsed.merchant_raw,
        merchant_normalized=parsed.merchant_normalized,
        amount=parsed.amount,
        type=parsed.txn_type,
        instrument=parsed.instrument,
        account_id=account_id,
        source='gmail',
        email_message_id=message_id,
        checksum_source=checksum_source,
        checksum_canonical=checksum_canonical,
        vpa_handle=parsed.vpa_handle,
        upi_ref_number=parsed.upi_ref_number,
        category=classification.category,
        subcategory=classification.subcategory,
        confidence=classification.confidence,
        classification_source=classification.source,
        is_transfer=(semantic_type == TransactionSemantic.INTERNAL_TRANSFER.value),
        is_income=(semantic_type == TransactionSemantic.INCOME.value),
        semantic_type=semantic_type,
        reconciled=False,
    )
    db.add(txn)
    # Retry flush up to 3 times on database lock
    for attempt in range(3):
        try:
            db.flush()
            break
        except Exception as flush_err:
            if 'database is locked' in str(flush_err) and attempt < 2:
                import time
                time.sleep(1 * (attempt + 1))
                continue
            raise
    if classification.category:
        upsert_merchant_memory(
            db,
            parsed.merchant_normalized,
            classification.category,
            classification.subcategory,
            classification.confidence,
            raw_string=parsed.merchant_raw,
        )
    if txn.merchant_normalized:
        result.merchant_keys.add((txn.merchant_normalized, txn.account_id))
    result.created += 1


def _update_setting(db: Session, key: str, value: str) -> None:
    setting = db.query(AppSetting).filter_by(key=key).first()
    if setting:
        setting.value = str(value)
    else:
        db.add(AppSetting(key=key, value=str(value)))


def run_initial_sync(db: Session) -> IngestionResult:
    """
    Run initial sync from start of current year to today.
    Stores the date range for tracking.
    """
    # Calculate date range: Jan 1 of current year to today
    today = date.today()
    start_of_year = date(today.year, 1, 1)

    after_date = start_of_year.strftime('%Y-%m-%d')
    before_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')

    # Run ingestion with date range
    result = run_ingestion_with_dates(db, after_date=after_date, before_date=before_date)

    # Store the date range
    date_range = f"{after_date} to {today.isoformat()}"
    _update_setting(db, 'initial_sync_date_range', date_range)
    completed = result.source_status in {"complete", "empty"}
    _update_setting(db, 'initial_sync_completed', 'true' if completed else 'false')
    db.commit()

    return result


def run_initial_sync_background() -> None:
    """
    Background task version of initial sync. Opens its own DB session
    and writes progress to app_settings for polling.
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        # Mark as running
        _update_setting(db, 'sync_status', 'running')
        _update_setting(db, 'sync_progress_processed', '0')
        _update_setting(db, 'sync_progress_total', '0')
        _update_setting(db, 'sync_error', '')
        _update_setting(db, 'sync_result', '')
        db.commit()

        today = date.today()
        start_of_year = date(today.year, 1, 1)
        after_date = start_of_year.strftime('%Y-%m-%d')
        before_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')

        # Fetch all messages first to get total count
        fetched = fetch_messages(
            after_date=after_date,
            before_date=before_date,
            max_results=1000,
        )
        messages, new_history_id = fetched

        total = len(messages)
        _update_setting(db, 'sync_progress_total', str(total))
        db.commit()

        result = IngestionResult()
        _record_fetch_status(result, fetched)
        batch_size = 25

        for i, msg in enumerate(messages):
            _process_message_with_savepoint(db, msg, result)

            # Update progress every batch_size messages
            if (i + 1) % batch_size == 0 or (i + 1) == total:
                _update_setting(db, 'sync_progress_processed', str(i + 1))
                db.commit()

        _run_post_ingestion_detection(db, result)

        # Finalize
        date_range = f"{after_date} to {today.isoformat()}"
        _update_setting(db, 'initial_sync_date_range', date_range)
        completed = result.source_status in {"complete", "empty"}
        _update_setting(db, 'initial_sync_completed', 'true' if completed else 'false')
        if completed:
            _update_setting(db, 'last_ingestion_run', datetime.now(timezone.utc).isoformat())
            if new_history_id:
                _update_setting(db, 'last_gmail_history_id', new_history_id)
        _update_setting(db, 'sync_status', 'completed' if completed else 'partial')
        _update_setting(db, 'sync_result', json.dumps(result.to_dict()))
        _update_setting(db, 'sync_progress_processed', str(total))
        db.commit()

        logger.info(f"Background initial sync complete: {result.created} created, {result.processed} processed")

    except Exception as e:
        logger.error(f"Background initial sync failed: {e}")
        try:
            _update_setting(db, 'sync_status', 'error')
            _update_setting(db, 'sync_error', str(e))
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


def run_ingestion_with_dates_background(start_date_str: str, end_date_str: str) -> None:
    """
    Background task version of date-range ingestion. Opens its own DB session
    and writes progress to app_settings for polling.
    Splits the date range into 7-day batches.
    """
    from datetime import date, timedelta
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        # Mark as running
        _update_setting(db, 'ingest_now_status', 'running')
        _update_setting(db, 'ingest_now_processed', '0')
        _update_setting(db, 'ingest_now_total', '0')
        _update_setting(db, 'ingest_now_result', '')
        _update_setting(db, 'ingest_now_error', '')
        _update_setting(db, 'ingest_now_batch_current', '0')
        _update_setting(db, 'ingest_now_batch_total', '0')
        db.commit()

        start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        # Split into 7-day batches
        batches = []
        batch_start = start
        while batch_start < end:
            batch_end = min(batch_start + timedelta(days=7), end)
            batches.append((batch_start.strftime('%Y-%m-%d'), batch_end.strftime('%Y-%m-%d')))
            batch_start = batch_end

        total_batches = len(batches)
        _update_setting(db, 'ingest_now_batch_total', str(total_batches))
        _update_setting(db, 'ingest_now_total', str(total_batches))
        db.commit()

        result = IngestionResult()

        for batch_idx, (batch_after, batch_before) in enumerate(batches):
            _update_setting(db, 'ingest_now_batch_current', str(batch_idx + 1))
            db.commit()

            # Fetch messages for this batch
            fetched = fetch_messages(
                after_date=batch_after,
                before_date=batch_before,
                max_results=1000,
            )
            messages, _ = fetched
            _record_fetch_status(result, fetched)

            for msg in messages:
                _process_message_with_savepoint(db, msg, result)

            # Update progress after each batch
            _update_setting(db, 'ingest_now_processed', str(batch_idx + 1))
            db.commit()

        _run_post_ingestion_detection(db, result)

        # Finalize
        completed = result.source_status in {"complete", "empty"}
        if completed:
            _update_setting(db, 'last_ingestion_run', datetime.now(timezone.utc).isoformat())
        date_range = f"{start_date_str} to {end_date_str}"
        _update_setting(db, 'last_manual_ingestion_range', date_range)
        _update_setting(db, 'last_manual_ingestion_date', datetime.now(timezone.utc).isoformat())
        _update_setting(db, 'ingest_now_status', 'completed' if completed else 'partial')
        _update_setting(db, 'ingest_now_result', json.dumps(result.to_dict()))
        _update_setting(db, 'ingest_now_processed', str(total_batches))
        db.commit()

        logger.info(f"Background date-range ingestion complete: {result.created} created, {result.processed} processed")

    except Exception as e:
        logger.error(f"Background date-range ingestion failed: {e}")
        try:
            _update_setting(db, 'ingest_now_status', 'error')
            _update_setting(db, 'ingest_now_error', str(e))
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


def run_ingestion_with_dates(
    db: Session,
    after_date: str,
    before_date: str,
    is_manual: bool = True
) -> IngestionResult:
    """
    Run ingestion for a specific date range.

    Args:
        after_date: Start date (YYYY-MM-DD, inclusive)
        before_date: End date (YYYY-MM-DD, exclusive)
        is_manual: Whether this is a manual ingestion (for tracking)
    """
    result = IngestionResult()

    # Fetch messages with date range
    fetched = fetch_messages(
        after_date=after_date,
        before_date=before_date,
        max_results=1000  # Higher limit for manual sync
    )
    messages, new_history_id = fetched
    _record_fetch_status(result, fetched)

    for msg in messages:
        _process_message_with_savepoint(db, msg, result)

    _run_post_ingestion_detection(db, result)

    # Update settings
    if is_manual:
        date_range = f"{after_date} to {before_date}"
        _update_setting(db, 'last_manual_ingestion_range', date_range)
        _update_setting(db, 'last_manual_ingestion_date', datetime.now(timezone.utc).isoformat())

    if result.source_status in {"complete", "empty"}:
        _update_setting(db, 'last_ingestion_run', datetime.now(timezone.utc).isoformat())
    db.commit()

    return result


def get_ingestion_history(db: Session) -> dict:
    """Get detailed ingestion history for display."""
    settings_to_fetch = [
        'last_ingestion_run',
        'last_manual_ingestion_date',
        'last_manual_ingestion_range',
        'initial_sync_date_range',
        'initial_sync_completed',
    ]

    history = {}
    for key in settings_to_fetch:
        setting = db.query(AppSetting).filter_by(key=key).first()
        history[key] = setting.value if setting else None

    return history
