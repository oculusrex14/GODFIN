from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

import pdfplumber
import xlrd

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
        )
        transactions = [ParsedTransaction.from_statement_transaction(t) for t in result.transactions]
        return cls(metadata=metadata, transactions=transactions)


@dataclass
class StatementParseResult:
    transactions: list[StatementTransaction] = field(default_factory=list)
    statement_type: str = ''  # 'hdfc_savings' or 'hdfc_credit_card'
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    errors: list[str] = field(default_factory=list)


def parse_statement_xls(file_bytes: bytes) -> StatementParseResult:
    """Parse HDFC savings account XLS statement.

    XLS format has clean one-row-per-transaction layout:
    - Metadata rows at top (account number, period, etc.)
    - Header row: Date | Narration | Chq./Ref.No. | Value Dt | Withdrawal Amt. | Deposit Amt. | Closing Balance
    - Data rows until separator (********) or empty date
    """
    result = StatementParseResult()
    result.statement_type = 'hdfc_savings'

    try:
        wb = xlrd.open_workbook(file_contents=file_bytes)
        sheet = wb.sheet_by_index(0)
    except Exception as e:
        result.errors.append(f"Failed to open XLS: {e}")
        return result

    # Find header row and extract metadata
    header_row = None
    col_map: dict[str, int] = {}

    for i in range(min(sheet.nrows, 30)):
        row_vals = [str(sheet.cell_value(i, j)).strip() for j in range(sheet.ncols)]
        row_upper = ' '.join(row_vals).upper()

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

    # Default column positions
    col_map.setdefault('date', 0)
    col_map.setdefault('narration', 1)
    col_map.setdefault('ref', 2)
    col_map.setdefault('value_date', 3)
    col_map.setdefault('withdrawal', 4)
    col_map.setdefault('deposit', 5)
    col_map.setdefault('balance', 6)

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

        ref = str(sheet.cell_value(i, col_map['ref'])).strip() if col_map['ref'] < sheet.ncols else ''

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
        _finalize_savings_txn(txn_dict, result.transactions)

    if not result.transactions:
        result.errors.append("No transactions found in XLS")

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

        if 'credit card' in full_text.lower() or 'card number' in full_text.lower():
            result.statement_type = 'hdfc_credit_card'
            _parse_hdfc_cc_statement(pdf, result)
        elif 'savings account' in full_text.lower() or 'statement of account' in full_text.lower():
            result.statement_type = 'hdfc_savings'
            _parse_hdfc_savings_statement(pdf, result)
        else:
            # Try savings parser as fallback
            result.statement_type = 'hdfc_savings'
            _parse_hdfc_savings_statement(pdf, result)
            if not result.transactions:
                result.statement_type = 'hdfc_credit_card'
                _parse_hdfc_cc_statement(pdf, result)

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

    # === NEFT Credit (Income) ===
    neft_match = re.match(r'NEFT\s?CR-(.+)', narration, re.IGNORECASE)
    if neft_match:
        # Extract meaningful part after NEFT CR-
        remainder = neft_match.group(1).strip()
        parts = remainder.split('-', 1)
        result['merchant_name'] = parts[1].strip() if len(parts) > 1 else parts[0].strip()
        result['is_income'] = True
        result['instrument'] = 'neft'
        result['suggested_category'] = 'INCOME'
        result['suggested_subcategory'] = 'Salary'
        return result

    # === Bill Pay (Transfer to CC) ===
    # PDF text may have no spaces: "IBBILLPAYDR" or "IB BILLPAY DR"
    if 'IBBILLPAY' in upper or 'IB BILLPAY' in upper:
        result['merchant_name'] = 'HDFC Credit Card Payment'
        result['is_transfer'] = True
        result['suggested_category'] = 'TRANSFERS'
        result['suggested_subcategory'] = 'Credit Card Payment'
        return result

    # === Fixed Deposit (Transfer) ===
    if upper.startswith('FD THROUGH') or upper.startswith('FDTHROUGH'):
        result['merchant_name'] = 'Fixed Deposit'
        result['is_transfer'] = True
        result['suggested_category'] = 'TRANSFERS'
        result['suggested_subcategory'] = 'Investment Transfer'
        return result

    # === Recurring Deposit (Transfer) ===
    # PDF may have "RDTHROUGHMOBILE" or "RD THROUGH MOBILE"
    if re.search(r'RD\s*THROUGH|RD\s*INSTALLMENT', upper):
        result['merchant_name'] = 'Recurring Deposit'
        result['is_transfer'] = True
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
        result['is_income'] = True
        result['suggested_category'] = 'INCOME'
        result['suggested_subcategory'] = 'Refund'
        return result

    # === Excess Payment (CC refund) ===
    if 'EXC PYMT' in upper or 'EXCPYMT' in upper:
        result['merchant_name'] = 'CC Excess Payment Refund'
        result['is_transfer'] = True
        result['suggested_category'] = 'TRANSFERS'
        result['suggested_subcategory'] = 'Credit Card Payment'
        return result

    # === ACH Credit ===
    if upper.startswith('ACH C-') or upper.startswith('ACHC-'):
        ach_match = re.match(r'ACH C-\s*(.*?)-\d+', narration, re.IGNORECASE)
        result['merchant_name'] = ach_match.group(1).strip() if ach_match else 'ACH Credit'
        result['is_income'] = True
        result['suggested_category'] = 'INCOME'
        result['suggested_subcategory'] = 'Interest'
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
    """Parse HDFC savings statement with multi-line narration joining."""
    raw_txns: list[StatementTransaction] = []
    # Column map discovered from first header — reused for headerless pages
    saved_col_map: Optional[dict] = None

    for page in pdf.pages:
        tables = page.extract_tables()
        if tables:
            for table in tables:
                col_map_used = _process_savings_table_v2(table, raw_txns, saved_col_map)
                if col_map_used and saved_col_map is None:
                    saved_col_map = col_map_used
        else:
            text = page.extract_text() or ''
            _process_savings_text_v2(text, raw_txns)

    # Deduplicate (same date + amount + ref + description prefix = duplicate from page overlap)
    seen: set[tuple] = set()
    for txn in raw_txns:
        key = (txn.date, txn.amount, txn.ref_number or '', txn.description[:30])
        if key not in seen:
            seen.add(key)
            result.transactions.append(txn)


def _safe_cell(row: list, idx: int) -> str:
    """Bounds-safe cell accessor for table rows."""
    if idx is None or idx >= len(row):
        return ''
    return str(row[idx] or '').strip()


def _process_savings_table_v2(table: list, txns_out: list, saved_col_map: Optional[dict] = None) -> Optional[dict]:
    """Process savings statement table with header detection and continuation row joining.

    Returns the column map used, so it can be reused for headerless pages.
    """
    if not table or len(table) < 1:
        return None

    # Find header row and map column indices
    header_idx = None
    col_map: dict[str, int] = {}
    for i, row in enumerate(table):
        if not row:
            continue
        row_text = ' '.join(str(c or '') for c in row).upper()
        if 'NARRATION' in row_text:
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
            # No header on this page — use saved column map, treat all rows as data
            col_map = saved_col_map
            header_idx = -1  # So header_idx + 1 == 0, processing all rows
        else:
            return None  # No header found and no saved map

    # Default column positions if header parsing missed some
    col_map.setdefault('date', 0)
    col_map.setdefault('narration', 1)
    col_map.setdefault('ref', 2)
    col_map.setdefault('value_date', 3)
    col_map.setdefault('withdrawal', 4)
    col_map.setdefault('deposit', 5)
    col_map.setdefault('balance', 6)

    # pdfplumber often packs an entire page into a single table row with \n
    # inside each cell. The columns have DIFFERENT line counts because narrations
    # span multiple lines. We use the date column as anchor — each date line
    # starts a new transaction. Narration lines between dates are continuations.
    # Withdrawal/Deposit/Balance/Ref have one entry per transaction (aligned with dates).

    data_rows = table[header_idx + 1:]

    for row in data_rows:
        if not row or all(cell is None or str(cell).strip() == '' for cell in row):
            continue

        # Split each column by \n
        date_lines = str(row[col_map['date']] or '').split('\n')
        narration_lines = str(row[col_map['narration']] or '').split('\n')
        ref_lines = str(row[col_map['ref']] or '').split('\n')
        value_date_lines = str(row[col_map.get('value_date', 3)] or '').split('\n') if col_map.get('value_date') is not None and col_map['value_date'] < len(row) else []
        withdrawal_lines = str(row[col_map['withdrawal']] or '').split('\n') if col_map['withdrawal'] < len(row) else []
        deposit_lines = str(row[col_map['deposit']] or '').split('\n') if col_map['deposit'] < len(row) else []
        balance_lines = str(row[col_map['balance']] or '').split('\n') if col_map['balance'] < len(row) else []

        # Check if this is a multi-line packed row
        max_date_lines = len([d for d in date_lines if d.strip()])
        if max_date_lines <= 1 and len(narration_lines) <= 1:
            # Normal single-line row — process directly
            date_val = _parse_statement_date(date_lines[0].strip() if date_lines else '')
            if date_val:
                txn_dict = {
                    'date': date_val,
                    'narration': narration_lines[0].strip() if narration_lines else '',
                    'ref': ref_lines[0].strip() if ref_lines else '',
                    'value_date': value_date_lines[0].strip() if value_date_lines else '',
                    'withdrawal': _parse_amount(withdrawal_lines[0].strip() if withdrawal_lines else ''),
                    'deposit': _parse_amount(deposit_lines[0].strip() if deposit_lines else ''),
                    'balance': _parse_amount(balance_lines[0].strip() if balance_lines else ''),
                }
                _finalize_savings_txn(txn_dict, txns_out)
            continue

        # Multi-line packed row: date column is the anchor.
        # Build transaction groups by scanning narration lines and aligning
        # with date/ref/withdrawal/deposit/balance which have fewer lines.
        # Each date corresponds to one transaction; narration lines between
        # dates are continuation lines that should be joined.

        # Index counters for the amount-aligned columns
        txn_idx = 0  # Which transaction we're on (increments with each date)
        current_txn: Optional[dict] = None

        # Track which narration lines belong to which date
        date_positions = []  # narration line indices where new transactions start
        for i, dl in enumerate(date_lines):
            if _parse_statement_date(dl.strip()):
                date_positions.append(i)

        # For each date position, gather narration lines until the next date
        for pos_idx, date_line_idx in enumerate(date_positions):
            date_val = _parse_statement_date(date_lines[date_line_idx].strip())
            if not date_val:
                continue

            # Figure out where this transaction's narration ends
            if pos_idx + 1 < len(date_positions):
                next_date_line = date_positions[pos_idx + 1]
            else:
                next_date_line = len(narration_lines)

            # Collect narration lines for this transaction
            # The narration lines corresponding to this txn start at some offset.
            # Since dates and narrations are printed in order, we need to map
            # date_line_idx to the correct narration range.
            # However narration has MORE lines than dates, so we can't use
            # date_line_idx directly. Instead we track a running narration pointer.
            pass

        # Better approach: walk narration lines, use date column to detect boundaries.
        # The date column has entries only on transaction-start lines; continuation
        # lines in the date column are empty or repeat previous date.
        # But pdfplumber packs dates densely (no empty lines for continuations).
        # So we need a different strategy: scan narration for date-like patterns
        # that correspond to the dates we found.

        # Simplest reliable approach: since we know the exact dates and their order,
        # and we know ref/withdrawal/deposit/balance have one entry per transaction,
        # we just need to split narration lines into groups.
        # Use a heuristic: narration lines that look like they start a new txn
        # typically start with known prefixes (UPI-, NEFT, POS, etc.) or uppercase.
        # But more robust: count transactions from date column, then assign
        # narration lines by finding natural break points.

        # Most robust: split narration by matching against ref numbers.
        # Each transaction has a ref in ref_lines[txn_idx]. When we see narration
        # content that matches a known pattern start, that's a new transaction.

        # Actually the simplest approach that works:
        # dates has N entries (one per txn), narration has M > N entries.
        # We know the first narration line belongs to the first date.
        # Subsequent narration lines without a corresponding date are continuations.
        # We can detect boundaries by checking if a narration line starts a
        # recognized pattern AND we haven't assigned all dates yet.

        # Let's just use date line count to determine transaction boundaries
        # in the narration stream.
        n_txns = len(date_positions)
        narr_per_txn: list[list[str]] = [[] for _ in range(n_txns)]

        # Assign narration lines to transactions
        # Strategy: lines are in order. When we encounter a narration that
        # looks like the start of a new txn pattern, advance to next txn group.
        txn_group = 0
        for nl in narration_lines:
            nl_stripped = nl.strip()
            if not nl_stripped:
                continue
            # Check if this starts a new transaction (only advance if we haven't filled all groups)
            if txn_group < n_txns:
                narr_per_txn[txn_group].append(nl_stripped)
                # Heuristic to detect we've moved to the next transaction:
                # if the NEXT narration line would be the start of a new txn.
                # We defer this check to after we've seen the line.
            else:
                # Extra lines beyond expected — append to last
                narr_per_txn[-1].append(nl_stripped)

        # Re-do: the above doesn't actually split correctly.
        # Better: use the fact that ref_lines has exactly one per txn,
        # and check if a ref appears in the narration stream as a marker.
        # Or even simpler: just use the known date values to find splits.

        # Let me use a completely different, cleaner approach.
        # Walk all narration lines. Maintain a pointer into date_positions.
        # A narration line "belongs" to the current transaction.
        # We advance to the next transaction when we've seen enough narration
        # lines AND the next narration line looks like a transaction start.

        # The KEY insight from the PDF: narration lines that START a txn
        # begin with: POS, UPI-, NEFT, IB, FD, ME DC, ACH, CRV, RD, EXC, or
        # a known merchant pattern. Continuation lines typically start with
        # lowercase or are fragments (e.g. "0YBLUPI-", "KITCHEN-", "-YESB").

        _TXN_START_PATTERNS = re.compile(
            r'^(POS|UPI-|NEFT\s?CR|IB\s?BILLPAY|FD\s?THROUGH|ME\s?DC|ACH\s?C-|CRV|RD\s?THROUGH|RD\s?INSTALLMENT|EXC\s?PYMT)',
            re.IGNORECASE
        )

        narr_per_txn = [[] for _ in range(n_txns)]
        txn_group = 0
        for nl in narration_lines:
            nl_stripped = nl.strip()
            if not nl_stripped:
                continue
            # If we're past the first line of the current group and this looks
            # like a new transaction start, advance to next group
            if (txn_group < n_txns - 1 and
                    len(narr_per_txn[txn_group]) > 0 and
                    _TXN_START_PATTERNS.match(nl_stripped)):
                txn_group += 1
            narr_per_txn[txn_group].append(nl_stripped)

        # Parse all balance values (1:1 with dates, most reliable column)
        parsed_balances = []
        for bl in balance_lines:
            parsed_balances.append(_parse_amount(bl.strip()) if bl.strip() else None)

        # Withdrawal and deposit columns are SPARSE — they only have entries
        # for their respective transaction types, so direct indexing doesn't work.
        # Instead, derive amount and direction from balance changes.

        # Build withdrawal/deposit lookup by consuming them in order
        wd_queue = [_parse_amount(w.strip()) for w in withdrawal_lines if w.strip()]
        dp_queue = [_parse_amount(d.strip()) for d in deposit_lines if d.strip()]
        wd_ptr = 0
        dp_ptr = 0

        # Now build transactions
        for i in range(n_txns):
            date_val = _parse_statement_date(date_lines[date_positions[i]].strip())
            if not date_val:
                continue

            joined_narration = ' '.join(narr_per_txn[i]) if i < len(narr_per_txn) else ''

            ref_val = ref_lines[i].strip() if i < len(ref_lines) else ''
            vd_val = value_date_lines[i].strip() if i < len(value_date_lines) else ''
            bl_val = parsed_balances[i] if i < len(parsed_balances) else None
            prev_bal = parsed_balances[i - 1] if i > 0 and i - 1 < len(parsed_balances) else None

            # Determine withdrawal vs deposit from balance change
            wd_val = None
            dp_val = None
            if bl_val is not None and prev_bal is not None:
                diff = bl_val - prev_bal
                if diff < 0:
                    # Balance decreased = withdrawal
                    wd_val = abs(diff)
                elif diff > 0:
                    # Balance increased = deposit
                    dp_val = diff
            elif i == 0:
                # First transaction — try consuming from withdrawal queue first
                if wd_ptr < len(wd_queue) and wd_queue[wd_ptr] is not None:
                    wd_val = wd_queue[wd_ptr]
                    wd_ptr += 1
                elif dp_ptr < len(dp_queue) and dp_queue[dp_ptr] is not None:
                    dp_val = dp_queue[dp_ptr]
                    dp_ptr += 1

            txn_dict = {
                'date': date_val,
                'narration': joined_narration,
                'ref': ref_val,
                'value_date': vd_val,
                'withdrawal': wd_val,
                'deposit': dp_val,
                'balance': bl_val,
            }
            _finalize_savings_txn(txn_dict, txns_out)

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

    # For credits, also flag as income unless narration says it's a transfer
    is_income = parsed.get('is_income', False)
    if txn_type == 'credit' and not parsed.get('is_transfer', False):
        is_income = True

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
    for page in pdf.pages:
        tables = page.extract_tables()
        if tables:
            for table in tables:
                _process_cc_table(table, result)
        else:
            text = page.extract_text() or ''
            _process_cc_text(text, result)


def _process_cc_table(table: list, result: StatementParseResult) -> None:
    for row in table:
        if not row or len(row) < 3:
            continue

        date_val = _parse_statement_date(str(row[0] or '').strip())
        if not date_val:
            continue

        description = str(row[1] or '').strip()
        if not description:
            continue

        # Amount is usually last column
        for cell in reversed(row[2:]):
            cell_str = str(cell or '').strip()
            is_credit = 'cr' in cell_str.lower()
            amt = _parse_amount(cell_str.replace('Cr', '').replace('cr', '').strip())
            if amt is not None and amt > 0:
                result.transactions.append(StatementTransaction(
                    date=date_val,
                    description=description,
                    amount=amt,
                    txn_type='credit' if is_credit else 'debit',
                ))
                break


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
