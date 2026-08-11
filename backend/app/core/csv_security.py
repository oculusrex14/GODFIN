"""Spreadsheet-safe CSV cell handling for every GODFIN export."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any


FORMULA_PREFIXES = frozenset({"=", "+", "-", "@"})


def _first_effective_character(value: str) -> str | None:
    """Return the first character a spreadsheet may treat as significant."""
    for character in value:
        category = unicodedata.category(character)
        if character.isspace() or category in {"Cc", "Cf"}:
            continue
        return character
    return None


def spreadsheet_safe_cell(value: Any) -> Any:
    """Force formula-like text to remain text while preserving other cell types."""
    if not isinstance(value, str) or not value:
        return value
    if _first_effective_character(value) in FORMULA_PREFIXES:
        return f"'{value}"
    return value


def spreadsheet_safe_row(values: Iterable[Any]) -> list[Any]:
    return [spreadsheet_safe_cell(value) for value in values]


def spreadsheet_safe_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: spreadsheet_safe_cell(value) for key, value in values.items()}
