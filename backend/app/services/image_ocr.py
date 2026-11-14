"""Optional local OCR for uploaded evidence images."""

from pathlib import Path


class ImageOCRError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def extract_image_text(image_path: Path) -> str:
    try:
        from PIL import Image, UnidentifiedImageError
        import pytesseract
    except ImportError:
        raise ImageOCRError(
            503,
            "Image OCR dependencies are unavailable. Install backend requirements and Tesseract OCR.",
        ) from None

    try:
        with Image.open(image_path) as image:
            image.load()
            text = pytesseract.image_to_string(image.convert("RGB")).strip()
    except pytesseract.TesseractNotFoundError:
        raise ImageOCRError(
            503,
            "Tesseract OCR is not installed or not on PATH. Install it and restart the backend.",
        ) from None
    except UnidentifiedImageError:
        raise ImageOCRError(422, "Image file is corrupted or unreadable.") from None
    except Exception:
        raise ImageOCRError(422, "Image OCR could not read this file.") from None

    if not text:
        raise ImageOCRError(422, "No readable text was found in the image.")
    return text
