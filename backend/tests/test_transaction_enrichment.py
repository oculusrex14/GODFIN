from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.core.reconciliation import ReconciliationService
from app.core.statement_parser import (
    ParsedStatement,
    ParsedTransaction,
    StatementParseResult,
    StatementTransaction,
)
from app.core.transaction_enrichment import (
    DetailedSemantic,
    apply_transaction_envelope,
    build_transaction_envelope,
    extract_processor,
    extract_reference,
    extract_vpa,
    infer_detailed_semantic,
)


def test_general_vpa_reference_and_processor_extraction_preserve_source_text():
    raw = "UPI/DR/RAZORPAY*ABC STORE/jane.doe-14@okhdfcbank/UTR 123456789012"

    assert extract_vpa(raw) == "jane.doe-14@okhdfcbank"
    assert extract_reference(raw) == "123456789012"
    assert extract_processor("RAZORPAY*ABC STORE") == ("Razorpay", "ABC STORE")

    envelope = build_transaction_envelope(
        raw_text=raw,
        source_type="statement_upload",
        source_bank="hdfc",
        source_account_id="account-1",
        source_format_version="fixture-v1",
        booking_date=date(2026, 8, 1),
        value_date=date(2026, 8, 2),
        amount="199.50",
        currency="inr",
        direction="debit",
        running_balance="1500.25",
        instrument="upi",
        merchant_raw="RAZORPAY*ABC STORE",
        category="SHOPPING",
        parser_version="fixture-parser-v1",
    )

    assert envelope.raw_text == raw
    assert envelope.processor_candidate == "Razorpay"
    assert envelope.merchant_candidate == "ABC STORE"
    assert envelope.vpa == "jane.doe-14@okhdfcbank"
    assert envelope.reference == "123456789012"
    assert envelope.currency == "INR"
    assert envelope.review_required is False


@pytest.mark.parametrize(
    ("direction", "coarse", "rail", "role", "text", "expected"),
    [
        ("credit", "income", None, None, "ACME PAYROLL SALARY", "salary"),
        ("debit", "expense", "atm", None, "ATM CASH", "cash_withdrawal"),
        ("debit", "expense", None, None, "HOME LOAN EMI", "emi"),
        ("credit", "refund", None, None, "MERCHANT REFUND", "refund"),
        ("debit", "unknown", "upi", "unknown", "UPI PAYMENT", "unknown"),
    ],
)
def test_detailed_semantics_use_evidence_and_abstain_when_ambiguous(
    direction,
    coarse,
    rail,
    role,
    text,
    expected,
):
    semantic, evidence = infer_detailed_semantic(
        direction=direction,
        coarse_semantic=coarse,
        payment_rail=rail,
        vpa_role=role,
        text_parts=(text,),
    )

    assert semantic == expected
    if expected == DetailedSemantic.UNKNOWN.value:
        assert evidence == ("abstained:insufficient_evidence",)
    else:
        assert evidence


def test_envelope_application_is_additive_and_uses_exact_running_balance_minor():
    target = SimpleNamespace(existing_value="untouched")
    envelope = build_transaction_envelope(
        raw_text="NEFT REF ABCD12345678",
        source_type="statement_upload",
        source_bank="hdfc",
        source_account_id="account-1",
        source_format_version="v1",
        booking_date=date(2026, 8, 2),
        amount="1.00",
        direction="credit",
        running_balance="-12.34",
        coarse_semantic="unknown",
    )

    apply_transaction_envelope(target, envelope)

    assert target.existing_value == "untouched"
    assert target.running_balance_minor == -1234
    assert target.reference_number == "ABCD12345678"
    assert target.review_required is True


def test_reconciliation_keeps_exact_raw_narration_and_enrichment_fields():
    raw = "UPI/DR/123456789012/COFFEE/jane.doe@okaxis"
    parsed = ParsedTransaction(
        date=date(2026, 8, 3),
        value_date=date(2026, 8, 4),
        description=raw,
        amount=245.75,
        type="debit",
        reference="123456789012",
        instrument="upi",
        source_bank="hdfc",
        source_format_version="hdfc-savings-v1",
        parser_version="parser-v1",
    )

    transaction = ReconciliationService.create_transaction_from_parsed(
        parsed,
        "account-1",
    )

    assert transaction.raw_text == raw
    assert transaction.raw_text.startswith("Statement:") is False
    assert transaction.value_date == date(2026, 8, 4)
    assert transaction.source_bank == "hdfc"
    assert transaction.reference_number == "123456789012"
    assert transaction.review_required is True


def test_statement_result_only_labels_bank_when_parser_identifies_it():
    generic = StatementParseResult(
        statement_type="mapped_spreadsheet",
        parser_profile="mapped-v1",
        transactions=[
            StatementTransaction(
                date=date(2026, 8, 5),
                description="Generic row",
                amount=100,
                txn_type="debit",
            )
        ],
    )
    hdfc = StatementParseResult(
        statement_type="hdfc_credit_card",
        parser_profile="hdfc-credit-v2",
        transactions=[
            StatementTransaction(
                date=date(2026, 8, 5),
                description="Known HDFC row",
                amount=100,
                txn_type="debit",
            )
        ],
    )

    generic_parsed = ParsedStatement.from_statement_result(generic)
    hdfc_parsed = ParsedStatement.from_statement_result(hdfc)

    assert generic_parsed.transactions[0].source_bank is None
    assert generic_parsed.transactions[0].parser_version is None
    assert hdfc_parsed.transactions[0].source_bank == "hdfc"
    assert hdfc_parsed.transactions[0].parser_version == "hdfc-credit-v2"
