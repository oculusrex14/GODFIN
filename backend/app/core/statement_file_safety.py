"""Cheap, fail-closed structural checks before financial document parsers run."""

from __future__ import annotations

import io
import re
import stat
import zipfile


MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_XLSX_ENTRIES = 1_000
MAX_XLSX_COMPRESSION_RATIO = 200
MAX_PDF_OBJECT_MARKERS = 50_000
MAX_PDF_EOF_SEARCH_BYTES = 8_192
_PDF_ACTIVE_CONTENT = re.compile(
    rb"/(?:JavaScript|JS|Launch|RichMedia|EmbeddedFile)(?=[\s/<>()\[\]])",
    re.IGNORECASE,
)
_XLSX_FORBIDDEN_PREFIXES = (
    "customui/",
    "xl/embeddings/",
    "xl/externallinks/",
    "xl/oleobjects/",
)


class UnsafeStatementFile(ValueError):
    """The supplied file structure is unsafe or inconsistent with its format."""


def validate_pdf_structure(contents: bytes) -> None:
    if not contents.startswith(b"%PDF-"):
        raise UnsafeStatementFile("The file is not a PDF document.")
    if b"%%EOF" not in contents[-MAX_PDF_EOF_SEARCH_BYTES:]:
        raise UnsafeStatementFile("The PDF document is incomplete.")
    if contents.count(b" obj") > MAX_PDF_OBJECT_MARKERS:
        raise UnsafeStatementFile("The PDF document is structurally excessive.")
    if _PDF_ACTIVE_CONTENT.search(contents):
        raise UnsafeStatementFile(
            "PDFs containing scripts, launches, attachments, or rich media are not supported."
        )


def validate_xlsx_archive(contents: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_XLSX_ENTRIES:
                raise UnsafeStatementFile("The XLSX workbook contains too many files.")
            names = {entry.filename.replace("\\", "/").lower() for entry in entries}
            if "[content_types].xml" not in names or "xl/workbook.xml" not in names:
                raise UnsafeStatementFile("The file is not a complete XLSX workbook.")
            total_uncompressed = 0
            for entry in entries:
                if entry.flag_bits & 0x1:
                    raise UnsafeStatementFile("Encrypted XLSX workbooks are not supported.")
                path = entry.filename.replace("\\", "/")
                normalized = path.lower()
                if path.startswith("/") or ".." in path.split("/"):
                    raise UnsafeStatementFile("The XLSX workbook contains an unsafe path.")
                file_type = (entry.external_attr >> 16) & 0o170000
                if file_type == stat.S_IFLNK:
                    raise UnsafeStatementFile("The XLSX workbook contains a symbolic link.")
                if normalized.endswith("vbaproject.bin") or normalized.startswith(
                    _XLSX_FORBIDDEN_PREFIXES
                ):
                    raise UnsafeStatementFile(
                        "XLSX workbooks with macros, external links, or embedded objects are not supported."
                    )
                total_uncompressed += entry.file_size
                if total_uncompressed > MAX_XLSX_UNCOMPRESSED_BYTES:
                    raise UnsafeStatementFile(
                        "The XLSX workbook expands beyond the safe 100 MB limit."
                    )
                if (
                    entry.compress_size > 0
                    and entry.file_size / entry.compress_size
                    > MAX_XLSX_COMPRESSION_RATIO
                ):
                    raise UnsafeStatementFile(
                        "The XLSX workbook has an unsafe compression ratio."
                    )
                if normalized.endswith(".rels") and entry.file_size <= 1024 * 1024:
                    relationship_xml = archive.read(entry)
                    if re.search(
                        rb"TargetMode\s*=\s*['\"]External['\"]",
                        relationship_xml,
                        re.IGNORECASE,
                    ):
                        raise UnsafeStatementFile(
                            "XLSX workbooks with external links are not supported."
                        )
    except UnsafeStatementFile:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise UnsafeStatementFile("The XLSX workbook is not a valid XLSX file.") from exc


def validate_statement_file(contents: bytes, file_format: str) -> None:
    if file_format == "pdf":
        validate_pdf_structure(contents)
    elif file_format == "xlsx":
        validate_xlsx_archive(contents)
    elif file_format == "xls":
        if not contents.startswith(b"\xd0\xcf\x11\xe0"):
            raise UnsafeStatementFile("The file is not a legacy XLS workbook.")
    else:
        raise UnsafeStatementFile("The statement file type is not supported.")
