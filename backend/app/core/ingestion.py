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
from app.core.background_jobs import JobCancelled, JobContext
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
from app.core.manual_income import link_manual_income_provenance
from app.core.transaction_semantics import (
    TransactionSemantic,
    infer_semantic_type,
)
from app.core.transaction_enrichment import (
    apply_transaction_envelope,
    build_transaction_envelope,
)
from app.models.app_setting import AppSetting
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


class IngestionResult:
    def __init__(self):
        self.processed = 0
        self.eligible_financial_messages = 0
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
        self.parse_review_count = 0
        self.skip_reasons: dict[str, int] = {}
        self.requested_start: str | None = None
        self.requested_end: str | None = None
        self.coverage_advanced = False
        self.last_successful_coverage_end: str | None = None
        self.cursor_advanced = False

    def skip(self, reason: str) -> None:
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1

    def to_dict(self):
        return {
            'processed': self.processed,
            'eligible_financial_messages': self.eligible_financial_messages,
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
            'parse_review_count': self.parse_review_count,
            'skip_reasons': dict(sorted(self.skip_reasons.items())),
            'requested_start': self.requested_start,
            'requested_end': self.requested_end,
            'coverage_advanced': self.coverage_advanced,
            'last_successful_coverage_end': self.last_successful_coverage_end,
            'cursor_advanced': self.cursor_advanced,
        }


GMAIL_COVERAGE_RANGES_KEY = "gmail_coverage_ranges"
GMAIL_LAST_RESULT_KEY = "gmail_last_ingestion_result"
GMAIL_LAST_REQUEST_START_KEY = "gmail_last_requested_start"
GMAIL_LAST_REQUEST_END_KEY = "gmail_last_requested_end"


def _date_setting(db: Session, key: str) -> date | None:
    setting = db.query(AppSetting).filter_by(key=key).first()
    if not setting or not setting.value:
        return None
    try:
        return date.fromisoformat(setting.value[:10])
    except (TypeError, ValueError):
        return None


def _coverage_ranges(db: Session) -> list[tuple[date, date]]:
    setting = db.query(AppSetting).filter_by(key=GMAIL_COVERAGE_RANGES_KEY).first()
    try:
        raw = json.loads(setting.value if setting and setting.value else "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    parsed: list[tuple[date, date]] = []
    if not isinstance(raw, list):
        return parsed
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            start = date.fromisoformat(str(item.get("start")))
            end = date.fromisoformat(str(item.get("end")))
        except ValueError:
            continue
        if start <= end:
            parsed.append((start, end))
    return _merge_coverage_ranges(parsed)


def _merge_coverage_ranges(
    ranges: list[tuple[date, date]],
) -> list[tuple[date, date]]:
    merged: list[tuple[date, date]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1] + timedelta(days=1):
            merged.append((start, end))
            continue
        prior_start, prior_end = merged[-1]
        merged[-1] = (prior_start, max(prior_end, end))
    return merged


def _record_successful_coverage(
    db: Session,
    start: date,
    end: date,
) -> list[tuple[date, date]]:
    if start > end:
        return _coverage_ranges(db)
    merged = _merge_coverage_ranges([*_coverage_ranges(db), (start, end)])
    _update_setting(
        db,
        GMAIL_COVERAGE_RANGES_KEY,
        json.dumps(
            [
                {"start": range_start.isoformat(), "end": range_end.isoformat()}
                for range_start, range_end in merged
            ],
            separators=(",", ":"),
        ),
    )
    return merged


def gmail_coverage_summary(
    db: Session,
    *,
    through: date | None = None,
) -> dict[str, object]:
    window_end = through or date.today()
    window_start = date(window_end.year, 1, 1)
    ranges = _coverage_ranges(db)
    clipped = [
        (max(start, window_start), min(end, window_end))
        for start, end in ranges
        if end >= window_start and start <= window_end
    ]
    clipped = _merge_coverage_ranges(clipped)
    missing: list[tuple[date, date]] = []
    cursor = window_start
    for start, end in clipped:
        if cursor < start:
            missing.append((cursor, start - timedelta(days=1)))
        cursor = max(cursor, end + timedelta(days=1))
    if cursor <= window_end:
        missing.append((cursor, window_end))

    last_end = max((end for _, end in ranges), default=None)
    fallback = _date_setting(db, "last_ingestion_run")
    next_start = last_end or fallback or window_start
    return {
        "coverage_ranges": [
            {"start": start.isoformat(), "end": end.isoformat()}
            for start, end in clipped
        ],
        "missing_ranges": [
            {"start": start.isoformat(), "end": end.isoformat()}
            for start, end in missing
        ],
        "coverage_window_start": window_start.isoformat(),
        "coverage_window_end": window_end.isoformat(),
        "last_successful_coverage_start": (
            min((start for start, _ in ranges), default=None).isoformat()
            if ranges
            else None
        ),
        "last_successful_coverage_end": last_end.isoformat() if last_end else None,
        "next_sync_start": next_start.isoformat(),
        "next_sync_end": window_end.isoformat(),
    }


def _prepare_result_range(
    result: IngestionResult,
    start: date,
    end: date,
) -> None:
    result.requested_start = start.isoformat()
    result.requested_end = end.isoformat()


def _finalize_successful_range(
    db: Session,
    result: IngestionResult,
    start: date,
    end: date,
) -> None:
    if result.source_status not in {"complete", "empty"}:
        return
    ranges = _record_successful_coverage(db, start, end)
    result.coverage_advanced = True
    result.last_successful_coverage_end = max(item[1] for item in ranges).isoformat()


def _store_last_result(db: Session, result: IngestionResult) -> None:
    _update_setting(db, GMAIL_LAST_RESULT_KEY, json.dumps(result.to_dict()))
    if result.requested_start:
        _update_setting(db, GMAIL_LAST_REQUEST_START_KEY, result.requested_start)
    if result.requested_end:
        _update_setting(db, GMAIL_LAST_REQUEST_END_KEY, result.requested_end)


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
    except FinalizedPeriodError:
        result.skipped_finalized_period += 1
        result.skip("finalized_period")
        result.source_status = "partial"
        result.retryable = True
        result.error_details.append(
            "A transaction was held because its finalized month is read-only."
        )
        logger.info(
            "A Gmail transaction was held because its accounting period is finalized"
        )
    except IntegrityError as exc:
        if not _is_email_identity_conflict(exc):
            result.errors += 1
            result.skip("database_validation")
            result.error_details.append(
                "A transaction failed local validation."
            )
            logger.warning(
                "A Gmail message failed database validation; "
                "the rest of the batch will continue"
            )
            return
        result.skipped_duplicate += 1
        result.skip("duplicate")
        logger.info(
            "A concurrently imported Gmail message was safely deduplicated"
        )
    except Exception as exc:
        result.errors += 1
        result.skip("import_error")
        result.error_details.append(
            "A transaction could not be imported."
        )
        logger.warning(
            "A Gmail message could not be imported; the rest of the batch will continue",
            extra={
                "operation_id": "gmail_message_import",
                "error_code": "GMAIL_MESSAGE_IMPORT_FAILED",
                "cause_type": type(exc).__name__,
            },
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
    requested_end = date.today()
    requested_start = date(requested_end.year, 1, 1)
    if mock_messages is not None:
        messages = mock_messages
        new_history_id = None
    else:
        coverage = gmail_coverage_summary(db, through=requested_end)
        requested_start = date.fromisoformat(str(coverage["next_sync_start"]))
        _prepare_result_range(result, requested_start, requested_end)
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
            requested_start = fallback_start
            _prepare_result_range(result, requested_start, requested_end)
            result.full_resync = True
        messages, new_history_id = fetched
        _record_fetch_status(result, fetched)

    for msg in messages:
        _process_message_with_savepoint(db, msg, result)

    completed = result.source_status in {"complete", "empty"}
    if new_history_id and mock_messages is None and completed:
        _update_setting(db, 'last_gmail_history_id', new_history_id)
        result.cursor_advanced = True

    _run_post_ingestion_detection(db, result)
    if completed:
        if mock_messages is None:
            _finalize_successful_range(
                db,
                result,
                requested_start,
                requested_end,
            )
        _update_setting(db, 'last_ingestion_run', datetime.now(timezone.utc).isoformat())
    if mock_messages is None:
        _store_last_result(db, result)
    db.commit()

    return result


def run_scheduled_ingestion_background(
    job_context: JobContext | None = None,
) -> dict:
    """Fetch Gmail without holding a SQLite transaction, then import locally.

    Reading the incremental cursor and importing the returned messages use
    separate short-lived sessions. A slow Gmail request therefore cannot keep a
    read transaction open while the UI or another worker needs to write.
    """
    from app.core.database import SessionLocal

    cursor_db = SessionLocal()
    try:
        history_setting = cursor_db.query(AppSetting).filter_by(
            key="last_gmail_history_id"
        ).first()
        history_id = (
            history_setting.value
            if history_setting and history_setting.value
            else None
        )
        last_run_setting = cursor_db.query(AppSetting).filter_by(
            key="last_ingestion_run"
        ).first()
        last_run_value = (
            last_run_setting.value
            if last_run_setting and last_run_setting.value
            else None
        )
        coverage = gmail_coverage_summary(cursor_db)
        requested_start = date.fromisoformat(str(coverage["next_sync_start"]))
        requested_end = date.today()
        cursor_db.rollback()
    finally:
        cursor_db.close()

    if job_context is not None:
        job_context.progress(10, message="Checking Gmail for new transactions…")
        job_context.check_cancelled()

    result = IngestionResult()
    _prepare_result_range(result, requested_start, requested_end)
    try:
        fetched = fetch_messages(history_id=history_id)
    except GmailSyncError as exc:
        if exc.code != "history_expired":
            raise
        fallback_start = date(date.today().year, 1, 1)
        if last_run_value:
            try:
                fallback_start = (
                    datetime.fromisoformat(last_run_value).date()
                    - timedelta(days=1)
                )
            except ValueError:
                pass
        fetched = fetch_messages(
            after_date=fallback_start.isoformat(),
            before_date=(date.today() + timedelta(days=1)).isoformat(),
            max_results=1000,
        )
        requested_start = fallback_start
        _prepare_result_range(result, requested_start, requested_end)
        result.full_resync = True

    messages, new_history_id = fetched
    _record_fetch_status(result, fetched)
    total = len(messages)
    if job_context is not None:
        job_context.progress(
            25,
            total=total,
            message="Gmail messages are ready to import.",
        )

    import_db = SessionLocal()
    try:
        for index, message in enumerate(messages):
            if job_context is not None and index % 25 == 0:
                job_context.check_cancelled()
            _process_message_with_savepoint(import_db, message, result)
            if job_context is not None and (
                (index + 1) % 25 == 0 or index + 1 == total
            ):
                progress = (
                    90
                    if total == 0
                    else 25 + int(((index + 1) / total) * 65)
                )
                job_context.progress(
                    progress,
                    total=total,
                    message=f"Imported {index + 1} of {total} Gmail messages…",
                )

        if job_context is not None:
            job_context.progress(
                92,
                total=total,
                message="Checking recurring payments and goal suggestions…",
            )
        _run_post_ingestion_detection(import_db, result)
        completed = result.source_status in {"complete", "empty"}
        if new_history_id and completed:
            _update_setting(import_db, "last_gmail_history_id", new_history_id)
            result.cursor_advanced = True
        if completed:
            _finalize_successful_range(
                import_db,
                result,
                requested_start,
                requested_end,
            )
            _update_setting(
                import_db,
                "last_ingestion_run",
                datetime.now(timezone.utc).isoformat(),
            )
        _store_last_result(import_db, result)
        import_db.commit()
        if job_context is not None:
            job_context.progress(
                99,
                total=total,
                message="Finishing the Gmail import…",
            )
        return result.to_dict()
    except Exception:
        import_db.rollback()
        raise
    finally:
        import_db.close()


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
        result.skip("unsupported_sender")
        return
    # Check subject blacklist
    if is_blacklisted_subject(subject):
        result.skipped_blacklist += 1
        result.skip("non_transaction_message")
        return

    result.eligible_financial_messages += 1

    # Check email_message_id dedup
    if message_id:
        existing = db.query(Transaction).filter_by(email_message_id=message_id).first()
        if existing:
            result.skipped_duplicate += 1
            result.skip("duplicate")
            return

    # Parse the email body
    try:
        parsed = parse_email_body(body, parser_profile)
    except Exception as exc:
        logger.warning(
            "Email parsing failed for one Gmail message (%s)",
            type(exc).__name__,
        )
        result.skipped_no_match += 1
        result.parse_review_count += 1
        result.skip("parse_review")
        return

    if not parsed:
        # Keep diagnostics support-safe: never log Gmail identifiers, senders,
        # subjects, or message bodies from a user's mailbox.
        if result.skipped_no_match < 5:
            logger.warning(
                "Email parsing failed (no supported alert pattern): "
                "parser_profile=%s",
                parser_profile,
            )
        result.skipped_no_match += 1
        result.parse_review_count += 1
        result.skip("parse_review")
        return

    # Sender addresses are only hints. Explicit message content and its last
    # four digits decide which configured active account receives the row.
    if parsed.account_last4:
        account_id = resolve_profile_account(
            db,
            parsed.account_type,
            parsed.account_last4,
        )
    elif mapping and mapping["parser_profile"] == parsed.account_type:
        account_id = mapping["account_id"]
    else:
        account_id = resolve_profile_account(db, parsed.account_type)

    if not account_id:
        result.skipped_no_match += 1
        result.parse_review_count += 1
        result.skip("account_mapping_required")
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
        result.skip("duplicate")
        return

    # Check canonical checksum dedup
    existing = db.query(Transaction).filter_by(checksum_canonical=checksum_canonical).first()
    if existing:
        result.skipped_duplicate += 1
        result.skip("duplicate")
        return

    parsed_semantic = infer_semantic_type(
        transaction_type=parsed.txn_type,
        text_parts=(parsed.raw_text, parsed.merchant_raw, parsed.merchant_normalized),
    )
    if parsed_semantic == TransactionSemantic.INCOME.value:
        manual_matches = (
            db.query(Transaction)
            .filter(
                Transaction.source == "manual_income",
                Transaction.account_id == account_id,
                Transaction.date == parsed.txn_date,
                Transaction.amount == parsed.amount,
                Transaction.type == "credit",
                Transaction.semantic_type == TransactionSemantic.INCOME.value,
                Transaction.status != "deleted",
            )
            .all()
        )
        if len(manual_matches) == 1:
            assert_period_writable(db, parsed.txn_date)
            manual_match = manual_matches[0]
            link_manual_income_provenance(
                db,
                manual_match,
                evidence_kind="gmail",
                evidence_id=checksum_source,
            )
            manual_match.email_message_id = message_id or None
            manual_match.checksum_canonical = checksum_canonical
            if not manual_match.reference_number:
                manual_match.reference_number = parsed.upi_ref_number
            result.skipped_duplicate += 1
            result.skip("reconciled_manual_income")
            return
        if len(manual_matches) > 1:
            result.skipped_duplicate += 1
            result.parse_review_count += 1
            result.skip("ambiguous_income_match")
            result.source_status = "partial"
            result.error_details.append(
                "A Gmail income credit matched more than one manual entry and needs review"
            )
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
    envelope = build_transaction_envelope(
        raw_text=parsed.raw_text,
        source_type="gmail",
        source_account_id=account_id,
        source_bank="hdfc",
        source_format_version=f"gmail-{parsed.account_type}-v1",
        booking_date=parsed.txn_date,
        amount=parsed.amount,
        currency="INR",
        direction=parsed.txn_type,
        instrument=parsed.instrument,
        merchant_raw=parsed.merchant_raw,
        merchant_candidate=parsed.merchant_normalized,
        vpa=parsed.vpa_handle,
        reference=parsed.upi_ref_number,
        coarse_semantic=semantic_type,
        category=classification.category,
        subcategory=classification.subcategory,
        parser_version="gmail-hdfc-v1",
    )
    apply_transaction_envelope(txn, envelope)
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
    result = run_ingestion_with_dates(
        db,
        after_date=after_date,
        before_date=before_date,
        is_manual=False,
    )

    # Store the date range
    date_range = f"{after_date} to {today.isoformat()}"
    _update_setting(db, 'initial_sync_date_range', date_range)
    completed = result.source_status in {"complete", "empty"}
    _update_setting(db, 'initial_sync_completed', 'true' if completed else 'false')
    db.commit()

    return result


def run_initial_sync_background(
    job_context: JobContext | None = None,
) -> dict:
    """
    Background task version of initial sync. Opens its own DB session
    and writes progress to app_settings for polling.
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        if job_context is not None:
            job_context.progress(
                1,
                message="Preparing the first Gmail import…",
            )
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
        if job_context is not None:
            job_context.progress(
                10,
                total=total,
                message="Gmail messages are ready to import.",
            )

        result = IngestionResult()
        _prepare_result_range(result, start_of_year, today)
        _record_fetch_status(result, fetched)
        batch_size = 25

        for i, msg in enumerate(messages):
            if job_context is not None and i % batch_size == 0:
                job_context.check_cancelled()
            _process_message_with_savepoint(db, msg, result)

            # Update progress every batch_size messages
            if (i + 1) % batch_size == 0 or (i + 1) == total:
                _update_setting(db, 'sync_progress_processed', str(i + 1))
                db.commit()
                if job_context is not None:
                    progress = 90 if total == 0 else 10 + int(((i + 1) / total) * 80)
                    job_context.progress(
                        progress,
                        total=total,
                        message=f"Imported {i + 1} of {total} Gmail messages…",
                    )

        if job_context is not None:
            job_context.progress(
                92,
                total=total,
                message="Checking recurring payments and goal suggestions…",
            )
        _run_post_ingestion_detection(db, result)

        # Finalize
        date_range = f"{after_date} to {today.isoformat()}"
        _update_setting(db, 'initial_sync_date_range', date_range)
        completed = result.source_status in {"complete", "empty"}
        _update_setting(db, 'initial_sync_completed', 'true' if completed else 'false')
        if completed:
            _finalize_successful_range(db, result, start_of_year, today)
            _update_setting(db, 'last_ingestion_run', datetime.now(timezone.utc).isoformat())
            if new_history_id:
                _update_setting(db, 'last_gmail_history_id', new_history_id)
                result.cursor_advanced = True
        _store_last_result(db, result)
        _update_setting(db, 'sync_status', 'completed' if completed else 'partial')
        _update_setting(db, 'sync_result', json.dumps(result.to_dict()))
        _update_setting(db, 'sync_progress_processed', str(total))
        db.commit()
        if job_context is not None:
            job_context.progress(
                99,
                total=total,
                message="Finishing the first Gmail import…",
            )

        logger.info(f"Background initial sync complete: {result.created} created, {result.processed} processed")
        return result.to_dict()

    except JobCancelled:
        db.rollback()
        try:
            _update_setting(db, 'sync_status', 'cancelled')
            _update_setting(db, 'sync_error', '')
            db.commit()
        except Exception:
            db.rollback()
        raise
    except Exception as exc:
        logger.exception(
            "Background initial sync failed",
            extra={
                "operation_id": "gmail_initial_sync",
                "error_code": "GMAIL_SYNC_FAILED",
                "cause_type": type(exc).__name__,
            },
        )
        try:
            _update_setting(db, 'sync_status', 'error')
            _update_setting(
                db,
                'sync_error',
                'Gmail sync could not be completed. Check the connection and try again.',
            )
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()


def run_ingestion_with_dates_background(
    start_date_str: str,
    end_date_str: str,
    job_context: JobContext | None = None,
) -> dict:
    """
    Background task version of date-range ingestion. Opens its own DB session
    and writes progress to app_settings for polling.
    Splits the date range into 7-day batches.
    """
    from datetime import date, timedelta
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        if job_context is not None:
            job_context.progress(
                1,
                message="Preparing the selected Gmail date range…",
            )
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
        if job_context is not None:
            job_context.progress(
                5,
                total=total_batches,
                message=f"Prepared {total_batches} Gmail import batch(es).",
            )

        result = IngestionResult()
        requested_end = end - timedelta(days=1)
        _prepare_result_range(result, start, requested_end)

        for batch_idx, (batch_after, batch_before) in enumerate(batches):
            if job_context is not None:
                job_context.check_cancelled()
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
            if job_context is not None:
                progress = (
                    90
                    if total_batches == 0
                    else 5 + int(((batch_idx + 1) / total_batches) * 85)
                )
                job_context.progress(
                    progress,
                    total=total_batches,
                    message=(
                        f"Imported Gmail batch {batch_idx + 1} "
                        f"of {total_batches}…"
                    ),
                )

        if job_context is not None:
            job_context.progress(
                92,
                total=total_batches,
                message="Checking recurring payments and goal suggestions…",
            )
        _run_post_ingestion_detection(db, result)

        # Finalize
        completed = result.source_status in {"complete", "empty"}
        if completed:
            _finalize_successful_range(db, result, start, requested_end)
            _update_setting(db, 'last_ingestion_run', datetime.now(timezone.utc).isoformat())
        date_range = f"{start_date_str} to {requested_end.isoformat()}"
        _update_setting(db, 'last_manual_ingestion_range', date_range)
        _update_setting(db, 'last_manual_ingestion_date', datetime.now(timezone.utc).isoformat())
        _store_last_result(db, result)
        _update_setting(db, 'ingest_now_status', 'completed' if completed else 'partial')
        _update_setting(db, 'ingest_now_result', json.dumps(result.to_dict()))
        _update_setting(db, 'ingest_now_processed', str(total_batches))
        db.commit()
        if job_context is not None:
            job_context.progress(
                99,
                total=total_batches,
                message="Finishing the Gmail import…",
            )

        logger.info(f"Background date-range ingestion complete: {result.created} created, {result.processed} processed")
        return result.to_dict()

    except JobCancelled:
        db.rollback()
        try:
            _update_setting(db, 'ingest_now_status', 'cancelled')
            _update_setting(db, 'ingest_now_error', '')
            db.commit()
        except Exception:
            db.rollback()
        raise
    except Exception as exc:
        logger.exception(
            "Background date-range ingestion failed",
            extra={
                "operation_id": "gmail_date_range_ingestion",
                "error_code": "GMAIL_INGESTION_FAILED",
                "cause_type": type(exc).__name__,
            },
        )
        try:
            _update_setting(db, 'ingest_now_status', 'error')
            _update_setting(
                db,
                'ingest_now_error',
                'Gmail import could not be completed. Check the connection and try again.',
            )
            db.commit()
        except Exception:
            db.rollback()
        raise
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
    start = date.fromisoformat(after_date)
    exclusive_end = date.fromisoformat(before_date)
    requested_end = exclusive_end - timedelta(days=1)
    _prepare_result_range(result, start, requested_end)

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
        date_range = f"{after_date} to {requested_end.isoformat()}"
        _update_setting(db, 'last_manual_ingestion_range', date_range)
        _update_setting(db, 'last_manual_ingestion_date', datetime.now(timezone.utc).isoformat())

    if result.source_status in {"complete", "empty"}:
        _finalize_successful_range(db, result, start, requested_end)
        _update_setting(db, 'last_ingestion_run', datetime.now(timezone.utc).isoformat())
    _store_last_result(db, result)
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

    history.update(gmail_coverage_summary(db))
    last_result = db.query(AppSetting).filter_by(key=GMAIL_LAST_RESULT_KEY).first()
    try:
        parsed_result = json.loads(last_result.value) if last_result and last_result.value else None
    except (TypeError, json.JSONDecodeError):
        parsed_result = None
    history["last_result"] = parsed_result if isinstance(parsed_result, dict) else None

    return history
