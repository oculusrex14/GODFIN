from __future__ import annotations

import re
from typing import Optional

from app.core.parsers.base import StatementParserPlugin
from app.core.parsers.certified_savings_pdf import parse_kotak_savings_pdf
from app.core.pdf_extraction import PDFPLUMBER_ENGINE, PdfExtractionError
from app.core.statement_parser import StatementParseResult


def _detect(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "", text.lower())
    return all(
        marker in normalized
        for marker in (
            "kotakmahindrabank",
            "accountstatement",
            "savingsaccounttransactions",
            "withdrawaldr",
            "depositcr",
        )
    )


def _parse(
    contents: bytes,
    file_format: str,
    password: Optional[str],
    account_last4: Optional[str] = None,
) -> StatementParseResult:
    result = StatementParseResult(
        statement_type="kotak_savings",
        parser_profile="kotak_savings",
        recognized=True,
    )
    if file_format != "pdf":
        result.errors.append(f"Unsupported Kotak savings format: {file_format}")
        return result
    try:
        with PDFPLUMBER_ENGINE.open_document(contents, password) as document:
            parse_kotak_savings_pdf(document, result, account_last4)
    except PdfExtractionError:
        result.errors.append(
            "The PDF could not be opened. Check the file and its password, then try again."
        )
    except Exception:
        result.errors.append(
            "The PDF layout could not be read as a certified Kotak savings statement."
        )
    return result


PARSER = StatementParserPlugin(
    profile="kotak_savings",
    bank="KOTAK",
    account_type="savings",
    statement_type="kotak_savings",
    formats=("pdf",),
    detect_text=_detect,
    parse=_parse,
)
