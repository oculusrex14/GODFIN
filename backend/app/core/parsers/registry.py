from __future__ import annotations

import io
from typing import Optional

import pdfplumber

from app.core.parsers.base import StatementParserPlugin
from app.core.parsers.hdfc_cc import PARSER as hdfc_cc
from app.core.parsers.hdfc_savings import PARSER as hdfc_savings
from app.core.statement_parser import StatementParseResult


MAX_PDF_PAGES = 250


def registered_parsers() -> tuple[StatementParserPlugin, ...]:
    # Explicit imports keep parser plugins discoverable in frozen builds.
    return (hdfc_savings, hdfc_cc)


def supported_parser_profiles() -> list[dict[str, object]]:
    return [
        {
            "profile": parser.profile,
            "bank": parser.bank,
            "account_type": parser.account_type,
            "statement_type": parser.statement_type,
            "formats": list(parser.formats),
        }
        for parser in registered_parsers()
    ]


def account_requirements(statement_type: str) -> tuple[Optional[str], Optional[str]]:
    for parser in registered_parsers():
        if parser.statement_type == statement_type:
            return parser.bank, parser.account_type
    return None, None


def _pdf_text(contents: bytes, password: Optional[str]) -> tuple[str, Optional[str]]:
    try:
        pdf = pdfplumber.open(io.BytesIO(contents), password=password)
    except Exception:
        return "", (
            "The PDF could not be opened. Check the file and its password, then try again."
        )
    try:
        if len(pdf.pages) > MAX_PDF_PAGES:
            return "", f"PDF exceeds the {MAX_PDF_PAGES}-page review limit"
        return "\n".join(page.extract_text() or "" for page in pdf.pages), None
    except Exception:
        return "", "The PDF layout could not be inspected safely."
    finally:
        pdf.close()


def parse_registered_statement(
    contents: bytes,
    file_format: str,
    password: Optional[str] = None,
) -> StatementParseResult:
    parsers = [
        parser for parser in registered_parsers()
        if file_format in parser.formats
    ]
    if not parsers:
        return StatementParseResult(
            errors=[f"No statement parser supports {file_format.upper()}"],
        )

    if file_format == "pdf":
        text, error = _pdf_text(contents, password)
        if error:
            return StatementParseResult(errors=[error])
        detected = [parser for parser in parsers if parser.detect_text(text)]
        if not detected:
            return StatementParseResult(
                errors=[
                    "Unsupported or unrecognized PDF statement; select a supported HDFC profile",
                ],
            )
        if len(detected) != 1:
            return StatementParseResult(
                errors=["Statement is ambiguous between multiple parser profiles"],
            )
        parser = detected[0]
    else:
        spreadsheet_parsers = [
            parser for parser in parsers if parser.profile == "hdfc_savings"
        ]
        if len(spreadsheet_parsers) != 1:
            return StatementParseResult(
                errors=["No unique parser is registered for this spreadsheet format"],
            )
        parser = spreadsheet_parsers[0]

    result = parser.parse(contents, file_format, password)
    result.parser_profile = result.parser_profile or parser.profile
    if result.errors or not result.transactions:
        result.transactions.clear()
        result.reconciliation_status = "failed"
        if not result.errors:
            result.errors.append("Registered parser produced no transactions")
        return result
    if not result.recognized:
        result.transactions.clear()
        result.reconciliation_status = "failed"
        result.errors.append("Parser did not establish a supported bank and statement profile")
        return result
    if result.reconciliation_status != "passed":
        result.transactions.clear()
        result.errors.append("Statement controls did not reconcile")
        result.reconciliation_status = "failed"
    return result
