from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class DocumentElement:
    element_type: str
    text: str
    page: int
    bounding_box: tuple[float, float, float, float] | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedDocument:
    extractor: str
    page_count: int
    elements: tuple[DocumentElement, ...]
    warnings: tuple[str, ...] = ()
    elapsed_ms: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
