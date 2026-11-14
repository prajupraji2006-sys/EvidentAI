"""Locate stored PDF evidence and extract its machine-readable text."""

import json
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader

from app.services.evidence_upload import SUPPORTED_EXTENSIONS, UPLOAD_DIR

MAX_PDF_TEXT_CHARS = 100_000


class PDFProcessingError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def locate_evidence_file(evidence_id: UUID) -> tuple[Path, str]:
    """Resolve a UUID to its stored file and original filename, if available."""
    matches = [
        UPLOAD_DIR / f"{evidence_id}{extension}"
        for extension in SUPPORTED_EXTENSIONS
        if (UPLOAD_DIR / f"{evidence_id}{extension}").is_file()
    ]
    if not matches:
        raise PDFProcessingError(404, "Evidence file was not found.")

    evidence_path = matches[0]
    if evidence_path.suffix.lower() != ".pdf":
        raise PDFProcessingError(415, "Evidence file is not a PDF.")

    original_filename = evidence_path.name
    metadata_path = UPLOAD_DIR / f"{evidence_id}.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        original_filename = metadata.get("original_filename") or original_filename
    except (OSError, json.JSONDecodeError, AttributeError):
        # Older uploads may not have a sidecar; the evidence remains processable.
        pass
    return evidence_path, original_filename


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF, returning a clear error for unreadable files."""
    try:
        reader = PdfReader(str(pdf_path), strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise PDFProcessingError(
                422,
                "PDF is encrypted and cannot be read without a password.",
            )

        pages_text = []
        extracted_length = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                extracted_length += len(page_text) + (1 if pages_text else 0)
                if extracted_length > MAX_PDF_TEXT_CHARS:
                    raise PDFProcessingError(
                        413,
                        f"Extracted PDF text exceeds the {MAX_PDF_TEXT_CHARS:,} character analysis limit.",
                    )
                pages_text.append(page_text)
        extracted_text = "\n".join(pages_text).strip()
    except PDFProcessingError:
        raise
    except Exception:
        # Parser exceptions may include internal paths or low-level file details.
        raise PDFProcessingError(
            422,
            "PDF is corrupted or unreadable. Upload a readable PDF and try again.",
        ) from None

    if not extracted_text:
        raise PDFProcessingError(
            422,
            "PDF contains no extractable text. Scanned PDFs require OCR, which is not enabled.",
        )
    return extracted_text
