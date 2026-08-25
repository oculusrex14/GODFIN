"""Deterministic, local transaction enrichment with explicit abstention."""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Iterable

from app.core.extraction_ir import TransactionEnvelope
from app.core.money import money_decimal, money_to_minor
from app.core.taxonomy import TAXONOMY


class DetailedSemantic(str, Enum):
    PURCHASE = "purchase"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    INTERNAL_TRANSFER = "internal_transfer"
    CREDIT_CARD_PAYMENT = "credit_card_payment"
    REFUND = "refund"
    REVERSAL = "reversal"
    CHARGEBACK = "chargeback"
    FEE_CHARGE = "fee_charge"
    CASH_WITHDRAWAL = "cash_withdrawal"
    CASH_DEPOSIT = "cash_deposit"
    INTEREST_CREDIT = "interest_credit"
    INTEREST_DEBIT = "interest_debit"
    SALARY = "salary"
    OTHER_INCOME = "other_income"
    CASHBACK_REWARD = "cashback_reward"
    WALLET_TOPUP = "wallet_topup"
    WALLET_WITHDRAWAL = "wallet_withdrawal"
    INVESTMENT_BUY = "investment_buy"
    INVESTMENT_SELL = "investment_sell"
    INVESTMENT_SIP = "investment_sip"
    DIVIDEND = "dividend"
    LOAN_DISBURSEMENT = "loan_disbursement"
    LOAN_PAYMENT = "loan_payment"
    EMI = "emi"
    BILL_PAYMENT = "bill_payment"
    TAX_PAYMENT = "tax_payment"
    TAX_REFUND = "tax_refund"
    UNKNOWN = "unknown"


DETAILED_SEMANTICS = frozenset(item.value for item in DetailedSemantic)

_VPA_PATTERN = re.compile(
    r"(?<![A-Z0-9._-])"
    r"([A-Z0-9][A-Z0-9._-]{1,99}@[A-Z0-9][A-Z0-9.-]{1,63})"
    r"(?![A-Z0-9._-])",
    re.IGNORECASE,
)
_REFERENCE_PATTERN = re.compile(
    r"(?:(?:UTR|RRN|REF(?:ERENCE)?|UPI\s*(?:REF)?)\s*[:#-]?\s*)"
    r"([A-Z0-9]{8,40})",
    re.IGNORECASE,
)
_PROCESSOR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Razorpay", re.compile(r"^(?:RAZORPAY|RZP)[* /:-]+", re.IGNORECASE)),
    ("PayU", re.compile(r"^(?:PAYU|PYU)[* /:-]+", re.IGNORECASE)),
    ("BillDesk", re.compile(r"^BILLDESK[* /:-]+", re.IGNORECASE)),
    ("CCAvenue", re.compile(r"^CCAVENUE[* /:-]+", re.IGNORECASE)),
    ("Cashfree", re.compile(r"^CASHFREE[* /:-]+", re.IGNORECASE)),
)


def _text(parts: Iterable[object]) -> str:
    return " ".join(str(part).strip() for part in parts if part).upper()


def extract_vpa(*parts: object) -> str | None:
    match = _VPA_PATTERN.search(_text(parts))
    return match.group(1).lower()[:100] if match else None


def extract_reference(*parts: object) -> str | None:
    match = _REFERENCE_PATTERN.search(_text(parts))
    return match.group(1).upper()[:64] if match else None


def detect_payment_rail(*parts: object, instrument: str | None = None) -> str | None:
    normalized_instrument = re.sub(
        r"[^a-z0-9]+", "_", (instrument or "").strip().lower()
    ).strip("_")
    instrument_rails = {
        "upi": "upi",
        "imps": "imps",
        "neft": "neft",
        "rtgs": "rtgs",
        "nach": "nach",
        "ach": "ach",
        "atm": "atm",
        "cash_withdrawal": "atm",
        "cheque": "cheque",
        "chq": "cheque",
        "debit_card": "card",
        "credit_card": "card",
        "card": "card",
        "pos": "pos",
    }
    if normalized_instrument in instrument_rails:
        return instrument_rails[normalized_instrument]
    text = _text((*parts, instrument))
    ordered = (
        ("UPI", ("UPI", "VPA")),
        ("IMPS", ("IMPS",)),
        ("NEFT", ("NEFT",)),
        ("RTGS", ("RTGS",)),
        ("NACH", ("NACH",)),
        ("ACH", ("ACH",)),
        ("ATM", ("ATM", "CASH WITHDRAWAL")),
        ("CHEQUE", ("CHEQUE", "CHQ")),
        ("CARD", ("DEBIT CARD", "CREDIT CARD", "RUPAY", "VISA", "MASTERCARD")),
        ("POS", ("POS",)),
    )
    for rail, markers in ordered:
        if any(marker in text for marker in markers):
            return rail.lower()
    return None


def extract_processor(raw_text: str, merchant_raw: str | None = None) -> tuple[str | None, str | None]:
    candidate = (merchant_raw or raw_text).strip()
    for processor, pattern in _PROCESSOR_PATTERNS:
        match = pattern.search(candidate)
        if match:
            merchant = candidate[match.end():].strip(" *-/:|") or None
            return processor, merchant[:255] if merchant else None
    return None, candidate[:255] if candidate else None


def infer_vpa_role(vpa: str | None, merchant_candidate: str | None) -> str | None:
    if not vpa:
        return None
    local = vpa.split("@", 1)[0]
    if re.fullmatch(r"\d{10}", local):
        return "person"
    merchant = (merchant_candidate or "").upper()
    if any(term in merchant for term in ("PVT", "LTD", "STORE", "MART", "HOTEL", "CAFE")):
        return "merchant"
    return "unknown"


def infer_detailed_semantic(
    *,
    direction: str,
    coarse_semantic: str,
    payment_rail: str | None,
    vpa_role: str | None,
    category: str | None = None,
    subcategory: str | None = None,
    text_parts: Iterable[object] = (),
) -> tuple[str, tuple[str, ...]]:
    """Return a detailed economic type or deliberately abstain to UNKNOWN."""

    text = _text(text_parts)
    category_upper = (category or "").upper()
    subcategory_upper = (subcategory or "").upper()
    evidence: list[str] = []

    def matched(value: DetailedSemantic, code: str) -> tuple[str, tuple[str, ...]]:
        evidence.append(code)
        return value.value, tuple(evidence)

    if any(term in text for term in ("REVERSAL", "REVERSED", "RETURNED PAYMENT")):
        return matched(DetailedSemantic.REVERSAL, "descriptor:reversal")
    if "CHARGEBACK" in text:
        return matched(DetailedSemantic.CHARGEBACK, "descriptor:chargeback")
    if "TAX REFUND" in text or "INCOME TAX REFUND" in text:
        return matched(DetailedSemantic.TAX_REFUND, "descriptor:tax_refund")
    if coarse_semantic == "refund" or "REFUND" in text:
        return matched(DetailedSemantic.REFUND, "coarse_or_descriptor:refund")
    if coarse_semantic == "cashback" or "CASHBACK" in text or "CASH BACK" in text:
        return matched(DetailedSemantic.CASHBACK_REWARD, "coarse_or_descriptor:cashback")
    if "CREDIT CARD" in text and any(term in text for term in ("PAYMENT", "BILL", "CRED")):
        return matched(DetailedSemantic.CREDIT_CARD_PAYMENT, "descriptor:credit_card_payment")
    if any(term in text for term in ("WALLET TOPUP", "WALLET LOAD", "ADD MONEY")) and direction == "debit":
        return matched(DetailedSemantic.WALLET_TOPUP, "descriptor:wallet_topup")
    if coarse_semantic == "internal_transfer" or category_upper == "TRANSFERS":
        if any(term in text for term in ("SELF", "OWN ACCOUNT", "INTERNAL")):
            return matched(DetailedSemantic.INTERNAL_TRANSFER, "descriptor:self_transfer")
        detail = DetailedSemantic.TRANSFER_IN if direction == "credit" else DetailedSemantic.TRANSFER_OUT
        return matched(detail, "coarse:transfer")
    if any(term in text for term in ("BANK CHARGE", "SERVICE CHARGE", "MARKUP", "SURCHARGE", "FEE")):
        return matched(DetailedSemantic.FEE_CHARGE, "descriptor:fee")
    if payment_rail == "atm" and direction == "debit":
        return matched(DetailedSemantic.CASH_WITHDRAWAL, "rail:atm_debit")
    if any(term in text for term in ("CASH DEPOSIT", "CASH DEP")) and direction == "credit":
        return matched(DetailedSemantic.CASH_DEPOSIT, "descriptor:cash_deposit")
    if any(term in text for term in ("SALARY", "WAGES", "PAYROLL", "PENSION")) and direction == "credit":
        return matched(DetailedSemantic.SALARY, "descriptor:salary")
    if "DIVIDEND" in text and direction == "credit":
        return matched(DetailedSemantic.DIVIDEND, "descriptor:dividend")
    if "INTEREST" in text:
        detail = DetailedSemantic.INTEREST_CREDIT if direction == "credit" else DetailedSemantic.INTEREST_DEBIT
        return matched(detail, "descriptor:interest")
    if any(term in text for term in ("LOAN DISBURSE", "LOAN CREDIT")) and direction == "credit":
        return matched(DetailedSemantic.LOAN_DISBURSEMENT, "descriptor:loan_disbursement")
    if "EMI" in text and direction == "debit":
        return matched(DetailedSemantic.EMI, "descriptor:emi")
    if "LOAN" in text and direction == "debit":
        return matched(DetailedSemantic.LOAN_PAYMENT, "descriptor:loan_payment")
    if (
        re.search(r"\bSIP\b", text) or "SYSTEMATIC INVESTMENT" in text
    ) and direction == "debit":
        return matched(DetailedSemantic.INVESTMENT_SIP, "descriptor:investment_sip")
    if any(term in text for term in ("BROKER", "STOCK", "SECURITIES", "MUTUAL FUND")):
        detail = DetailedSemantic.INVESTMENT_SELL if direction == "credit" else DetailedSemantic.INVESTMENT_BUY
        return matched(detail, "descriptor:investment")
    if "WALLET" in text and direction == "credit":
        return matched(DetailedSemantic.WALLET_WITHDRAWAL, "descriptor:wallet_withdrawal")
    if any(term in text for term in ("GST", "TDS", "INCOME TAX", "TAX PAYMENT")) and direction == "debit":
        return matched(DetailedSemantic.TAX_PAYMENT, "descriptor:tax_payment")
    if "BILL" in text or "UTILIT" in subcategory_upper:
        return matched(DetailedSemantic.BILL_PAYMENT, "descriptor_or_category:bill")
    if direction == "credit" and coarse_semantic == "income":
        return matched(DetailedSemantic.OTHER_INCOME, "coarse:verified_income")
    if direction == "debit" and payment_rail in {"card", "pos"}:
        return matched(DetailedSemantic.PURCHASE, "rail:merchant_purchase")
    if direction == "debit" and payment_rail == "upi" and vpa_role == "merchant":
        return matched(DetailedSemantic.PURCHASE, "vpa_role:merchant")
    return DetailedSemantic.UNKNOWN.value, ("abstained:insufficient_evidence",)


def build_transaction_envelope(
    *,
    raw_text: str,
    source_type: str,
    source_account_id: str,
    booking_date: date,
    amount: object,
    direction: str,
    transaction_status: str = "settled",
    source_bank: str | None = None,
    source_format_version: str | None = None,
    value_date: date | None = None,
    currency: str = "INR",
    running_balance: object | None = None,
    instrument: str | None = None,
    merchant_raw: str | None = None,
    merchant_candidate: str | None = None,
    counterparty_candidate: str | None = None,
    vpa: str | None = None,
    reference: str | None = None,
    coarse_semantic: str = "unknown",
    category: str | None = None,
    subcategory: str | None = None,
    parser_version: str | None = None,
) -> TransactionEnvelope:
    if direction not in {"debit", "credit"}:
        raise ValueError("Transaction direction must be debit or credit")
    normalized_currency = currency.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", normalized_currency):
        raise ValueError("Transaction currency must be a three-letter code")

    processor, processor_merchant = extract_processor(raw_text, merchant_raw)
    merchant = merchant_candidate or processor_merchant or merchant_raw
    resolved_vpa = (vpa or extract_vpa(raw_text, merchant_raw))
    resolved_vpa = resolved_vpa.lower()[:100] if resolved_vpa else None
    vpa_role = infer_vpa_role(resolved_vpa, merchant)
    payment_rail = detect_payment_rail(raw_text, merchant_raw, instrument=instrument)
    resolved_reference = (reference or extract_reference(raw_text))
    resolved_reference = resolved_reference.upper()[:64] if resolved_reference else None
    detail, evidence = infer_detailed_semantic(
        direction=direction,
        coarse_semantic=coarse_semantic,
        payment_rail=payment_rail,
        vpa_role=vpa_role,
        category=category,
        subcategory=subcategory,
        text_parts=(raw_text, merchant_raw, merchant),
    )
    review_required = detail == DetailedSemantic.UNKNOWN.value or not category
    return TransactionEnvelope(
        raw_text=raw_text,
        source_type=source_type,
        source_bank=source_bank,
        source_account_id=source_account_id,
        source_format_version=source_format_version,
        booking_date=booking_date,
        value_date=value_date,
        amount=money_decimal(amount),
        currency=normalized_currency,
        direction=direction,
        running_balance=(money_decimal(running_balance) if running_balance is not None else None),
        payment_rail=payment_rail,
        transaction_status=transaction_status,
        instrument=instrument,
        merchant_candidate=merchant[:255] if merchant else None,
        counterparty_candidate=(counterparty_candidate[:255] if counterparty_candidate else None),
        processor_candidate=processor,
        vpa=resolved_vpa,
        vpa_role=vpa_role,
        reference=resolved_reference,
        semantic_detail=detail,
        parser_version=parser_version,
        extraction_evidence=evidence,
        review_required=review_required,
    )


def apply_transaction_envelope(transaction: object, envelope: TransactionEnvelope) -> None:
    transaction.value_date = envelope.value_date
    transaction.currency = envelope.currency
    transaction.source_bank = envelope.source_bank
    transaction.source_format_version = envelope.source_format_version
    transaction.payment_rail = envelope.payment_rail
    transaction.processor_candidate = envelope.processor_candidate
    transaction.counterparty_candidate = envelope.counterparty_candidate
    transaction.reference_number = envelope.reference
    transaction.parser_version = envelope.parser_version
    transaction.semantic_detail = envelope.semantic_detail
    transaction.vpa_role = envelope.vpa_role
    transaction.review_required = envelope.review_required
    transaction.running_balance_minor = (
        money_to_minor(envelope.running_balance)
        if envelope.running_balance is not None
        else None
    )
    transaction.extraction_evidence = json.dumps(
        list(envelope.extraction_evidence),
        separators=(",", ":"),
        sort_keys=True,
    )


def refresh_transaction_enrichment(transaction: object) -> None:
    """Refresh derived enrichment after a category is learned or confirmed."""

    payment_rail = getattr(transaction, "payment_rail", None) or detect_payment_rail(
        getattr(transaction, "raw_text", None),
        getattr(transaction, "merchant_raw", None),
        instrument=getattr(transaction, "instrument", None),
    )
    vpa = getattr(transaction, "vpa_handle", None) or extract_vpa(
        getattr(transaction, "raw_text", None)
    )
    vpa_role = getattr(transaction, "vpa_role", None) or infer_vpa_role(
        vpa,
        getattr(transaction, "merchant_normalized", None)
        or getattr(transaction, "merchant_raw", None),
    )
    detail, evidence = infer_detailed_semantic(
        direction=getattr(transaction, "type", ""),
        coarse_semantic=getattr(transaction, "semantic_type", "unknown"),
        payment_rail=payment_rail,
        vpa_role=vpa_role,
        category=getattr(transaction, "category", None),
        subcategory=getattr(transaction, "subcategory", None),
        text_parts=(
            getattr(transaction, "raw_text", None),
            getattr(transaction, "merchant_raw", None),
            getattr(transaction, "merchant_normalized", None),
        ),
    )
    transaction.payment_rail = payment_rail
    transaction.vpa_role = vpa_role
    transaction.semantic_detail = detail
    transaction.extraction_evidence = json.dumps(
        list(evidence), separators=(",", ":"), sort_keys=True
    )
    category = getattr(transaction, "category", None)
    confidence = float(getattr(transaction, "confidence", 0.0) or 0.0)
    threshold = TAXONOMY.get(category or "", {}).get("confidence_threshold", 0.85)
    transaction.review_required = (
        not category
        or confidence < threshold
        or detail == DetailedSemantic.UNKNOWN.value
    )
