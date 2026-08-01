from __future__ import annotations

import io
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List, Optional

import pdfplumber
import xlrd

from app.core.transaction_semantics import contains_semantic_term

logger = logging.getLogger(__name__)


@dataclass
class StatementTransaction:
    date: date
    description: str
    amount: float
    txn_type: str  # 'debit' or 'credit'
    ref_number: Optional[str] = None
    closing_balance: Optional[float] = None
    value_date: Optional[date] = None
    instrument: Optional[str] = None  # 'upi', 'debit_card', 'neft', 'savings_account'
    is_transfer: bool = False
    is_income: bool = False
    semantic_type: str = "unknown"
    vpa_handle: Optional[str] = None
    upi_ref_number: Optional[str] = None
    suggested_category: Optional[str] = None
    suggested_subcategory: Optional[str] = None
    merchant_name: Optional[str] = None


# Aliases for compatibility with GLM reconciliation service
@dataclass
class ParsedTransaction:
    """Represents a parsed transaction from a statement (GLM compatibility alias)"""
    date: date
    description: str
    amount: float
    type: str  # 'debit' or 'credit'
    balance: Optional[float] = None
    reference: Optional[str] = None
    category_hint: Optional[str] = None
    subcategory_hint: Optional[str] = None
    instrument: Optional[str] = None
    is_transfer: bool = False
    is_income: bool = False
    semantic_type: str = "unknown"
    vpa_handle: Optional[str] = None
    upi_ref_number: Optional[str] = None
    merchant_name: Optional[str] = None

    @classmethod
    def from_statement_transaction(cls, st: StatementTransaction) -> 'ParsedTransaction':
        """Convert StatementTransaction to ParsedTransaction"""
        return cls(
            date=st.date,
            description=st.description,
            amount=st.amount,
            type=st.txn_type,
            balance=st.closing_balance,
            reference=st.ref_number,
            category_hint=st.suggested_category,
            subcategory_hint=st.suggested_subcategory,
            instrument=st.instrument,
            is_transfer=st.is_transfer,
            is_income=st.is_income,
            semantic_type=st.semantic_type,
            vpa_handle=st.vpa_handle,
            upi_ref_number=st.upi_ref_number,
            merchant_name=st.merchant_name,
        )


@dataclass
class StatementMetadata:
    """Metadata extracted from statement (GLM compatibility)"""
    statement_type: str
    account_number: str = ''
    statement_period: str = ''
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    total_debits: Optional[float] = None
    total_credits: Optional[float] = None


@dataclass
class ParsedStatement:
    """Complete parsed statement (GLM compatibility alias)"""
    metadata: StatementMetadata
    transactions: List[ParsedTransaction]

    @classmethod
    def from_statement_result(cls, result: StatementParseResult) -> 'ParsedStatement':
        """Convert StatementParseResult to ParsedStatement"""
        metadata = StatementMetadata(
            statement_type=result.statement_type,
            account_number='',
            statement_period=f"{result.period_start} to {result.period_end}" if result.period_start and result.period_end else '',
            opening_balance=result.opening_balance,
            closing_balance=result.closing_balance,
            total_debits=result.total_debits,
            total_credits=result.total_credits,
        )
        transactions = [ParsedTransaction.from_statement_transaction(t) for t in result.transactions]
        return cls(metadata=metadata, transactions=transactions)


@dataclass
class StatementParseResult:
    transactions: list[StatementTransaction] = field(default_factory=list)
    statement_type: str = ''  # 'hdfc_savings' or 'hdfc_credit_card'
    parser_profile: str = ''
    recognized: bool = False
    reconciliation_status: str = 'not_checked'
    reconciliation_method: str = ''
    source_digest: str = ''
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    total_debits: Optional[float] = None
    total_credits: Optional[float] = None
    errors: list[str] = field(default_factory=list)


_MONEY_QUANTUM = Decimal("0.01")


def _money_decimal(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _append_strict_savings_txn(
    raw: dict,
    txns_out: list[StatementTransaction],
    errors: list[str],
    *,
    row_label: str,
) -> None:
    """Append one explicit savings row or record why the row is unsafe.

    Debit/credit direction must come from the statement's withdrawal/deposit
    columns. Running balances are controls only; they are never substituted for
    a transaction amount.
    """
    transaction_date = raw.get("date")
    narration = str(raw.get("narration") or "").strip()
    withdrawal = _money_decimal(raw.get("withdrawal"))
    deposit = _money_decimal(raw.get("deposit"))
    balance = _money_decimal(raw.get("balance"))

    if transaction_date is None:
        errors.append(f"{row_label}: missing or invalid transaction date")
        return
    if not narration:
        errors.append(f"{row_label}: missing transaction narration")
        return

    has_withdrawal = withdrawal is not None and withdrawal > 0
    has_deposit = deposit is not None and deposit > 0
    if has_withdrawal and has_deposit:
        errors.append(f"{row_label}: both withdrawal and deposit are populated")
        return
    if not has_withdrawal and not has_deposit:
        errors.append(f"{row_label}: exactly one explicit withdrawal or deposit is required")
        return
    if balance is None:
        errors.append(f"{row_label}: closing balance is required for reconciliation")
        return

    normalized = dict(raw)
    normalized["narration"] = narration
    normalized["withdrawal"] = float(withdrawal) if has_withdrawal else None
    normalized["deposit"] = float(deposit) if has_deposit else None
    normalized["balance"] = float(balance)
    _finalize_savings_txn(normalized, txns_out)


def _validate_savings_controls(result: StatementParseResult) -> None:
    """Fail the complete savings parse unless running balances reconcile."""
    result.reconciliation_status = "failed"
    if result.errors:
        result.transactions.clear()
        return
    if len(result.transactions) < 2:
        result.errors.append(
            "Savings statement needs at least two explicit rows to verify balance continuity",
        )
        result.transactions.clear()
        return

    for index, transaction in enumerate(result.transactions, start=1):
        if (
            transaction.txn_type not in {"debit", "credit"}
            or not math.isfinite(float(transaction.amount))
            or float(transaction.amount) <= 0
            or _money_decimal(transaction.closing_balance) is None
        ):
            result.errors.append(f"Transaction {index} has invalid financial controls")
            result.transactions.clear()
            return

    def ordered_candidate(transactions: list[StatementTransaction]) -> bool:
        return all(
            left.date <= right.date
            for left, right in zip(transactions, transactions[1:])
        )

    def continuity_error(transactions: list[StatementTransaction]) -> Optional[str]:
        for index in range(1, len(transactions)):
            previous = transactions[index - 1]
            current = transactions[index]
            previous_balance = _money_decimal(previous.closing_balance)
            current_balance = _money_decimal(current.closing_balance)
            amount = _money_decimal(current.amount)
            assert previous_balance is not None
            assert current_balance is not None
            assert amount is not None
            signed_amount = amount if current.txn_type == "credit" else -amount
            expected = (previous_balance + signed_amount).quantize(
                _MONEY_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
            if expected != current_balance:
                return (
                    "Savings balance continuity failed between rows "
                    f"{index} and {index + 1}: expected {expected}, "
                    f"statement shows {current_balance}"
                )
        return None

    original = list(result.transactions)
    reversed_rows = list(reversed(result.transactions))
    candidates = [rows for rows in (original, reversed_rows) if ordered_candidate(rows)]
    passing: Optional[list[StatementTransaction]] = None
    failures: list[str] = []
    for candidate in candidates:
        error = continuity_error(candidate)
        if error is None:
            passing = candidate
            break
        failures.append(error)

    if passing is None:
        result.errors.append(
            failures[0]
            if failures
            else "Transaction dates are not consistently chronological or reverse chronological",
        )
        result.transactions.clear()
        return

    first = passing[0]
    last = passing[-1]
    first_balance = _money_decimal(first.closing_balance)
    first_amount = _money_decimal(first.amount)
    assert first_balance is not None
    assert first_amount is not None
    first_signed = first_amount if first.txn_type == "credit" else -first_amount
    opening = (first_balance - first_signed).quantize(
        _MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    debits = sum(
        (
            (_money_decimal(txn.amount) or Decimal("0"))
            for txn in result.transactions
            if txn.txn_type == "debit"
        ),
        start=Decimal("0"),
    )
    credits = sum(
        (
            (_money_decimal(txn.amount) or Decimal("0"))
            for txn in result.transactions
            if txn.txn_type == "credit"
        ),
        start=Decimal("0"),
    )

    result.opening_balance = float(opening)
    result.closing_balance = float(_money_decimal(last.closing_balance) or Decimal("0"))
    result.total_debits = float(debits.quantize(_MONEY_QUANTUM))
    result.total_credits = float(credits.quantize(_MONEY_QUANTUM))
    result.period_start = result.period_start or min(txn.date for txn in result.transactions)
    result.period_end = result.period_end or max(txn.date for txn in result.transactions)
    result.reconciliation_status = "passed"
    result.reconciliation_method = "explicit_columns_and_running_balance"


def parse_statement_xls(file_bytes: bytes) -> StatementParseResult:
    """Parse HDFC savings account XLS statement.

    XLS format has clean one-row-per-transaction layout:
    - Metadata rows at top (account number, period, etc.)
    - Header row: Date | Narration | Chq./Ref.No. | Value Dt | Withdrawal Amt. | Deposit Amt. | Closing Balance
    - Data rows until separator (********) or empty date
    """
    result = StatementParseResult(
        statement_type='hdfc_savings',
        parser_profile='hdfc_savings',
    )

    try:
        wb = xlrd.open_workbook(file_contents=file_bytes)
        sheet = wb.sheet_by_index(0)
    except Exception as e:
        result.errors.append(f"Failed to open XLS: {e}")
        return result

    # Find header row and extract metadata
    header_row = None
    col_map: dict[str, int] = {}

    bank_fingerprint = False
    for i in range(min(sheet.nrows, 30)):
        row_vals = [str(sheet.cell_value(i, j)).strip() for j in range(sheet.ncols)]
        row_upper = ' '.join(row_vals).upper()
        if 'HDFC' in row_upper:
            bank_fingerprint = True

        # Extract metadata
        if 'ACCOUNT NO' in row_upper:
            for v in row_vals:
                if v and v.replace(' ', '').isdigit() and len(v.replace(' ', '')) >= 8:
                    # Found account number
                    break
        if 'STATEMENT FROM' in row_upper or 'FROM :' in row_upper:
            # Extract period dates
            for v in row_vals:
                dates = re.findall(r'\d{2}/\d{2}/\d{2,4}', v)
                if len(dates) >= 2:
                    result.period_start = _parse_statement_date(dates[0])
                    result.period_end = _parse_statement_date(dates[1])

        # Find header
        if 'NARRATION' in row_upper and 'DATE' in row_upper:
            header_row = i
            for j, cell in enumerate(row_vals):
                cu = cell.upper()
                if cu == 'DATE':
                    col_map['date'] = j
                elif 'NARRATION' in cu:
                    col_map['narration'] = j
                elif 'CHQ' in cu or 'REF' in cu:
                    col_map['ref'] = j
                elif 'VALUE' in cu:
                    col_map['value_date'] = j
                elif 'WITHDRAWAL' in cu:
                    col_map['withdrawal'] = j
                elif 'DEPOSIT' in cu:
                    col_map['deposit'] = j
                elif 'CLOSING' in cu or 'BALANCE' in cu:
                    col_map['balance'] = j
            break

    if header_row is None:
        result.errors.append("Could not find header row in XLS")
        return result
    if not bank_fingerprint:
        result.errors.append("HDFC bank fingerprint was not found in XLS metadata")
        return result

    required_columns = {'date', 'narration', 'withdrawal', 'deposit', 'balance'}
    missing_columns = sorted(required_columns - set(col_map))
    if missing_columns:
        result.errors.append(
            "Missing required XLS columns: " + ", ".join(missing_columns),
        )
        return result
    result.recognized = True

    # Parse data rows (skip header + separator row)
    data_start = header_row + 1
    # Skip separator rows (********)
    while data_start < sheet.nrows:
        first_cell = str(sheet.cell_value(data_start, 0)).strip()
        if first_cell.startswith('*') or not first_cell:
            data_start += 1
        else:
            break

    for i in range(data_start, sheet.nrows):
        date_cell = str(sheet.cell_value(i, col_map['date'])).strip()

        # Stop at separator or empty date
        if not date_cell or date_cell.startswith('*'):
            break

        date_val = _parse_statement_date(date_cell)
        if not date_val:
            continue

        narration = str(sheet.cell_value(i, col_map['narration'])).strip()
        if not narration:
            continue

        ref_index = col_map.get('ref')
        ref = (
            str(sheet.cell_value(i, ref_index)).strip()
            if ref_index is not None and ref_index < sheet.ncols
            else ''
        )

        # Amounts: xlrd returns float for numbers, empty string for blank
        wd_raw = sheet.cell_value(i, col_map['withdrawal'])
        dp_raw = sheet.cell_value(i, col_map['deposit'])
        bal_raw = sheet.cell_value(i, col_map['balance']) if col_map['balance'] < sheet.ncols else ''

        withdrawal = float(wd_raw) if isinstance(wd_raw, (int, float)) and wd_raw else None
        deposit = float(dp_raw) if isinstance(dp_raw, (int, float)) and dp_raw else None
        balance = float(bal_raw) if isinstance(bal_raw, (int, float)) and bal_raw else None

        # Also try parsing string amounts (some XLS files store as text)
        if withdrawal is None and isinstance(wd_raw, str) and wd_raw.strip():
            withdrawal = _parse_amount(wd_raw)
        if deposit is None and isinstance(dp_raw, str) and dp_raw.strip():
            deposit = _parse_amount(dp_raw)

        txn_dict = {
            'date': date_val,
            'narration': narration,
            'ref': ref,
            'value_date': '',
            'withdrawal': withdrawal,
            'deposit': deposit,
            'balance': balance,
        }
        _append_strict_savings_txn(
            txn_dict,
            result.transactions,
            result.errors,
            row_label=f"XLS row {i + 1}",
        )

    if not result.transactions and not result.errors:
        result.errors.append("No transactions found in XLS")

    _validate_savings_controls(result)

    logger.info(f"XLS parser: found {len(result.transactions)} transactions")
    return result


def parse_statement_pdf(pdf_bytes: bytes, password: Optional[str] = None) -> StatementParseResult:
    result = StatementParseResult()

    try:
        pdf_file = io.BytesIO(pdf_bytes)
        pdf = pdfplumber.open(pdf_file, password=password)
    except Exception as e:
        result.errors.append(f"Failed to open PDF: {str(e)}")
        return result

    try:
        full_text = ''
        for page in pdf.pages:
            text = page.extract_text() or ''
            full_text += text + '\n'

        normalized_text = full_text.lower()
        if 'hdfc' not in normalized_text:
            result.errors.append(
                "Unsupported or unrecognized PDF statement; HDFC fingerprint not found",
            )
        elif 'credit card' in normalized_text or 'card number' in normalized_text:
            result.statement_type = 'hdfc_credit_card'
            result.parser_profile = 'hdfc_credit'
            result.recognized = True
            _parse_hdfc_cc_statement(pdf, result)
        elif 'savings account' in normalized_text or 'statement of account' in normalized_text:
            result.statement_type = 'hdfc_savings'
            result.parser_profile = 'hdfc_savings'
            result.recognized = True
            _parse_hdfc_savings_statement(pdf, result)
        else:
            result.errors.append(
                "Unsupported HDFC PDF layout; statement profile could not be established",
            )

    except Exception as e:
        result.errors.append(f"Parse error: {str(e)}")
    finally:
        pdf.close()

    return result


# --- Narration Parsing ---

def parse_upi_narration(narration: str) -> dict:
    """Parse UPI narration into structured components.

    UPI narrations follow the pattern: UPI-NAME-VPA@BANK-IFSC-REF-DESCRIPTION
    The VPA (contains @) is the reliable anchor point.
    """
    text = narration[4:]  # Strip 'UPI-' prefix

    # Find the VPA (contains @ symbol) — this is the anchor
    vpa_match = re.search(r'([A-Za-z0-9._]+@[A-Za-z0-9]+)', text)
    if not vpa_match:
        return {'merchant_name': text.split('-')[0].strip(), 'vpa': None, 'ref': None, 'instrument': 'upi'}

    vpa = vpa_match.group(1)
    vpa_start = vpa_match.start()

    # Everything before the VPA (minus trailing hyphen) is the name
    name_part = text[:vpa_start].rstrip('-').strip()

    # Everything after the VPA contains IFSC-REF-DESCRIPTION
    after_vpa = text[vpa_match.end():]

    # Extract reference number (long digit sequence)
    ref_match = re.search(r'(\d{10,})', after_vpa)
    ref = ref_match.group(1) if ref_match else None

    return {
        'merchant_name': name_part,
        'vpa': vpa,
        'ref': ref,
        'instrument': 'upi',
    }


def parse_statement_narration(narration: str) -> dict:
    """Parse HDFC savings statement narration into structured data.

    Returns dict with: merchant_name, instrument, is_transfer, is_income,
                       vpa, ref, suggested_category, suggested_subcategory
    """
    narration = narration.strip()
    upper = narration.upper()
    result = {
        'merchant_raw': narration,
        'merchant_name': None,
        'instrument': 'savings_account',
        'is_transfer': False,
        'is_income': False,
        'semantic_type': 'unknown',
        'vpa': None,
        'ref': None,
        'suggested_category': None,
        'suggested_subcategory': None,
    }

    # === UPI ===
    if upper.startswith('UPI-'):
        parsed = parse_upi_narration(narration)
        result.update(parsed)
        result['instrument'] = 'upi'
        return result

    # === NEFT credit ===
    neft_match = re.match(r'NEFT\s?CR-(.+)', narration, re.IGNORECASE)
    if neft_match:
        # Extract meaningful part after NEFT CR-
        remainder = neft_match.group(1).strip()
        parts = remainder.split('-', 1)
        result['merchant_name'] = parts[1].strip() if len(parts) > 1 else parts[0].strip()
        result['instrument'] = 'neft'
        if contains_semantic_term(
            upper,
            (
                'SALARY', 'WAGES', 'PENSION', 'INTEREST', 'DIVIDEND',
                'BONUS', 'INCENTIVE',
            ),
        ):
            result['is_income'] = True
            result['semantic_type'] = 'income'
            result['suggested_category'] = 'INCOME'
            result['suggested_subcategory'] = (
                'Interest'
                if contains_semantic_term(upper, ('INTEREST', 'DIVIDEND'))
                else 'Salary'
            )
        return result

    # === Bill Pay (Transfer to CC) ===
    # PDF text may have no spaces: "IBBILLPAYDR" or "IB BILLPAY DR"
    if 'IBBILLPAY' in upper or 'IB BILLPAY' in upper:
        result['merchant_name'] = 'HDFC Credit Card Payment'
        result['is_transfer'] = True
        result['semantic_type'] = 'internal_transfer'
        result['suggested_category'] = 'TRANSFERS'
        result['suggested_subcategory'] = 'Credit Card Payment'
        return result

    # === Fixed Deposit (Transfer) ===
    if upper.startswith('FD THROUGH') or upper.startswith('FDTHROUGH'):
        result['merchant_name'] = 'Fixed Deposit'
        result['is_transfer'] = True
        result['semantic_type'] = 'internal_transfer'
        result['suggested_category'] = 'TRANSFERS'
        result['suggested_subcategory'] = 'Investment Transfer'
        return result

    # === Recurring Deposit (Transfer) ===
    # PDF may have "RDTHROUGHMOBILE" or "RD THROUGH MOBILE"
    if re.search(r'RD\s*THROUGH|RD\s*INSTALLMENT', upper):
        result['merchant_name'] = 'Recurring Deposit'
        result['is_transfer'] = True
        result['semantic_type'] = 'internal_transfer'
        result['suggested_category'] = 'TRANSFERS'
        result['suggested_subcategory'] = 'Investment Transfer'
        return result

    # === Debit Card International (Subscriptions) ===
    dc_match = re.match(r'ME DC SI\s+\d+X+\d+\s+(.*)', narration, re.IGNORECASE)
    if dc_match:
        result['merchant_name'] = dc_match.group(1).strip()
        result['instrument'] = 'debit_card'
        return result

    # === POS Transaction ===
    pos_match = re.match(r'POS\s+[\dX*]+\s+(.*)', narration, re.IGNORECASE)
    if pos_match:
        result['merchant_name'] = pos_match.group(1).strip()
        result['instrument'] = 'debit_card'
        return result

    # === International Markup/Surcharge ===
    if 'DC INTL POS TXN MARKUP' in upper or 'DCINTLPOSTXNMARKUP' in upper:
        result['merchant_name'] = 'Intl Transaction Fee'
        result['instrument'] = 'debit_card'
        result['suggested_category'] = 'FINANCIAL OBLIGATIONS'
        result['suggested_subcategory'] = 'Bank Charges'
        return result

    # === Reversal/Refund ===
    if upper.startswith('CRV'):
        crv_match = re.match(r'CRV POS[- ]+\d+[\*X]+\d+[- ]*(.*)', narration, re.IGNORECASE)
        merchant = crv_match.group(1).strip() if crv_match else 'Reversal'
        result['merchant_name'] = f"Refund - {merchant}" if merchant else 'Refund'
        result['semantic_type'] = 'refund'
        result['suggested_category'] = 'INCOME'
        result['suggested_subcategory'] = 'Refund'
        return result

    # === Excess Payment (CC refund) ===
    if 'EXC PYMT' in upper or 'EXCPYMT' in upper:
        result['merchant_name'] = 'CC Excess Payment Refund'
        result['is_transfer'] = True
        result['semantic_type'] = 'internal_transfer'
        result['suggested_category'] = 'TRANSFERS'
        result['suggested_subcategory'] = 'Credit Card Payment'
        return result

    # === ACH Credit ===
    if upper.startswith('ACH C-') or upper.startswith('ACHC-'):
        ach_match = re.match(r'ACH C-\s*(.*?)-\d+', narration, re.IGNORECASE)
        result['merchant_name'] = ach_match.group(1).strip() if ach_match else 'ACH Credit'
        if contains_semantic_term(
            upper,
            ('SALARY', 'WAGES', 'PENSION', 'INTEREST', 'DIVIDEND'),
        ):
            result['is_income'] = True
            result['semantic_type'] = 'income'
            result['suggested_category'] = 'INCOME'
            result['suggested_subcategory'] = (
                'Interest'
                if contains_semantic_term(upper, ('INTEREST', 'DIVIDEND'))
                else 'Salary'
            )
        return result

    if contains_semantic_term(upper, ('CASHBACK', 'CASH BACK')):
        result['merchant_name'] = narration[:50]
        result['semantic_type'] = 'cashback'
        result['suggested_category'] = 'INCOME'
        result['suggested_subcategory'] = 'Cashback'
        return result

    if contains_semantic_term(upper, ('REIMBURSEMENT', 'REIMBURSED')):
        result['merchant_name'] = narration[:50]
        result['semantic_type'] = 'reimbursement'
        return result

    # === Fallback ===
    result['merchant_name'] = narration[:50]
    return result


# --- HDFC Savings Account Statement Parser ---

# Text fallback patterns
SAVINGS_LINE_PATTERN = re.compile(
    r'(\d{2}/\d{2}/\d{2,4})\s+'
    r'(.+?)\s+'
    r'([\d,]+\.\d{2})\s*$'
)

SAVINGS_DEBIT_CREDIT_PATTERN = re.compile(
    r'(\d{2}/\d{2}/\d{2,4})\s+'
    r'(.+?)\s+'
    r'([\d,]+\.\d{2})\s+'
    r'([\d,]+\.\d{2})\s*$'
)


def _parse_hdfc_savings_statement(pdf: pdfplumber.PDF, result: StatementParseResult) -> None:
    """Parse only explicit, column-preserving HDFC savings PDF tables."""
    raw_txns: list[StatementTransaction] = []
    saved_col_map: Optional[dict] = None
    saw_supported_table = False

    for page_number, page in enumerate(pdf.pages, start=1):
        tables = page.extract_tables()
        if tables:
            for table in tables:
                col_map_used = _process_savings_table_v2(
                    table,
                    raw_txns,
                    saved_col_map,
                    errors=result.errors,
                    table_label=f"PDF page {page_number}",
                )
                if col_map_used and saved_col_map is None:
                    saved_col_map = col_map_used
                saw_supported_table = saw_supported_table or bool(col_map_used)
        else:
            result.errors.append(
                f"PDF page {page_number}: text-only statement extraction cannot preserve "
                "withdrawal and deposit columns",
            )

    if not saw_supported_table and not result.errors:
        result.errors.append("No supported HDFC savings transaction table was found")
    if result.errors:
        result.transactions.clear()
        result.reconciliation_status = "failed"
        return

    # Deduplicate (same date + amount + ref + description prefix = duplicate from page overlap)
    seen: set[tuple] = set()
    for txn in raw_txns:
        key = (txn.date, txn.amount, txn.ref_number or '', txn.description[:30])
        if key not in seen:
            seen.add(key)
            result.transactions.append(txn)

    if not result.transactions:
        result.errors.append("No explicit savings transactions were found")
    _validate_savings_controls(result)


def _safe_cell(row: list, idx: int) -> str:
    """Bounds-safe cell accessor for table rows."""
    if idx is None or idx >= len(row):
        return ''
    return str(row[idx] or '').strip()


def _process_savings_table_v2(
    table: list,
    txns_out: list[StatementTransaction],
    saved_col_map: Optional[dict] = None,
    *,
    errors: Optional[list[str]] = None,
    table_label: str = "PDF table",
) -> Optional[dict]:
    """Process rows only when their explicit statement columns remain aligned.

    Packed PDF rows are rejected. They cannot safely align multiline narration
    with sparse withdrawal/deposit cells, and running-balance deltas must never
    be used to guess transaction facts.
    """
    parse_errors = errors if errors is not None else []
    if not table or len(table) < 1:
        return None

    # Find header row and map column indices
    header_idx = None
    col_map: dict[str, int] = {}
    for i, row in enumerate(table):
        if not row:
            continue
        row_text = ' '.join(str(c or '') for c in row).upper()
        if 'NARRATION' in row_text and 'DATE' in row_text:
            header_idx = i
            for j, cell in enumerate(row):
                cell_str = str(cell or '').strip().upper()
                if 'DATE' in cell_str and 'VALUE' not in cell_str:
                    col_map['date'] = j
                elif 'NARRATION' in cell_str:
                    col_map['narration'] = j
                elif 'CHQ' in cell_str or 'REF' in cell_str:
                    col_map['ref'] = j
                elif 'VALUE' in cell_str:
                    col_map['value_date'] = j
                elif 'WITHDRAWAL' in cell_str:
                    col_map['withdrawal'] = j
                elif 'DEPOSIT' in cell_str:
                    col_map['deposit'] = j
                elif 'CLOSING' in cell_str or 'BALANCE' in cell_str:
                    col_map['balance'] = j
            break

    if header_idx is None:
        if saved_col_map:
            col_map = dict(saved_col_map)
            header_idx = -1
        else:
            return None

    required_columns = {'date', 'narration', 'withdrawal', 'deposit', 'balance'}
    missing_columns = sorted(required_columns - set(col_map))
    if missing_columns:
        parse_errors.append(
            f"{table_label}: missing required statement columns: "
            + ", ".join(missing_columns),
        )
        return None

    data_rows = table[header_idx + 1:]

    for row_number, row in enumerate(data_rows, start=header_idx + 2):
        if not row or all(cell is None or str(cell).strip() == '' for cell in row):
            continue

        cell_values = {
            name: _safe_cell(row, index)
            for name, index in col_map.items()
        }
        if any("\n" in value or "\r" in value for value in cell_values.values()):
            parse_errors.append(
                f"{table_label} row {row_number}: packed multi-line PDF rows are "
                "ambiguous; use the bank XLS/XLSX export",
            )
            continue

        transaction_date = _parse_statement_date(cell_values.get('date', ''))
        if transaction_date is None:
            if any(value.strip() for value in cell_values.values()):
                parse_errors.append(
                    f"{table_label} row {row_number}: non-empty row has no valid transaction date",
                )
            continue

        _append_strict_savings_txn(
            {
                'date': transaction_date,
                'narration': cell_values.get('narration', ''),
                'ref': cell_values.get('ref', ''),
                'value_date': cell_values.get('value_date', ''),
                'withdrawal': _parse_amount(cell_values.get('withdrawal', '')),
                'deposit': _parse_amount(cell_values.get('deposit', '')),
                'balance': _parse_amount(cell_values.get('balance', '')),
            },
            txns_out,
            parse_errors,
            row_label=f"{table_label} row {row_number}",
        )

    return col_map


def _finalize_savings_txn(raw: dict, txns_out: list) -> None:
    """Determine debit/credit, parse narration, build StatementTransaction."""
    withdrawal = raw.get('withdrawal')
    deposit = raw.get('deposit')

    if withdrawal is not None and withdrawal > 0:
        amount = withdrawal
        txn_type = 'debit'
    elif deposit is not None and deposit > 0:
        amount = deposit
        txn_type = 'credit'
    else:
        return  # No amount — skip header remnant or empty row

    narration = raw['narration']

    # Parse narration for structured metadata
    parsed = parse_statement_narration(narration)

    semantic_type = parsed.get('semantic_type', 'unknown')
    if txn_type == 'debit' and semantic_type == 'unknown':
        semantic_type = 'expense'
    is_income = semantic_type == 'income'

    txn = StatementTransaction(
        date=raw['date'],
        description=narration,
        amount=amount,
        txn_type=txn_type,
        ref_number=raw.get('ref') or parsed.get('ref'),
        closing_balance=raw.get('balance'),
        instrument=parsed.get('instrument', 'savings_account'),
        is_transfer=parsed.get('is_transfer', False),
        is_income=is_income,
        semantic_type=semantic_type,
        vpa_handle=parsed.get('vpa'),
        upi_ref_number=parsed.get('ref'),
        suggested_category=parsed.get('suggested_category'),
        suggested_subcategory=parsed.get('suggested_subcategory'),
        merchant_name=parsed.get('merchant_name'),
    )
    txns_out.append(txn)


def _process_savings_text_v2(text: str, txns_out: list) -> None:
    """Text fallback parser for savings statements (when no tables extracted)."""
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try pattern with two amounts (debit + balance, or debit + credit)
        m = SAVINGS_DEBIT_CREDIT_PATTERN.match(line)
        if m:
            date_val = _parse_statement_date(m.group(1))
            if not date_val:
                continue

            description = m.group(2).strip()
            amt1 = _parse_amount(m.group(3))
            amt2 = _parse_amount(m.group(4))

            parsed = parse_statement_narration(description)

            if amt1 and amt1 > 0:
                is_income = parsed.get('is_income', False)
                txns_out.append(StatementTransaction(
                    date=date_val,
                    description=description,
                    amount=amt1,
                    txn_type='debit',
                    instrument=parsed.get('instrument', 'savings_account'),
                    is_transfer=parsed.get('is_transfer', False),
                    is_income=is_income,
                    semantic_type=(
                        parsed.get('semantic_type', 'unknown')
                        if parsed.get('semantic_type', 'unknown') != 'unknown'
                        else 'expense'
                    ),
                    vpa_handle=parsed.get('vpa'),
                    upi_ref_number=parsed.get('ref'),
                    suggested_category=parsed.get('suggested_category'),
                    suggested_subcategory=parsed.get('suggested_subcategory'),
                    merchant_name=parsed.get('merchant_name'),
                ))
            continue

        # Try single amount pattern
        m = SAVINGS_LINE_PATTERN.match(line)
        if m:
            date_val = _parse_statement_date(m.group(1))
            if not date_val:
                continue

            description = m.group(2).strip()
            amount = _parse_amount(m.group(3))
            if amount and amount > 0:
                parsed = parse_statement_narration(description)
                txns_out.append(StatementTransaction(
                    date=date_val,
                    description=description,
                    amount=amount,
                    txn_type='debit',
                    instrument=parsed.get('instrument', 'savings_account'),
                    is_transfer=parsed.get('is_transfer', False),
                    is_income=parsed.get('is_income', False),
                    semantic_type=(
                        parsed.get('semantic_type', 'unknown')
                        if parsed.get('semantic_type', 'unknown') != 'unknown'
                        else 'expense'
                    ),
                    vpa_handle=parsed.get('vpa'),
                    upi_ref_number=parsed.get('ref'),
                    suggested_category=parsed.get('suggested_category'),
                    suggested_subcategory=parsed.get('suggested_subcategory'),
                    merchant_name=parsed.get('merchant_name'),
                ))


# --- HDFC Credit Card Statement Parser ---

CC_LINE_PATTERN = re.compile(
    r'(\d{2}/\d{2}/\d{2,4})\s+'
    r'(.+?)\s+'
    r'([\d,]+\.\d{2})\s*(Cr)?\s*$'
)


def _parse_hdfc_cc_statement(pdf: pdfplumber.PDF, result: StatementParseResult) -> None:
    raw_transactions: list[StatementTransaction] = []
    saved_col_map: Optional[dict[str, int]] = None
    saw_supported_table = False
    original_transactions = result.transactions
    result.transactions = raw_transactions

    for page_number, page in enumerate(pdf.pages, start=1):
        tables = page.extract_tables()
        if tables:
            for table in tables:
                col_map = _process_cc_table(
                    table,
                    result,
                    saved_col_map=saved_col_map,
                    table_label=f"PDF page {page_number}",
                )
                if col_map and saved_col_map is None:
                    saved_col_map = col_map
                saw_supported_table = saw_supported_table or bool(col_map)
        else:
            result.errors.append(
                f"PDF page {page_number}: text-only credit-card extraction cannot "
                "preserve the explicit transaction amount column",
            )

    if not saw_supported_table and not result.errors:
        result.errors.append("No supported HDFC credit-card transaction table was found")
    if result.errors:
        result.transactions = original_transactions
        result.transactions.clear()
        result.reconciliation_status = "failed"
        return

    seen: set[tuple[date, float, str, str]] = set()
    deduplicated: list[StatementTransaction] = []
    for transaction in raw_transactions:
        key = (
            transaction.date,
            transaction.amount,
            transaction.txn_type,
            transaction.description,
        )
        if key not in seen:
            seen.add(key)
            deduplicated.append(transaction)

    result.transactions = deduplicated
    if not result.transactions:
        result.errors.append("No explicit HDFC credit-card transactions were found")
        result.reconciliation_status = "failed"
        return

    result.period_start = min(txn.date for txn in result.transactions)
    result.period_end = max(txn.date for txn in result.transactions)
    result.total_debits = round(
        sum(txn.amount for txn in result.transactions if txn.txn_type == 'debit'),
        2,
    )
    result.total_credits = round(
        sum(txn.amount for txn in result.transactions if txn.txn_type == 'credit'),
        2,
    )
    result.reconciliation_status = "passed"
    result.reconciliation_method = "explicit_credit_card_amount_columns"


def _process_cc_table(
    table: list,
    result: StatementParseResult,
    *,
    saved_col_map: Optional[dict[str, int]] = None,
    table_label: str = "PDF table",
) -> Optional[dict[str, int]]:
    if not table:
        return None

    header_index: Optional[int] = None
    columns: dict[str, int] = {}
    for index, row in enumerate(table):
        if not row:
            continue
        values = [str(cell or '').strip() for cell in row]
        upper = ' '.join(values).upper()
        if 'DATE' not in upper or 'AMOUNT' not in upper:
            continue
        if 'TRANSACTION' not in upper and 'DESCRIPTION' not in upper:
            continue
        header_index = index
        for column, value in enumerate(values):
            cell = value.upper()
            if 'DATE' in cell:
                columns['date'] = column
            elif 'TRANSACTION' in cell or 'DESCRIPTION' in cell:
                columns['description'] = column
            elif 'AMOUNT' in cell:
                columns['amount'] = column
        break

    if header_index is None:
        if not saved_col_map:
            return None
        columns = dict(saved_col_map)
        header_index = -1

    missing = {'date', 'description', 'amount'} - set(columns)
    if missing:
        result.errors.append(
            f"{table_label}: missing required credit-card columns: "
            + ", ".join(sorted(missing)),
        )
        return None

    for row_number, row in enumerate(table[header_index + 1:], start=header_index + 2):
        if not row or all(cell is None or str(cell).strip() == '' for cell in row):
            continue

        date_text = _safe_cell(row, columns['date'])
        description = _safe_cell(row, columns['description'])
        amount_text = _safe_cell(row, columns['amount'])
        if any('\n' in value or '\r' in value for value in (date_text, description, amount_text)):
            result.errors.append(
                f"{table_label} row {row_number}: packed multi-line credit-card row is ambiguous",
            )
            continue

        date_val = _parse_statement_date(date_text)
        if not date_val:
            if date_text or description or amount_text:
                result.errors.append(
                    f"{table_label} row {row_number}: non-empty row has no valid transaction date",
                )
            continue
        if not description:
            result.errors.append(f"{table_label} row {row_number}: missing description")
            continue
        is_credit = bool(re.search(r'\bCR\b', amount_text, re.IGNORECASE))
        amount = _parse_amount(re.sub(r'\bCR\b', '', amount_text, flags=re.IGNORECASE))
        if amount is None or not math.isfinite(amount) or amount <= 0:
            result.errors.append(f"{table_label} row {row_number}: invalid amount")
            continue
        result.transactions.append(StatementTransaction(
            date=date_val,
            description=description,
            amount=amount,
            txn_type='credit' if is_credit else 'debit',
        ))

    return columns


def _process_cc_text(text: str, result: StatementParseResult) -> None:
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        m = CC_LINE_PATTERN.match(line)
        if not m:
            continue

        date_val = _parse_statement_date(m.group(1))
        if not date_val:
            continue

        description = m.group(2).strip()
        amount = _parse_amount(m.group(3))
        is_credit = m.group(4) is not None

        if amount and amount > 0:
            result.transactions.append(StatementTransaction(
                date=date_val,
                description=description,
                amount=amount,
                txn_type='credit' if is_credit else 'debit',
            ))


# --- Utility ---

def _parse_statement_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ('%d/%m/%Y', '%d/%m/%y', '%d-%m-%Y', '%d-%m-%y'):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(s: str) -> Optional[float]:
    if not s:
        return None
    s = s.replace(',', '').replace(' ', '').strip()
    # Remove any trailing non-numeric chars
    s = re.sub(r'[^0-9.]', '', s)
    try:
        return float(s)
    except ValueError:
        return None


class StatementParser:
    """Parser for bank and credit card statements (GLM compatibility class)"""

    @staticmethod
    def parse(pdf_bytes: bytes, password: Optional[str] = None) -> ParsedStatement:
        """Parse a PDF statement and return a ParsedStatement"""
        result = parse_statement_pdf(pdf_bytes, password)
        return ParsedStatement.from_statement_result(result)
