from __future__ import annotations

from typing import Optional
import re

from app.core.parsers.base import StatementParserPlugin
from app.core.pdf_extraction import PDFPLUMBER_ENGINE, PdfExtractionError
from app.core.statement_parser import (
    StatementParseResult,
    _parse_hdfc_cc_statement,
)


def _detect(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "", text.lower())
    return "hdfcbank" in normalized and (
        "creditcardstatement" in normalized
        or "statementofcreditcard" in normalized
    ) and (
        "transactionamount" in normalized
        or ("transactiondescription" in normalized and "amount" in normalized)
    )


def _parse(
    contents: bytes,
    file_format: str,
    password: Optional[str],
    _account_last4: Optional[str] = None,
) -> StatementParseResult:
    result = StatementParseResult(
        statement_type="hdfc_credit_card",
        parser_profile="hdfc_credit",
        recognized=True,
    )
    if file_format != "pdf":
        result.errors.append(f"Unsupported HDFC credit-card format: {file_format}")
        return result

    try:
        with PDFPLUMBER_ENGINE.open_document(contents, password) as document:
            _parse_hdfc_cc_statement(document, result)
    except PdfExtractionError:
        result.errors.append(
            "The PDF could not be opened. Check the file and its password, then try again."
        )
    except Exception:
        result.errors.append(
            "The PDF layout could not be read as an HDFC credit-card statement."
        )
    if result.errors:
        result.transactions.clear()
        result.reconciliation_status = "failed"
    elif not result.transactions:
        result.errors.append("No explicit HDFC credit-card transactions were found")
        result.reconciliation_status = "failed"
    else:
        result.reconciliation_status = "passed"
        result.reconciliation_method = "explicit_credit_card_amount_columns"
    return result


PARSER = StatementParserPlugin(
    profile="hdfc_credit",
    bank="HDFC",
    account_type="credit_card",
    statement_type="hdfc_credit_card",
    formats=("pdf",),
    detect_text=_detect,
    parse=_parse,
)
