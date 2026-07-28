"""
PDF Extraction Service
Handles PDF file processing, including password-protected PDFs
"""
from __future__ import annotations

import io
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Lazy import pdfplumber to avoid startup issues
_pdfplumber = None

def get_pdfplumber():
    global _pdfplumber
    if _pdfplumber is None:
        import pdfplumber
        _pdfplumber = pdfplumber
    return _pdfplumber


class PDFExtractionError(Exception):
    """Raised when PDF extraction fails"""
    pass


class PDFPasswordError(Exception):
    """Raised when PDF requires a password or password is incorrect"""
    pass


def extract_text_from_pdf(
    file_content: bytes,
    password: Optional[str] = None,
) -> Tuple[str, dict]:
    """
    Extract text content from a PDF file

    Args:
        file_content: Raw PDF file bytes
        password: Optional password for encrypted PDFs

    Returns:
        Tuple of (extracted_text, metadata_dict)

    Raises:
        PDFPasswordError: If PDF is encrypted and password is missing/incorrect
        PDFExtractionError: If extraction fails for other reasons
    """
    pdfplumber = get_pdfplumber()

    try:
        # Open PDF from bytes
        pdf_file = io.BytesIO(file_content)

        with pdfplumber.open(pdf_file, password=password or '') as pdf:
            # Extract metadata
            metadata = {
                'num_pages': len(pdf.pages),
                'pdf_version': getattr(pdf, 'pdf_version', None),
            }

            # Try to get PDF metadata
            if hasattr(pdf, 'metadata') and pdf.metadata:
                metadata.update({
                    'title': pdf.metadata.get('title', ''),
                    'author': pdf.metadata.get('author', ''),
                    'creator': pdf.metadata.get('creator', ''),
                    'producer': pdf.metadata.get('producer', ''),
                })

            # Extract text from all pages
            all_text = []
            for i, page in enumerate(pdf.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        all_text.append(page_text)
                except Exception as e:
                    logger.warning(f"Error extracting text from page {i+1}: {e}")
                    continue

            combined_text = '\n\n'.join(all_text)
            logger.info(f"Extracted {len(combined_text)} characters from {metadata['num_pages']} pages")

            return combined_text, metadata

    except Exception as e:
        error_msg = str(e).lower()

        # Check for password-related errors
        if 'password' in error_msg or 'encrypt' in error_msg or 'decrypt' in error_msg:
            raise PDFPasswordError(
                "PDF is password-protected. Please provide the correct password."
            ) from e

        # Check for corrupted/invalid PDF
        if 'not a pdf' in error_msg or 'eof marker' in error_msg or 'trailer' in error_msg:
            raise PDFExtractionError(
                "Invalid or corrupted PDF file."
            ) from e

        # Generic error
        raise PDFExtractionError(f"Failed to extract text from PDF: {e}") from e


def validate_pdf(file_content: bytes) -> bool:
    """
    Validate that the file content is a valid PDF

    Args:
        file_content: Raw file bytes

    Returns:
        True if valid PDF, False otherwise
    """
    # Check PDF header
    if not file_content.startswith(b'%PDF-'):
        return False

    # Check for EOF marker (PDFs should end with %%EOF)
    if b'%%EOF' not in file_content[-1024:]:
        return False

    return True


def get_pdf_page_count(file_content: bytes, password: Optional[str] = None) -> int:
    """
    Get the number of pages in a PDF

    Args:
        file_content: Raw PDF file bytes
        password: Optional password for encrypted PDFs

    Returns:
        Number of pages
    """
    pdfplumber = get_pdfplumber()

    try:
        pdf_file = io.BytesIO(file_content)
        with pdfplumber.open(pdf_file, password=password or '') as pdf:
            return len(pdf.pages)
    except Exception:
        return 0


def extract_tables_from_pdf(
    file_content: bytes,
    password: Optional[str] = None,
) -> list:
    """
    Extract tables from a PDF file

    Args:
        file_content: Raw PDF file bytes
        password: Optional password for encrypted PDFs

    Returns:
        List of tables (each table is a list of rows)
    """
    pdfplumber = get_pdfplumber()

    try:
        pdf_file = io.BytesIO(file_content)
        all_tables = []

        with pdfplumber.open(pdf_file, password=password or '') as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if tables:
                    all_tables.extend(tables)

        return all_tables

    except Exception as e:
        logger.error(f"Failed to extract tables from PDF: {e}")
        return []