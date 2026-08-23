from __future__ import annotations

import asyncio
import hashlib
import logging
import multiprocessing
import re
import secrets
import sys
import threading
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.v1.entitlements import conditional_entitlement, enforce_feature
from app.core.auth import get_current_user
from app.core.account_balances import (
    balance_at_date,
    record_verified_statement_controls,
)
from app.core.api_errors import APIErrorResponse
from app.core.audit import FinalizedPeriodError
from app.core.classifier import classify_transaction
from app.core.database import get_db
from app.core.errors import LocalOperationError, StateConflictError
from app.core.merchant_memory_service import upsert_merchant_memory
from app.core.import_postprocessing import postprocess_imported_transactions
from app.core.mapped_import import (
    GENERIC_MAPPING_VERSION,
    MappedImportError,
    inspect_mapped_sheet,
    mapping_fingerprint,
    parse_mapped_sheet,
    sample_rows,
    suggested_mapping,
)
from app.core.parsers import account_requirements, parse_registered_statement
from app.core.reconciliation import (
    ReconciliationService,
    import_new_transactions,
    reconcile_statement,
)
from app.core.statement_parser import ParsedStatement
from app.core.transaction_semantics import (
    TransactionSemantic,
    apply_category_semantic,
)
from app.core.transaction_enrichment import refresh_transaction_enrichment
from app.models.account import Account
from app.models.income_source import IncomeSource
from app.models.transaction import Transaction
from app.schemas.statement import (
    IncomeSourceCreate,
    IncomeSourceCreatedResponse,
    IncomeSourceResponse,
    IncomeSourceUpdate,
    IncomeSourceUpdatedResponse,
    MappedImportMapping,
    MappedImportResponse,
    MappedInspectResponse,
    MappedPreviewResponse,
    StatementImportResponse,
    StatementPreviewResponse,
    StatementReconcileResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Helpers ---

def _resolve_account_id(db: Session, statement_type: str, account_id: str = None) -> str:
    """Resolve account_id from statement type if not provided."""
    if account_id:
        acct = db.query(Account).filter_by(id=account_id, is_active=True).first()
        if not acct:
            raise HTTPException(status_code=400, detail="Invalid account_id")
        return account_id

    bank, account_type = account_requirements(statement_type)
    query = db.query(Account).filter_by(is_active=True)
    if bank:
        query = query.filter(Account.bank == bank)
    if account_type:
        query = query.filter(Account.account_type == account_type)
    acct = query.order_by(Account.created_at.asc()).first()

    if not acct:
        raise HTTPException(status_code=400, detail="No matching account found. Please specify account_id.")
    return acct.id


def _statement_balance_snapshot(
    db: Session,
    account_id: str,
    parse_result,
) -> dict[str, object]:
    statement_balance = parse_result.closing_balance
    if parse_result.period_end is None:
        return {
            "statement_closing_balance": statement_balance,
            "computed_balance": None,
            "balance_discrepancy": None,
            "balance_status": "unverified_no_anchor",
            "coverage_complete": False,
            "missing_ranges": [],
        }
    result = balance_at_date(db, account_id, parse_result.period_end)
    computed = float(result.balance) if result.balance is not None else None
    discrepancy = (
        round(float(statement_balance) - computed, 2)
        if statement_balance is not None and computed is not None
        else None
    )
    return {
        "statement_closing_balance": statement_balance,
        "computed_balance": computed,
        "balance_discrepancy": discrepancy,
        "balance_status": result.status,
        "coverage_complete": result.coverage_complete,
        "missing_ranges": list(result.missing_ranges),
    }


async def _read_mapped_sheet(file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    if not file.filename.lower().endswith((".csv", ".xlsx")):
        raise HTTPException(
            status_code=400,
            detail="Guided mapping supports CSV and XLSX files.",
        )
    contents_buffer = bytearray()
    while True:
        chunk = await file.read(STATEMENT_READ_CHUNK_BYTES)
        if not chunk:
            break
        contents_buffer.extend(chunk)
        if len(contents_buffer) > MAX_STATEMENT_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    try:
        return inspect_mapped_sheet(bytes(contents_buffer), file.filename)
    except MappedImportError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "GODFIN could not safely read this spreadsheet. Check that it "
                "is a single-sheet UTF-8 CSV or XLSX within the stated limits."
            ),
        ) from exc


def _mapped_mapping(mapping_json: str) -> MappedImportMapping:
    try:
        return MappedImportMapping.model_validate_json(mapping_json)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail="The selected spreadsheet columns are incomplete or invalid.",
        ) from exc


def _mapped_account(db: Session, account_id: str) -> Account:
    enforce_feature(db, "generic_mapped_import")
    account = (
        db.query(Account)
        .filter_by(id=account_id, is_active=True)
        .first()
    )
    if not account:
        raise HTTPException(status_code=400, detail="Select an active account.")
    return account


def _validate_mapped_account_identity(
    account: Account,
    identifiers: tuple[str, ...],
) -> None:
    for identifier in identifiers:
        digits = re.sub(r"\D", "", identifier)
        if len(digits) >= 4 and digits[-4:] != account.last_4_digits:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The mapped account identifier does not match the selected "
                    "account's last four digits."
                ),
            )


def _mapped_preview_rows(statement, limit: int = 100) -> list[dict[str, object]]:
    return [
        {
            "date": str(transaction.date),
            "description": transaction.description,
            "amount": transaction.amount,
            "type": transaction.txn_type,
            "reference": transaction.ref_number,
            "instrument": transaction.instrument,
            "is_transfer": transaction.is_transfer,
            "is_income": transaction.is_income,
            "semantic_type": transaction.semantic_type,
            "merchant_name": transaction.merchant_name,
        }
        for transaction in statement.transactions[:limit]
    ]


SUPPORTED_EXTENSIONS = ('.pdf', '.xls', '.xlsx')
MAX_STATEMENT_BYTES = 10 * 1024 * 1024
STATEMENT_READ_CHUNK_BYTES = 1024 * 1024
MAX_PARSED_TRANSACTIONS = 10_000
PARSER_TIMEOUT_SECONDS = 45.0
PARSER_MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024
_PARSER_SLOTS = threading.BoundedSemaphore(value=2)


class StatementParserTimeout(RuntimeError):
    """A statement parser worker exceeded its interactive safety budget."""


class StatementParserWorkerError(RuntimeError):
    """A statement parser worker crashed or returned an invalid result."""


def _apply_parser_memory_limit() -> None:
    """Bound parser address space on Linux without weakening portability."""
    if not sys.platform.startswith("linux"):
        return
    try:
        import resource

        resource.setrlimit(
            resource.RLIMIT_AS,
            (PARSER_MEMORY_LIMIT_BYTES, PARSER_MEMORY_LIMIT_BYTES),
        )
    except (ImportError, OSError, ValueError):
        # Windows and macOS use the same process/timeout isolation, but do not
        # expose a dependable per-child address-space limit through stdlib.
        return


def _statement_parser_worker(
    send_connection,
    contents: bytes,
    file_format: str,
    password: Optional[str],
) -> None:
    """Parse one untrusted statement in a disposable child process."""
    try:
        _apply_parser_memory_limit()
        result = parse_registered_statement(contents, file_format, password)
        if len(result.transactions) > MAX_PARSED_TRANSACTIONS:
            result.transactions.clear()
            result.reconciliation_status = "failed"
            result.errors.append(
                f"Statement exceeds the {MAX_PARSED_TRANSACTIONS:,}-row review limit"
            )
        send_connection.send(("ok", result))
    except BaseException:
        # Deliberately do not send exception text or a traceback across the
        # trust boundary; parser/library errors may contain private file data.
        try:
            send_connection.send(("error", None))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        send_connection.close()


def _terminate_parser_process(process: multiprocessing.Process) -> None:
    if not process.is_alive():
        process.join(timeout=0.2)
        return
    process.terminate()
    process.join(timeout=2.0)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=1.0)


def _run_parser_process(
    contents: bytes,
    file_format: str,
    password: Optional[str],
    cancel_event: threading.Event,
    *,
    timeout_seconds: float = PARSER_TIMEOUT_SECONDS,
):
    """Run and supervise one parser process with timeout and cancellation."""
    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_statement_parser_worker,
        args=(send_connection, contents, file_format, password),
        daemon=True,
        name="godfin-statement-parser",
    )
    started_at = time.monotonic()
    process_started = False
    try:
        process.start()
        process_started = True
        send_connection.close()
        while True:
            if cancel_event.is_set():
                raise asyncio.CancelledError
            if receive_connection.poll(0.05):
                try:
                    status, payload = receive_connection.recv()
                except EOFError as exc:
                    raise StatementParserWorkerError(
                        "The statement parser stopped unexpectedly."
                    ) from exc
                process.join(timeout=1.0)
                if status != "ok" or payload is None:
                    raise StatementParserWorkerError(
                        "The statement parser could not inspect this file safely."
                    )
                return payload
            if not process.is_alive():
                process.join(timeout=0.2)
                raise StatementParserWorkerError(
                    "The statement parser stopped unexpectedly."
                )
            if time.monotonic() - started_at >= timeout_seconds:
                raise StatementParserTimeout(
                    "Statement inspection exceeded the safe time limit."
                )
    finally:
        receive_connection.close()
        send_connection.close()
        if process_started:
            _terminate_parser_process(process)


async def _parse_in_isolated_process(
    contents: bytes,
    file_format: str,
    password: Optional[str],
):
    cancel_event = threading.Event()
    task = asyncio.create_task(
        asyncio.to_thread(
            _run_parser_process,
            contents,
            file_format,
            password,
            cancel_event,
        )
    )
    try:
        return await task
    except asyncio.CancelledError:
        cancel_event.set()
        try:
            await asyncio.shield(task)
        except (asyncio.CancelledError, StatementParserTimeout, StatementParserWorkerError):
            pass
        raise


def _detect_file_format(filename: str, contents: bytes) -> str:
    """Detect file format from magic bytes, falling back to extension."""
    if contents[:5].startswith(b'%PDF-'):
        return 'pdf'
    if contents[:4] == b'\xd0\xcf\x11\xe0':  # OLE2 compound document (.xls)
        return 'xls'
    if contents[:2] == b'PK':  # ZIP-based (.xlsx)
        return 'xlsx'
    # Fallback to extension
    lower = filename.lower()
    if lower.endswith('.xls'):
        return 'xls'
    if lower.endswith('.xlsx'):
        return 'xlsx'
    if lower.endswith('.pdf'):
        return 'pdf'
    return 'unknown'


async def _read_and_parse(file: UploadFile, password: Optional[str]):
    """Read file and parse PDF or XLS, returning the parse result."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    lower_name = file.filename.lower()
    if not any(lower_name.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Supported formats: PDF, XLS, XLSX")

    contents_buffer = bytearray()
    while True:
        chunk = await file.read(STATEMENT_READ_CHUNK_BYTES)
        if not chunk:
            break
        contents_buffer.extend(chunk)
        if len(contents_buffer) > MAX_STATEMENT_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    contents = bytes(contents_buffer)

    fmt = _detect_file_format(file.filename, contents)

    if fmt not in {"pdf", "xls", "xlsx"}:
        raise HTTPException(status_code=400, detail="Unrecognized file format")
    if not _PARSER_SLOTS.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Two statements are already being inspected. Try again shortly.",
            headers={"Retry-After": "3"},
        )
    try:
        try:
            parse_result = await _parse_in_isolated_process(contents, fmt, password)
        except StatementParserTimeout as exc:
            raise HTTPException(
                status_code=408,
                detail="Statement inspection timed out. Try a smaller statement.",
            ) from exc
        except StatementParserWorkerError as exc:
            raise HTTPException(
                status_code=422,
                detail="The statement could not be inspected safely.",
            ) from exc
    finally:
        _PARSER_SLOTS.release()
    parse_result.source_digest = hashlib.sha256(contents).hexdigest()

    if parse_result.errors:
        raise HTTPException(
            status_code=400,
            detail=f"Parse errors: {'; '.join(parse_result.errors)}",
        )

    if not parse_result.transactions:
        raise HTTPException(
            status_code=400,
            detail="No transactions found in statement",
        )

    if not parse_result.recognized or parse_result.reconciliation_status != "passed":
        raise HTTPException(
            status_code=400,
            detail="Statement type or financial controls could not be verified",
        )

    return parse_result


# --- Guided CSV/XLSX mapping ---

@router.post(
    "/ingest/mapped/inspect",
    response_model=MappedInspectResponse,
)
@conditional_entitlement("generic_mapped_import")
async def inspect_mapped_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    enforce_feature(db, "generic_mapped_import")
    sheet = await _read_mapped_sheet(file)
    data_rows = sum(
        1
        for row in sheet.rows[sheet.header_row + 1 :]
        if any(str(value or "").strip() for value in row)
    )
    return {
        "file_format": sheet.file_format,
        "source_fingerprint": sheet.source_fingerprint,
        "header_signature": sheet.header_signature,
        "header_row": sheet.header_row + 1,
        "row_count": data_rows,
        "columns": [
            {"index": index, "label": label}
            for index, label in enumerate(sheet.headers)
        ],
        "sample_rows": sample_rows(sheet),
        "suggested_mapping": suggested_mapping(sheet.headers),
    }


@router.post(
    "/ingest/mapped/preview",
    response_model=MappedPreviewResponse,
)
@conditional_entitlement("generic_mapped_import")
async def preview_mapped_import(
    file: UploadFile = File(...),
    account_id: str = Form(..., min_length=1, max_length=36),
    mapping_json: str = Form(..., min_length=2, max_length=2_000),
    date_format: str = Form(
        "dd/mm/yyyy",
        pattern=r"^(auto|dd/mm/yyyy|dd-mm-yyyy|yyyy-mm-dd|mm/dd/yyyy)$",
    ),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    account = _mapped_account(db, account_id)
    sheet = await _read_mapped_sheet(file)
    mapping = _mapped_mapping(mapping_json)
    try:
        parsed = parse_mapped_sheet(sheet, mapping, date_format=date_format)
    except MappedImportError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "The selected columns or date style cannot be used safely. "
                "Review the mapping and try again."
            ),
        ) from exc
    _validate_mapped_account_identity(account, parsed.identifiers)

    reconciliation = None
    if not parsed.errors:
        reconciliation = ReconciliationService.reconcile(
            db,
            ParsedStatement.from_statement_result(parsed.statement),
            account.id,
        )
    mapped_fingerprint = mapping_fingerprint(sheet, mapping, date_format)
    return {
        "account_id": account.id,
        "source_fingerprint": sheet.source_fingerprint,
        "mapping_fingerprint": mapped_fingerprint,
        "header_signature": sheet.header_signature,
        "parser_profile": "generic_mapped",
        "mapping_version": GENERIC_MAPPING_VERSION,
        "total_rows": len(parsed.statement.transactions) + len(parsed.errors),
        "matched_count": (
            len(reconciliation.duplicate_transactions) if reconciliation else 0
        ),
        "possible_count": (
            len(reconciliation.potential_duplicates) if reconciliation else 0
        ),
        "new_count": reconciliation.total_new if reconciliation else 0,
        "preview_rows": _mapped_preview_rows(parsed.statement),
        "preview_truncated": len(parsed.statement.transactions) > 100,
        "total_debits": parsed.statement.total_debits or 0,
        "total_credits": parsed.statement.total_credits or 0,
        "running_balance_mapped": mapping.running_balance_column is not None,
        "balance_controls_verified": (
            parsed.statement.reconciliation_status == "passed"
        ),
        "opening_balance": parsed.statement.opening_balance,
        "closing_balance": parsed.statement.closing_balance,
        "status": "needs_review" if parsed.errors else "ready",
        "errors": [error.to_dict() for error in parsed.errors],
        "account_identifiers": [
            f"••••{re.sub(r'\D', '', value)[-4:]}"
            if len(re.sub(r"\D", "", value)) >= 4
            else "Present"
            for value in parsed.identifiers
        ],
    }


@router.post(
    "/ingest/mapped/import",
    response_model=MappedImportResponse,
)
@conditional_entitlement("generic_mapped_import")
async def import_mapped_spreadsheet(
    file: UploadFile = File(...),
    account_id: str = Form(..., min_length=1, max_length=36),
    mapping_json: str = Form(..., min_length=2, max_length=2_000),
    date_format: str = Form(
        "dd/mm/yyyy",
        pattern=r"^(auto|dd/mm/yyyy|dd-mm-yyyy|yyyy-mm-dd|mm/dd/yyyy)$",
    ),
    confirm_mapping: bool = Form(False),
    accepted_fingerprint: str = Form(..., min_length=64, max_length=64),
    accepted_mapping_fingerprint: str = Form(..., min_length=64, max_length=64),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    try:
        if not confirm_mapping:
            raise HTTPException(
                status_code=400,
                detail="Review the mapped rows and explicitly confirm before importing.",
            )
        account = _mapped_account(db, account_id)
        sheet = await _read_mapped_sheet(file)
        mapping = _mapped_mapping(mapping_json)
        mapped_fingerprint = mapping_fingerprint(sheet, mapping, date_format)
        if not secrets.compare_digest(
            accepted_fingerprint.lower(), sheet.source_fingerprint
        ) or not secrets.compare_digest(
            accepted_mapping_fingerprint.lower(), mapped_fingerprint
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "The file or its column mapping changed after review. "
                    "Preview it again before importing."
                ),
            )
        parsed = parse_mapped_sheet(sheet, mapping, date_format=date_format)
        _validate_mapped_account_identity(account, parsed.identifiers)
        if parsed.errors:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Fix every highlighted spreadsheet row before importing. "
                    "No rows were saved."
                ),
            )

        statement = ParsedStatement.from_statement_result(parsed.statement)
        reconciliation = ReconciliationService.reconcile(
            db, statement, account.id
        )
        imported = import_new_transactions(
            db,
            reconciliation.new_transactions,
            account.id,
            source="mapped_import",
        )
        postprocess = postprocess_imported_transactions(
            db,
            imported,
            reconciliation.new_transactions,
        )
        controls_verified = parsed.statement.reconciliation_status == "passed"
        if controls_verified and not reconciliation.potential_duplicates:
            record_verified_statement_controls(db, account.id, parsed.statement)
        db.commit()
        balance_snapshot = _statement_balance_snapshot(
            db, account.id, parsed.statement
        )
        return {
            "source_fingerprint": sheet.source_fingerprint,
            "mapping_fingerprint": mapped_fingerprint,
            "total_parsed": reconciliation.total_parsed,
            "imported": len(imported),
            "skipped_duplicate": len(reconciliation.duplicate_transactions),
            "possible_duplicate": len(reconciliation.potential_duplicates),
            "classified": postprocess.classified,
            "review_queue": postprocess.review_queue,
            "balance_controls_verified": controls_verified,
            "balance_status": balance_snapshot["balance_status"],
            "coverage_complete": bool(balance_snapshot["coverage_complete"]),
            "errors": [],
        }
    except FinalizedPeriodError as exc:
        db.rollback()
        raise StateConflictError(
            code="FINALIZED_PERIOD_READ_ONLY",
            message=(
                "This spreadsheet includes a finalized month that is read-only. "
                "Reopen the month before importing."
            ),
            hint="Reopen that month before importing these transactions.",
        ) from exc
    except HTTPException:
        db.rollback()
        raise
    except MappedImportError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=(
                "The reviewed spreadsheet mapping is no longer valid. "
                "Preview the file again before importing."
            ),
        ) from exc
    except Exception as exc:
        db.rollback()
        raise LocalOperationError(
            code="MAPPED_IMPORT_FAILED",
            message="GODFIN could not complete this spreadsheet import.",
            hint="No partial import was kept. Review the mapping and try again.",
            status_code=503,
        ) from exc


# --- Statement Upload (3-step flow) ---

@router.post(
    "/ingest/upload/preview",
    response_model=StatementPreviewResponse,
)
async def preview_statement(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Step 1: Parse PDF and return transaction preview. No database writes."""
    parse_result = await _read_and_parse(file, password)

    # Convert to ParsedStatement for consistent output
    parsed = ParsedStatement.from_statement_result(parse_result)

    return {
        "statement_type": parse_result.statement_type,
        "parser_profile": parse_result.parser_profile,
        "recognized": parse_result.recognized,
        "reconciliation_status": parse_result.reconciliation_status,
        "reconciliation_method": parse_result.reconciliation_method,
        "parse_fingerprint": parse_result.source_digest,
        "period_start": str(parse_result.period_start) if parse_result.period_start else None,
        "period_end": str(parse_result.period_end) if parse_result.period_end else None,
        "control_totals": {
            "opening_balance": parse_result.opening_balance,
            "closing_balance": parse_result.closing_balance,
            "total_debits": parse_result.total_debits,
            "total_credits": parse_result.total_credits,
        },
        "total_transactions": len(parsed.transactions),
        "transactions": [
            {
                "date": str(t.date),
                "description": t.description,
                "amount": t.amount,
                "type": t.type,
                "reference": t.reference,
                "instrument": t.instrument,
                "is_transfer": t.is_transfer,
                "is_income": t.is_income,
                "semantic_type": t.semantic_type,
                "merchant_name": t.merchant_name,
            }
            for t in parsed.transactions
        ],
    }


@router.post(
    "/ingest/upload/reconcile",
    response_model=StatementReconcileResponse,
)
async def reconcile_statement_preview(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    account_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Step 2: Parse + reconcile against existing transactions. No imports."""
    parse_result = await _read_and_parse(file, password)
    parsed = ParsedStatement.from_statement_result(parse_result)

    resolved_account_id = _resolve_account_id(db, parse_result.statement_type, account_id)

    recon_result = ReconciliationService.reconcile(db, parsed, resolved_account_id)
    income_txns = ReconciliationService.detect_income_sources(db, parsed)

    balance_snapshot = _statement_balance_snapshot(
        db, resolved_account_id, parse_result
    )

    return {
        "account_id": resolved_account_id,
        "statement_type": parse_result.statement_type,
        "parser_profile": parse_result.parser_profile,
        "reconciliation_status": parse_result.reconciliation_status,
        "reconciliation_method": parse_result.reconciliation_method,
        "parse_fingerprint": parse_result.source_digest,
        "control_totals": {
            "opening_balance": parse_result.opening_balance,
            "closing_balance": parse_result.closing_balance,
            "total_debits": parse_result.total_debits,
            "total_credits": parse_result.total_credits,
        },
        "total_parsed": recon_result.total_parsed,
        "matched_count": len(recon_result.duplicate_transactions),
        "possible_count": len(recon_result.potential_duplicates),
        "new_count": recon_result.total_new,
        "income_count": len(income_txns),
        **balance_snapshot,
        "new_transactions": [
            {
                "date": str(t.date),
                "description": t.description,
                "amount": t.amount,
                "type": t.type,
            }
            for t in recon_result.new_transactions
        ],
        "potential_duplicates": [
            {
                "parsed": {
                    "date": str(p.date),
                    "description": p.description,
                    "amount": p.amount,
                },
                "existing": {
                    "id": e.id,
                    "date": str(e.date),
                    "merchant": e.merchant_normalized or e.merchant_raw,
                    "amount": float(e.amount),
                },
            }
            for p, e in recon_result.potential_duplicates
        ],
        "income_detected": [
            {
                "date": str(t.date),
                "description": t.description,
                "amount": t.amount,
            }
            for t in income_txns
        ],
    }


@router.post(
    "/ingest/upload/import",
    response_model=StatementImportResponse,
)
async def import_statement(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    account_id: Optional[str] = Form(None),
    import_new: bool = Form(True),
    detect_income: bool = Form(True),
    confirm_reconciled: bool = Form(False),
    accepted_fingerprint: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Step 3: Parse + reconcile + import new transactions with classification."""
    try:
        parse_result = await _read_and_parse(file, password)
        if not confirm_reconciled:
            raise HTTPException(
                status_code=400,
                detail="Review the reconciled preview and explicitly confirm before importing",
            )
        if (
            not accepted_fingerprint
            or len(accepted_fingerprint) != 64
            or not secrets.compare_digest(
                accepted_fingerprint.lower(),
                parse_result.source_digest,
            )
        ):
            raise HTTPException(
                status_code=409,
                detail="The selected file changed after review; preview it again before importing",
            )
        parsed = ParsedStatement.from_statement_result(parse_result)

        resolved_account_id = _resolve_account_id(db, parse_result.statement_type, account_id)

        recon_result = ReconciliationService.reconcile(db, parsed, resolved_account_id)

        imported_count = 0
        classified_count = 0
        review_queue_count = 0
        imported_txns = []

        if import_new and recon_result.new_transactions:
            imported_txns = import_new_transactions(
                db, recon_result.new_transactions, resolved_account_id
            )
            imported_count = len(imported_txns)

            # Classify each imported transaction and update merchant memory
            for i, txn in enumerate(imported_txns):
                # Get corresponding parsed transaction for narration hints
                parsed_txn = recon_result.new_transactions[i] if i < len(recon_result.new_transactions) else None

                try:
                    classification = classify_transaction(
                        db,
                        txn.merchant_normalized or txn.merchant_raw or '',
                        float(txn.amount),
                        txn.instrument or 'statement',
                        vpa_handle=txn.vpa_handle,
                    )
                    if classification.category:
                        txn.category = classification.category
                        txn.subcategory = classification.subcategory
                        txn.confidence = classification.confidence
                        txn.classification_source = classification.source
                        apply_category_semantic(
                            txn,
                            explicitly_classified=classification.source
                            in {"exact_match", "confirmed_pattern", "rule"},
                        )
                        classified_count += 1

                        # Update merchant memory for future classifications
                        upsert_merchant_memory(
                            db,
                            txn.merchant_normalized or txn.merchant_raw or '',
                            classification.category,
                            classification.subcategory,
                            classification.confidence,
                        )
                    elif parsed_txn and parsed_txn.category_hint:
                        # Classifier failed — use parser's narration-based hint as fallback
                        txn.category = parsed_txn.category_hint
                        txn.subcategory = getattr(parsed_txn, 'subcategory_hint', None)
                        txn.confidence = 0.65
                        txn.classification_source = 'narration_hint'
                        apply_category_semantic(
                            txn,
                            explicitly_classified=(
                                getattr(parsed_txn, 'semantic_type', None)
                                == TransactionSemantic.INCOME.value
                            ),
                        )
                        classified_count += 1
                    refresh_transaction_enrichment(txn)
                    if txn.review_required:
                        review_queue_count += 1
                except Exception as e:
                    logger.warning(f"Classification failed for {txn.merchant_raw}: {e}")
                    txn.review_required = True
                    review_queue_count += 1

            merchant_keys = {
                (txn.merchant_normalized, txn.account_id)
                for txn in imported_txns
                if txn.merchant_normalized
            }
            if merchant_keys:
                from app.core.goal_contributions import (
                    detect_goal_contribution_suggestions,
                )
                from app.core.license import has_feature
                from app.core.product_depth import sync_subscription_suggestions
                from app.core.recurring import detect_recurring_patterns

                detect_recurring_patterns(db, merchant_keys=merchant_keys)
                sync_subscription_suggestions(db, run_detection=False)
                if has_feature(db, "fd_rd_goal_detection"):
                    detect_goal_contribution_suggestions(
                        db, transactions=imported_txns
                    )

        # Detect income
        income_items = []
        if detect_income:
            income_txns = ReconciliationService.detect_income_sources(db, parsed)
            income_items = [
                {
                    "date": str(t.date),
                    "description": t.description,
                    "amount": t.amount,
                }
                for t in income_txns
            ]

        if import_new and not recon_result.potential_duplicates:
            record_verified_statement_controls(
                db,
                resolved_account_id,
                parse_result,
            )

        db.commit()
        balance_snapshot = _statement_balance_snapshot(
            db, resolved_account_id, parse_result
        )

        return {
            "statement_type": parse_result.statement_type,
            "total_parsed": recon_result.total_parsed,
            "matched": len(recon_result.duplicate_transactions),
            "skipped_dup": len(recon_result.duplicate_transactions),
            "possible": len(recon_result.potential_duplicates),
            "new_imported": imported_count,
            "imported": imported_count,
            "classified": classified_count,
            "review_queue": review_queue_count,
            "errors": [],
            "income_detected": len(income_items),
            "income_items": income_items,
            **balance_snapshot,
        }
    except FinalizedPeriodError as exc:
        db.rollback()
        raise StateConflictError(
            code="FINALIZED_PERIOD_READ_ONLY",
            message=(
                "This statement includes a finalized month that is read-only. "
                "Reopen the month before importing."
            ),
            hint="Reopen that month before importing these transactions.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise LocalOperationError(
            code="STATEMENT_IMPORT_FAILED",
            message="GODFIN could not complete this statement import.",
            hint="No partial import was kept. Review the file and try again.",
            status_code=503,
        ) from exc


@router.post(
    "/ingest/upload",
    status_code=410,
    response_model=APIErrorResponse,
)
async def upload_statement_legacy(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    """Retired because one-step imports bypass explicit reconciliation review."""
    raise HTTPException(
        status_code=410,
        detail="One-step import was retired. Use preview, reconcile, then confirmed import.",
    )


# --- Income Sources ---

@router.get("/income-sources", response_model=list[IncomeSourceResponse])
def list_income_sources(
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    sources = db.query(IncomeSource).filter_by(is_active=True).all()
    return [
        {
            "id": s.id,
            "source_name": s.source_name,
            "expected_amount": s.expected_amount,
            "frequency": s.frequency,
            "last_detected_date": str(s.last_detected_date) if s.last_detected_date else None,
            "last_detected_amount": s.last_detected_amount,
            "is_active": s.is_active,
        }
        for s in sources
    ]


@router.post(
    "/income-sources",
    response_model=IncomeSourceCreatedResponse,
    status_code=201,
)
def create_income_source(
    body: IncomeSourceCreate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    source = IncomeSource(
        source_name=body.source_name,
        expected_amount=body.expected_amount,
        frequency=body.frequency,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return {
        "id": source.id,
        "source_name": source.source_name,
        "expected_amount": source.expected_amount,
        "frequency": source.frequency,
    }


@router.put(
    "/income-sources/{source_id}",
    response_model=IncomeSourceUpdatedResponse,
)
def update_income_source(
    source_id: str,
    body: IncomeSourceUpdate,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    if body.source_name is not None:
        source.source_name = body.source_name
    if body.expected_amount is not None:
        source.expected_amount = body.expected_amount
    if body.frequency is not None:
        source.frequency = body.frequency
    if body.is_active is not None:
        source.is_active = body.is_active

    db.commit()
    return {"id": source.id, "source_name": source.source_name, "status": "updated"}


@router.delete("/income-sources/{source_id}", status_code=204)
def delete_income_source(
    source_id: str,
    db: Session = Depends(get_db),
    _user: bool = Depends(get_current_user),
):
    source = db.query(IncomeSource).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")

    source.is_active = False
    db.commit()
