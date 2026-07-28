from __future__ import annotations

import io
from typing import Optional

import pdfplumber

from app.core.parsers.base import StatementParserPlugin
from app.core.statement_parser import (
    StatementParseResult,
    _parse_hdfc_cc_statement,
)


def _detect(text: str) -> bool:
    normalized = text.lower()
    return "credit card" in normalized or "card number" in normalized


def _parse(
    contents: bytes,
    file_format: str,
    password: Optional[str],
) -> StatementParseResult:
    result = StatementParseResult(statement_type="hdfc_credit_card")
    if file_format != "pdf":
        result.errors.append(f"Unsupported HDFC credit-card format: {file_format}")
        return result

    try:
        pdf = pdfplumber.open(io.BytesIO(contents), password=password)
    except Exception as exc:
        result.errors.append(f"Failed to open PDF: {exc}")
        return result

    try:
        _parse_hdfc_cc_statement(pdf, result)
    except Exception as exc:
        result.errors.append(f"Parse error: {exc}")
    finally:
        pdf.close()
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
