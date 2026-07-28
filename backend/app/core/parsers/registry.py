from __future__ import annotations

import io
from typing import Optional

import pdfplumber

from app.core.parsers.base import StatementParserPlugin
from app.core.parsers.hdfc_cc import PARSER as hdfc_cc
from app.core.parsers.hdfc_savings import PARSER as hdfc_savings
from app.core.statement_parser import StatementParseResult


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
    except Exception as exc:
        return "", f"Failed to open PDF: {exc}"
    try:
        return "\n".join(page.extract_text() or "" for page in pdf.pages), None
    except Exception as exc:
        return "", f"Failed to inspect PDF: {exc}"
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

    detected: list[StatementParserPlugin] = []
    if file_format == "pdf":
        text, error = _pdf_text(contents, password)
        if error:
            return StatementParseResult(errors=[error])
        detected = [parser for parser in parsers if parser.detect_text(text)]
    elif file_format in {"xls", "xlsx"}:
        detected = [
            parser for parser in parsers
            if parser.profile == "hdfc_savings"
        ]

    ordered = detected + [parser for parser in parsers if parser not in detected]
    collected_errors: list[str] = []
    last_result = StatementParseResult()
    for parser in ordered:
        result = parser.parse(contents, file_format, password)
        last_result = result
        if result.transactions:
            result.errors = []
            return result
        collected_errors.extend(result.errors)

    last_result.errors = collected_errors or [
        "No registered parser recognized this statement",
    ]
    return last_result
