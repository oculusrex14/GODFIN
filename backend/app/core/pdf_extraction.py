from __future__ import annotations

import io
import json
import shutil
import tempfile
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

import pdfplumber


class PdfExtractionError(RuntimeError):
    """A PDF extraction backend could not inspect a document safely."""


class PdfExtractionEngine(ABC):
    """Minimal extraction contract used by certified statement parsers."""

    name: str

    @abstractmethod
    def open_document(
        self,
        contents: bytes,
        password: Optional[str] = None,
    ) -> AbstractContextManager[Any]:
        """Open one PDF and close all extraction resources on exit."""


class PdfPlumberEngine(PdfExtractionEngine):
    name = "pdfplumber"

    @contextmanager
    def open_document(
        self,
        contents: bytes,
        password: Optional[str] = None,
    ) -> Iterator[pdfplumber.PDF]:
        try:
            document = pdfplumber.open(io.BytesIO(contents), password=password)
        except Exception as exc:
            raise PdfExtractionError(
                "The PDF could not be opened. Check the file and its password."
            ) from exc
        try:
            yield document
        finally:
            document.close()


class OpenDataLoaderEngine:
    """Optional benchmark-only OpenDataLoader adapter.

    The package and Java runtime are deliberately not GODFIN dependencies. The
    adapter is available to the private benchmark harness when both are already
    installed, but production statement imports never select it implicitly.
    """

    name = "opendataloader"

    @staticmethod
    def runtime_status() -> dict[str, object]:
        java = shutil.which("java")
        try:
            import opendataloader_pdf  # noqa: F401

            package_available = True
        except ImportError:
            package_available = False
        return {
            "java_available": java is not None,
            "package_available": package_available,
            "ready": bool(java and package_available),
            "production_enabled": False,
        }

    def extract_json(
        self,
        contents: bytes,
        password: Optional[str] = None,
    ) -> dict[str, object]:
        if not self.runtime_status()["ready"]:
            raise PdfExtractionError(
                "OpenDataLoader is not installed in this benchmark environment."
            )
        try:
            import opendataloader_pdf

            with tempfile.TemporaryDirectory(prefix="godfin-odl-benchmark-") as tmp:
                root = Path(tmp)
                source = root / "statement.pdf"
                output = root / "output"
                source.write_bytes(contents)
                output.mkdir()
                options: dict[str, object] = {
                    "input_path": [str(source)],
                    "output_dir": str(output),
                    "format": "json",
                    "image_output": "off",
                }
                if password:
                    options["password"] = password
                opendataloader_pdf.convert(**options)
                result = output / "statement.json"
                if not result.is_file():
                    raise PdfExtractionError(
                        "OpenDataLoader did not produce the expected JSON output."
                    )
                payload = json.loads(result.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise PdfExtractionError(
                        "OpenDataLoader returned an invalid document structure."
                    )
                return payload
        except PdfExtractionError:
            raise
        except Exception as exc:
            raise PdfExtractionError(
                "OpenDataLoader could not inspect the benchmark document."
            ) from exc


PDFPLUMBER_ENGINE = PdfPlumberEngine()
