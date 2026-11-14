"""Temporary evidence upload validation and integrity hashing."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import UploadFile
from pydantic import BaseModel


UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
MAX_FILE_SIZE = 200 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".txt": "text",
    ".csv": "text",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
}


class EvidenceUploadError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class EvidenceUploadResult(BaseModel):
    evidence_id: UUID
    original_filename: str
    file_type: Literal["pdf", "image", "text", "audio"]
    file_size: int  # bytes
    sha256_hash: str
    upload_status: Literal["uploaded"]
    uploaded_at: datetime


def _remove_partial_file(path: Path | None) -> None:
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def find_stored_file(evidence_id: UUID) -> Path | None:
    for extension in SUPPORTED_EXTENSIONS:
        path = UPLOAD_DIR / f"{evidence_id}{extension}"
        if path.is_file():
            return path
    return None


def read_evidence_metadata(evidence_id: UUID) -> dict:
    metadata_path = UPLOAD_DIR / f"{evidence_id}.json"
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_evidence_metadata(evidence_id: UUID, metadata: dict) -> None:
    metadata_path = UPLOAD_DIR / f"{evidence_id}.json"
    temporary_path = UPLOAD_DIR / f"{evidence_id}.json.tmp"
    temporary_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(metadata_path)


def list_evidence_records() -> list[dict]:
    records = []
    for metadata_path in UPLOAD_DIR.glob("*.json"):
        try:
            evidence_id = UUID(metadata_path.stem)
        except ValueError:
            continue
        file_path = find_stored_file(evidence_id)
        if file_path is None:
            continue
        metadata = read_evidence_metadata(evidence_id)
        records.append({
            "evidence_id": str(evidence_id),
            "original_filename": metadata.get("original_filename", file_path.name),
            "file_type": metadata.get("file_type", SUPPORTED_EXTENSIONS[file_path.suffix.lower()]),
            "file_size": metadata.get("file_size", file_path.stat().st_size),
            "sha256_hash": metadata.get("sha256_hash"),
            "upload_status": "uploaded",
            "uploaded_at": metadata.get("uploaded_at"),
            "analysis": metadata.get("analysis"),
            "extraction_status": metadata.get("extraction_status"),
        })
    records.sort(key=lambda record: record.get("uploaded_at") or "", reverse=True)
    return records


def save_analysis_result(evidence_id: UUID, analysis: dict, preview: str) -> None:
    metadata = read_evidence_metadata(evidence_id)
    metadata["analysis"] = analysis
    metadata["extracted_text_preview"] = preview
    metadata["extraction_status"] = "completed"
    write_evidence_metadata(evidence_id, metadata)


def calculate_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as evidence_file:
        while chunk := evidence_file.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def save_evidence_file(upload: UploadFile) -> EvidenceUploadResult:
    """Validate and stream one upload to backend/uploads while hashing it."""
    original_filename = upload.filename or ""
    extension = Path(original_filename).suffix.lower()
    file_type = SUPPORTED_EXTENSIONS.get(extension)

    if not original_filename.strip():
        raise EvidenceUploadError(400, "A filename is required.")
    if file_type is None:
        allowed = ", ".join(SUPPORTED_EXTENSIONS)
        raise EvidenceUploadError(
            415,
            f"Unsupported file type. Allowed extensions: {allowed}.",
        )

    evidence_id = uuid4()
    destination = UPLOAD_DIR / f"{evidence_id}{extension}"
    metadata_destination = UPLOAD_DIR / f"{evidence_id}.json"
    digest = hashlib.sha256()
    file_size = 0

    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stored_file:
            while chunk := upload.file.read(CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise EvidenceUploadError(
                        413,
                        "File exceeds the maximum allowed size of 200 MB.",
                    )
                digest.update(chunk)
                stored_file.write(chunk)

        if file_size == 0:
            raise EvidenceUploadError(400, "Uploaded file is empty.")
    except EvidenceUploadError:
        _remove_partial_file(destination)
        raise
    except OSError:
        _remove_partial_file(destination)
        raise EvidenceUploadError(
            500,
            "The uploaded file could not be stored. Please try again.",
        ) from None

    uploaded_at = datetime.now(timezone.utc)
    result = EvidenceUploadResult(
        evidence_id=evidence_id,
        original_filename=original_filename,
        file_type=file_type,
        file_size=file_size,
        sha256_hash=digest.hexdigest(),
        upload_status="uploaded",
        uploaded_at=uploaded_at,
    )
    try:
        metadata_destination.write_text(
            json.dumps(
                {
                    "original_filename": original_filename,
                    "file_type": file_type,
                    "file_size": file_size,
                    "sha256_hash": digest.hexdigest(),
                    "uploaded_at": uploaded_at.isoformat(),
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        _remove_partial_file(destination)
        _remove_partial_file(metadata_destination)
        raise EvidenceUploadError(
            500,
            "Upload metadata could not be stored. Please try again.",
        ) from None

    return result
