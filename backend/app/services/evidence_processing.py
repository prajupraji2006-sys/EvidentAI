"""Dispatch supported evidence to a type-specific text extraction service."""

from pathlib import Path

from app.services.audio_transcription import AudioTranscriptionError, transcribe_audio
from app.services.image_ocr import ImageOCRError, extract_image_text
from app.services.pdf_extraction import PDFProcessingError, extract_pdf_text


MAX_ANALYSIS_TEXT_CHARS = 100_000


class EvidenceTextError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def extract_evidence_text(file_path: Path, file_type: str) -> tuple[str, str]:
    """Return extracted content and the extraction method used."""
    extension = file_path.suffix.lower()
    try:
        if file_type == "pdf":
            return extract_pdf_text(file_path), "pdf_text_extraction"
        if file_type == "image":
            return extract_image_text(file_path), "ocr"
        if file_type == "audio":
            return transcribe_audio(file_path), "gemini_audio_transcription"
        if file_type == "text" and extension in {".txt", ".csv"}:
            try:
                with file_path.open("r", encoding="utf-8-sig") as source:
                    text = source.read(MAX_ANALYSIS_TEXT_CHARS + 1)
            except UnicodeDecodeError:
                raise EvidenceTextError(
                    422,
                    "Text evidence is not valid UTF-8. Save it as UTF-8 and upload again.",
                ) from None
            if len(text) > MAX_ANALYSIS_TEXT_CHARS:
                raise EvidenceTextError(
                    413,
                    f"Extracted text exceeds the {MAX_ANALYSIS_TEXT_CHARS:,} character analysis limit.",
                )
            if not text.strip():
                raise EvidenceTextError(422, "Text file contains no extractable text.")
            return text.strip(), "text_file"
    except PDFProcessingError as exc:
        raise EvidenceTextError(exc.status_code, str(exc)) from None
    except (ImageOCRError, AudioTranscriptionError) as exc:
        raise EvidenceTextError(exc.status_code, str(exc)) from None

    raise EvidenceTextError(415, "This evidence type cannot be analyzed.")
