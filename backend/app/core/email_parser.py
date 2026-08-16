from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from datetime import date, datetime
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# --- Sender Whitelist / Blacklist ---

SENDER_WHITELIST = {
    "alerts@hdfcbank.net": "hdfc_savings",
    "alerts@hdfcbank.bank.in": "hdfc_credit",
}

SENDER_BLACKLIST_SUBJECTS = [
    "Missed Call from your HDFC",
    "Relationship Manager",
    "Your OTP",
    "OTP For",
    "Welcome to HDFC",
    "eStatement",
    "SmartStatement",
    "e-mandate",
    "View: Account update",
]


# --- Regex Patterns ---

UPI_DEBIT_PATTERN = re.compile(
    r'Rs\.(?P<amount>[\d,]+\.\d{2})\s+has been debited from account\s+'
    r'(?P<account>\d{4})\s+to VPA\s+'
    r'(?P<vpa>\S+)\s+'
    r'(?P<merchant>.+?)\s+on\s+'
    r'(?P<date>\d{2}-\d{2}-\d{2,4})\.\s+'
    r'Your UPI transaction reference number is\s+'
    r'(?P<ref>\d+)',
    re.DOTALL | re.IGNORECASE
)

CC_DEBIT_PATTERN = re.compile(
    r'Rs\.?\s*(?P<amount>[\d,]+\.\d{2})\s+is debited from your HDFC Bank\s+'
    r'Credit Card ending\s+(?P<card_last4>\d{4})\s+'
    r'(?:towards|at)\s+'
    r'(?P<merchant>.+?)\s+on\s+'
    r'(?P<date>\d{1,2}\s+\w+,?\s+\d{4})'
    r'(?:\s+at\s+(?P<time>[\d:]+))?',
    re.DOTALL | re.IGNORECASE
)

P2P_VPA_PATTERN = re.compile(r'\d{10}@(ybl|paytm|okaxis|okicici|apl)')

# Debit Card Pattern - for "Thank you for using HDFC Bank Debit Card..."
DEBIT_CARD_PATTERN = re.compile(
    r'Thank you for using HDFC Bank Debit Card ending with\s+(?P<card_last4>\d{4})\s+'
    r'for Rs\.?\s*(?P<amount>[\d,]+\.?\d{0,2})\s+'
    r'at\s+(?P<merchant>.+?)\s+on\s+'
    r'(?P<date>\d{2}-\d{2}-\d{4})\s+'
    r'(?P<time>[\d:]+)',
    re.DOTALL | re.IGNORECASE
)

# RuPay Credit Card via UPI - credit card linked to UPI
RUPAY_CREDIT_UPI_PATTERN = re.compile(
    r'Rs\.?\s*(?P<amount>[\d,]+\.\d{2})\s+has been debited from your HDFC Bank\s+'
    r'(?:RuPay\s+)?Credit Card\s+(?:ending\s+)?(?:XX)?(?P<card_last4>\d{4})\s+'
    r'to\s+(?:VPA\s+)?(?P<vpa>\S+)\s+'
    r'(?P<merchant>.+?)\s+on\s+'
    r'(?P<date>\d{2}-\d{2}-\d{2,4})\.\s*'
    r'Your UPI transaction reference number is\s+(?P<ref>\d+)',
    re.DOTALL | re.IGNORECASE
)

# UPI Credit/Refund Pattern - for credits to account
UPI_CREDIT_PATTERN = re.compile(
    r'Rs\.?\s*(?P<amount>[\d,]+\.\d{2})\s+is successfully credited to your account\s+'
    r'(?:\*\*)?(?P<account>\d{4})\s+by VPA\s+'
    r'(?P<vpa>\S+)\s+'
    r'(?P<merchant>.+?)\s+on\s+'
    r'(?P<date>\d{2}-\d{2}-\d{2,4})',
    re.DOTALL | re.IGNORECASE
)


# --- Merchant Normalization ---

GATEWAY_PREFIXES = ['PYU*', 'PAY*', 'PP*', 'SQ*', 'GOOGLE *', 'AMZN*']

CORPORATE_SUFFIXES = [
    ' PVT LTD', ' PRIVATE LIMITED', ' PRIVATE LTD', ' LIMITED', ' LTD',
    ' INDIA', ' PRIVA', ' INC', ' LLC', ' P ',
]

CITY_SUFFIXES_PATTERN = re.compile(
    r'\s+(BANGALORE|BENGALURU|MUMBAI|DELHI|CHENNAI|INDIA|IN)\s*$'
)


def normalize_merchant(raw: str) -> str:
    text = raw.strip()
    text = unicodedata.normalize('NFKC', text)
    text = text.upper()

    for prefix in GATEWAY_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break

    # Strip city suffixes first (they appear at the end after corporate suffixes)
    text = CITY_SUFFIXES_PATTERN.sub('', text).strip()

    # Strip corporate suffixes iteratively (may need multiple passes)
    changed = True
    while changed:
        changed = False
        for suffix in CORPORATE_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)]
                changed = True
                break

    return text.strip()


# --- HTML Extraction ---

def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(separator=' ', strip=True)


# --- Date Parsing ---

def parse_upi_date(date_str: str) -> date:
    for fmt in ('%d-%m-%y', '%d-%m-%Y'):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse UPI date: {date_str}")


def parse_cc_date(date_str: str) -> date:
    for fmt in ('%d %B, %Y', '%d %B %Y', '%d %b, %Y', '%d %b %Y'):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse CC date: {date_str}")


def parse_debit_card_date(date_str: str) -> date:
    """Parse date in format DD-MM-YYYY"""
    try:
        return datetime.strptime(date_str.strip(), '%d-%m-%Y').date()
    except ValueError:
        raise ValueError(f"Cannot parse debit card date: {date_str}")


def parse_amount(amount_str: str) -> float:
    return float(amount_str.replace(',', ''))


# --- Checksum ---

def compute_source_checksum(raw_text: str, source: str) -> str:
    data = f"{raw_text}|{source}"
    return hashlib.sha256(data.encode()).hexdigest()


def compute_canonical_checksum(
    txn_date: date, amount: float, merchant_normalized: str,
    instrument: str, account_id: str,
) -> str:
    data = f"{txn_date.isoformat()}|{amount:.2f}|{merchant_normalized}|{instrument}|{account_id}"
    return hashlib.sha256(data.encode()).hexdigest()


# --- Filtering ---

def is_whitelisted_sender(sender: str) -> Optional[str]:
    sender_lower = sender.lower().strip()
    for email, account_type in SENDER_WHITELIST.items():
        if email in sender_lower:
            return account_type
    return None


def is_blacklisted_subject(subject: str) -> bool:
    subject_lower = subject.lower()
    return any(bl.lower() in subject_lower for bl in SENDER_BLACKLIST_SUBJECTS)


# --- Parsed Result ---

class ParsedTransaction:
    def __init__(
        self,
        amount: float,
        merchant_raw: str,
        merchant_normalized: str,
        txn_date: date,
        txn_type: str = 'debit',
        instrument: str = 'upi',
        account_type: str = 'hdfc_savings',
        vpa_handle: Optional[str] = None,
        upi_ref_number: Optional[str] = None,
        txn_time: Optional[str] = None,
        is_p2p: bool = False,
        account_last4: Optional[str] = None,
        raw_text: str = '',
    ):
        self.amount = amount
        self.merchant_raw = merchant_raw
        self.merchant_normalized = merchant_normalized
        self.txn_date = txn_date
        self.txn_type = txn_type
        self.instrument = instrument
        self.account_type = account_type
        self.vpa_handle = vpa_handle
        self.upi_ref_number = upi_ref_number
        self.txn_time = txn_time
        self.is_p2p = is_p2p
        self.account_last4 = account_last4
        self.raw_text = raw_text


# --- Main Parse Function ---

def parse_email_body(body: str, account_type: str) -> Optional[ParsedTransaction]:
    """Parse a supported HDFC alert, using content as the account authority.

    ``account_type`` is only a sender-routing hint. HDFC can send savings and
    credit-card alerts from the same address, so explicit wording and the
    instrument's last four digits decide the parsed profile.
    """
    if account_type not in {'hdfc_savings', 'hdfc_credit'}:
        return None
    text = extract_text_from_html(body) if '<' in body else body

    # Try RuPay Credit Card + UPI first (comes from savings sender but is credit card)
    match = RUPAY_CREDIT_UPI_PATTERN.search(text)
    if match:
        merchant_raw = match.group('merchant').strip()
        vpa = match.group('vpa').strip()
        is_p2p = bool(P2P_VPA_PATTERN.match(vpa))
        return ParsedTransaction(
            amount=parse_amount(match.group('amount')),
            merchant_raw=merchant_raw,
            merchant_normalized=normalize_merchant(merchant_raw),
            txn_date=parse_upi_date(match.group('date')),
            txn_type='debit',
            instrument='rupay_credit_upi',
            account_type='hdfc_credit',
            vpa_handle=vpa,
            upi_ref_number=match.group('ref'),
            is_p2p=is_p2p,
            account_last4=match.group('card_last4'),
            raw_text=text,
        )

    # Try UPI Credit/Refund
    match = UPI_CREDIT_PATTERN.search(text)
    if match:
        merchant_raw = match.group('merchant').strip()
        vpa = match.group('vpa').strip()
        is_p2p = bool(P2P_VPA_PATTERN.match(vpa))
        return ParsedTransaction(
            amount=parse_amount(match.group('amount')),
            merchant_raw=merchant_raw,
            merchant_normalized=normalize_merchant(merchant_raw),
            txn_date=parse_upi_date(match.group('date')),
            txn_type='credit',
            instrument='upi',
            account_type='hdfc_savings',
            vpa_handle=vpa,
            is_p2p=is_p2p,
            account_last4=match.group('account'),
            raw_text=text,
        )

    # HDFC sender addresses are not reliable account-type identifiers. These
    # patterns are explicit enough to select savings/debit routing safely.
    match = UPI_DEBIT_PATTERN.search(text)
    if match:
        merchant_raw = match.group('merchant').strip()
        vpa = match.group('vpa').strip()
        is_p2p = bool(P2P_VPA_PATTERN.match(vpa))
        return ParsedTransaction(
            amount=parse_amount(match.group('amount')),
            merchant_raw=merchant_raw,
            merchant_normalized=normalize_merchant(merchant_raw),
            txn_date=parse_upi_date(match.group('date')),
            txn_type='debit',
            instrument='upi',
            account_type='hdfc_savings',
            vpa_handle=vpa,
            upi_ref_number=match.group('ref'),
            is_p2p=is_p2p,
            account_last4=match.group('account'),
            raw_text=text,
        )

    match = DEBIT_CARD_PATTERN.search(text)
    if match:
        merchant_raw = match.group('merchant').strip()
        return ParsedTransaction(
            amount=parse_amount(match.group('amount')),
            merchant_raw=merchant_raw,
            merchant_normalized=normalize_merchant(merchant_raw),
            txn_date=parse_debit_card_date(match.group('date')),
            txn_type='debit',
            instrument='debit_card',
            account_type='hdfc_savings',
            txn_time=match.group('time'),
            account_last4=match.group('card_last4'),
            raw_text=text,
        )

    match = CC_DEBIT_PATTERN.search(text)
    if match:
        merchant_raw = match.group('merchant').strip()
        return ParsedTransaction(
            amount=parse_amount(match.group('amount')),
            merchant_raw=merchant_raw,
            merchant_normalized=normalize_merchant(merchant_raw),
            txn_date=parse_cc_date(match.group('date')),
            txn_type='debit',
            instrument='credit_card',
            account_type='hdfc_credit',
            txn_time=match.group('time') if match.group('time') else None,
            account_last4=match.group('card_last4'),
            raw_text=text,
        )

    return None
