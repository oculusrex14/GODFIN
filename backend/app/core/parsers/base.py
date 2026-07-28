from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.core.statement_parser import StatementParseResult


ParseCallable = Callable[[bytes, str, Optional[str]], StatementParseResult]
DetectCallable = Callable[[str], bool]


@dataclass(frozen=True)
class StatementParserPlugin:
    """Declarative contract for a bank/account statement parser."""

    profile: str
    bank: str
    account_type: str
    statement_type: str
    formats: tuple[str, ...]
    detect_text: DetectCallable
    parse: ParseCallable
