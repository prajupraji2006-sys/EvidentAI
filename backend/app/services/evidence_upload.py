"""Supabase-backed evidence upload and integrity management."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.supabase_client import get_supabase_client


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

STORAGE_BUCKET = "evidence-files"
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB

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

UPLOAD_DIR = (
    Path(__file__).resolve().parents[2] / "uploads"
)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------

class EvidenceUploadError(Exception):
    """Expected evidence upload failure."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------
# Response model data
# ---------------------------------------------------------------------

@dataclass
class EvidenceUploadResult:
    evidence_id: uuid.UUID
    original_filename: str
    file_type: str
    file_size: int
    sha256_hash: str
    upload_status: str
    uploaded_at: datetime
    exact_duplicate: bool = False
    duplicate_of: str | None = None


# ---------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------

def _safe_filename(filename: str | None) -> str:
    """Return a safe filename for metadata purposes."""

    if not filename:
        return "evidence"

    # Treat both Windows and POSIX separators as path separators, regardless
    # of which platform is running the API.
    name = filename.replace("\\", "/").split("/")[-1].strip()
    name = "".join(character for character in name if character.isprintable())

    if not name:
        return "evidence"

    return name


def _detect_file_type(filename: str) -> str:
    """Determine supported evidence type from extension."""

    extension = Path(filename).suffix.lower()

    file_type = SUPPORTED_EXTENSIONS.get(extension)

    if not file_type:
        supported = ", ".join(SUPPORTED_EXTENSIONS.keys())

        raise EvidenceUploadError(
            415,
            (
                "Unsupported evidence format. "
                f"Supported formats: {supported}"
            ),
        )

    return file_type


def _detect_mime_type(filename: str) -> str:
    """Return a MIME type for storage metadata."""

    extension = Path(filename).suffix.lower()

    known_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
    }

    return known_types.get(
        extension,
        mimetypes.guess_type(filename)[0] or "application/octet-stream",
    )


def _sha256_file(file_path: Path) -> str:
    """Calculate SHA-256 for a local file."""

    digest = hashlib.sha256()

    with file_path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def calculate_sha256(file_path: Path) -> str:
    """Backward-compatible public name used by the API layer."""
    return _sha256_file(file_path)


def _validate_file_content(path: Path, extension: str) -> None:
    """Reject obvious extension/MIME mismatches without transforming bytes."""
    with path.open("rb") as source:
        head = source.read(1024)
    valid = {
        ".pdf": b"%PDF-" in head[:1024],
        ".jpg": head.startswith(b"\xff\xd8\xff"),
        ".jpeg": head.startswith(b"\xff\xd8\xff"),
        ".png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        ".wav": len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE",
        ".mp3": head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0),
        ".m4a": len(head) >= 8 and head[4:8] == b"ftyp",
    }
    if extension in valid and not valid[extension]:
        raise EvidenceUploadError(415, "The file contents do not match the selected file extension.")
    if extension in {".txt", ".csv"}:
        try:
            with path.open("r", encoding="utf-8-sig") as source:
                source.read(64 * 1024)
        except UnicodeDecodeError:
            raise EvidenceUploadError(415, "Text and CSV files must use UTF-8 encoding.") from None


def _validate_declared_mime(upload: UploadFile, extension: str) -> None:
    """Reject a declared MIME type that conflicts with the supported extension."""
    declared = (upload.content_type or "").split(";", 1)[0].strip().lower()
    if not declared or declared == "application/octet-stream":
        return
    accepted = {
        ".pdf": {"application/pdf", "application/x-pdf"},
        ".jpg": {"image/jpeg"},
        ".jpeg": {"image/jpeg"},
        ".png": {"image/png"},
        ".txt": {"text/plain"},
        ".csv": {"text/csv", "text/plain", "application/vnd.ms-excel"},
        ".mp3": {"audio/mpeg", "audio/mp3", "audio/x-mpeg"},
        ".wav": {"audio/wav", "audio/wave", "audio/x-wav", "audio/vnd.wave"},
        ".m4a": {"audio/mp4", "audio/x-m4a", "video/mp4", "application/mp4"},
    }
    if extension in accepted and declared not in accepted[extension]:
        raise EvidenceUploadError(415, "The declared MIME type does not match the selected evidence format.")


def _copy_upload_to_temp(upload: UploadFile, destination: Path) -> int:
    """Stream an uploaded file to disk while enforcing the size limit."""

    total_size = 0

    try:
        with destination.open("wb") as target:

            while True:
                chunk = upload.file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise EvidenceUploadError(
                        413,
                        "Evidence file exceeds the 200 MB size limit.",
                    )

                target.write(chunk)

    finally:
        try:
            upload.file.close()
        except Exception:
            pass

    if total_size == 0:
        raise EvidenceUploadError(
            422,
            "The uploaded evidence file is empty.",
        )

    return total_size


def _storage_path(
    uploaded_by: str,
    incident_id: uuid.UUID,
    evidence_id: uuid.UUID,
    extension: str,
) -> str:
    """Build a private Storage path."""

    return (
        f"{uploaded_by}/"
        f"{incident_id}/"
        f"{evidence_id}"
        f"{extension}"
    )


def _owned_incident_ids(client: Any, user_id: str) -> list[str]:
    rows = client.table("incidents").select("id").eq(
        "owner_id", str(user_id)
    ).execute().data or []
    return [str(row["id"]) for row in rows if row.get("id")]


def _incident_is_owned(client: Any, incident_id: str, user_id: str) -> bool:
    rows = client.table("incidents").select("id").eq(
        "id", str(incident_id)
    ).eq("owner_id", str(user_id)).limit(1).execute().data or []
    return bool(rows)


def _find_exact_duplicate(client: Any, uploader_id: str, sha256_hash: str) -> str | None:
    """Find an exact hash duplicate only among the uploader's own records."""
    incident_ids = _owned_incident_ids(client, uploader_id)
    if not incident_ids:
        return None
    evidence_rows = client.table("evidence").select("id").eq(
        "uploaded_by", str(uploader_id)
    ).in_("incident_id", incident_ids).execute().data or []
    evidence_ids = [str(row["id"]) for row in evidence_rows if row.get("id")]
    if not evidence_ids:
        return None
    hash_rows = client.table("evidence_hashes").select("evidence_id").eq(
        "sha256_hash", sha256_hash
    ).in_("evidence_id", evidence_ids).limit(1).execute().data or []
    return str(hash_rows[0]["evidence_id"]) if hash_rows else None


def _delete_storage_file(client: Any, storage_path: str) -> None:
    """Best-effort Storage cleanup."""

    try:
        client.storage.from_(STORAGE_BUCKET).remove(
            [storage_path]
        )
    except Exception:
        # Cleanup failure should never hide the original error.
        pass


def _delete_evidence_row(
    client: Any,
    evidence_id: uuid.UUID,
) -> None:
    """Best-effort evidence row cleanup."""

    try:
        client.table("evidence").delete().eq(
            "id",
            str(evidence_id),
        ).execute()
    except Exception:
        pass


def _delete_hash_row(
    client: Any,
    evidence_id: uuid.UUID,
) -> None:
    """Best-effort evidence hash cleanup."""

    try:
        client.table("evidence_hashes").delete().eq(
            "evidence_id",
            str(evidence_id),
        ).execute()
    except Exception:
        pass


# ---------------------------------------------------------------------
# Main upload function
# ---------------------------------------------------------------------

def save_evidence_file(
    upload: UploadFile,
    incident_id: uuid.UUID,
    uploader_id: str,
) -> EvidenceUploadResult:

    client = get_supabase_client()

    original_filename = _safe_filename(upload.filename)

    file_type = _detect_file_type(original_filename)

    mime_type = _detect_mime_type(original_filename)

    extension = Path(original_filename).suffix.lower()
    _validate_declared_mime(upload, extension)

    evidence_id = uuid.uuid4()

    temp_file: Path | None = None

    storage_path: str | None = None

    evidence_inserted = False

    hash_inserted = False

    try:

        # -------------------------------------------------------------
        # 1. Verify incident
        # -------------------------------------------------------------

        incident_response = (
            client.table("incidents")
            .select("id, owner_id, status")
            .eq("id", str(incident_id))
            .eq("owner_id", str(uploader_id))
            .limit(1)
            .execute()
        )

        incident_rows = incident_response.data or []

        if not incident_rows:
            raise EvidenceUploadError(
                404,
                "The specified incident was not found.",
            )

        incident = incident_rows[0]

        if incident.get("status") != "active":
            raise EvidenceUploadError(
                409,
                "Evidence can only be uploaded to an active incident.",
            )

        uploaded_by = str(uploader_id)

        if not uploaded_by:
            raise EvidenceUploadError(
                500,
                "The incident does not have a valid owner.",
            )

        # -------------------------------------------------------------
        # 2. Create temporary local file
        # -------------------------------------------------------------

        descriptor, temp_name = tempfile.mkstemp(prefix="evidentai-", suffix=extension)
        os.close(descriptor)
        temp_file = Path(temp_name)

        file_size = _copy_upload_to_temp(
            upload,
            temp_file,
        )
        _validate_file_content(temp_file, extension)

        # -------------------------------------------------------------
        # 3. Generate SHA-256
        # -------------------------------------------------------------

        sha256_hash = _sha256_file(temp_file)

        # Exact duplicate detection is limited to this authenticated user's
        # existing evidence. Duplicate uploads are preserved as new records.
        duplicate_of = _find_exact_duplicate(client, uploaded_by, sha256_hash)

        # -------------------------------------------------------------
        # 4. Upload original file to private Supabase Storage
        # -------------------------------------------------------------

        storage_path = _storage_path(
            uploaded_by=str(uploaded_by),
            incident_id=incident_id,
            evidence_id=evidence_id,
            extension=extension,
        )

        with temp_file.open("rb") as source:

            file_bytes = source.read()

        storage_response = (
            client.storage
            .from_(STORAGE_BUCKET)
            .upload(
                storage_path,
                file_bytes,
                {
                    "content-type": mime_type,
                    "upsert": False,
                },
            )
        )

        if storage_response is None:
            raise EvidenceUploadError(
                500,
                "Supabase Storage did not confirm the upload.",
            )

        # -------------------------------------------------------------
        # 5. Insert evidence metadata
        # -------------------------------------------------------------

        uploaded_at = datetime.now(timezone.utc)

        evidence_row = {
            "id": str(evidence_id),
            "incident_id": str(incident_id),
            "uploaded_by": str(uploaded_by),
            "original_filename": original_filename,
            "mime_type": mime_type,
            "file_size": file_size,
            "storage_path": storage_path,
            "evidence_type": file_type,
            "processing_status": "uploaded",
            "analysis_status": "pending",
            "processing_error": None,
            "uploaded_at": uploaded_at.isoformat(),
            "duplicate_of": duplicate_of,
        }

        evidence_response = (
            client.table("evidence")
            .insert(evidence_row)
            .execute()
        )

        if not evidence_response.data:
            raise EvidenceUploadError(
                500,
                "Evidence metadata could not be saved.",
            )

        evidence_inserted = True

        # -------------------------------------------------------------
        # 6. Insert SHA-256 integrity record
        # -------------------------------------------------------------

        hash_row = {
            "id": str(uuid.uuid4()),
            "evidence_id": str(evidence_id),
            "sha256_hash": sha256_hash,
            "hash_algorithm": "SHA-256",
            "generated_at": uploaded_at.isoformat(),
            "verified_at": None,
            "verification_status": "generated",
        }

        hash_response = (
            client.table("evidence_hashes")
            .insert(hash_row)
            .execute()
        )

        if not hash_response.data:
            raise EvidenceUploadError(
                500,
                "Evidence integrity hash could not be saved.",
            )

        hash_inserted = True

        # -------------------------------------------------------------
        # 7. Success
        # -------------------------------------------------------------

        return EvidenceUploadResult(
            evidence_id=evidence_id,
            original_filename=original_filename,
            file_type=file_type,
            file_size=file_size,
            sha256_hash=sha256_hash,
            upload_status="uploaded",
            uploaded_at=uploaded_at,
            exact_duplicate=duplicate_of is not None,
            duplicate_of=duplicate_of,
        )

    except EvidenceUploadError:
        if hash_inserted:
            _delete_hash_row(client, evidence_id)
        if evidence_inserted:
            _delete_evidence_row(client, evidence_id)
        if storage_path:
            _delete_storage_file(client, storage_path)
        raise

    except Exception as exc:

        # -------------------------------------------------------------
        # Roll back anything already created
        # -------------------------------------------------------------

        if hash_inserted:
            _delete_hash_row(
                client,
                evidence_id,
            )

        if evidence_inserted:
            _delete_evidence_row(
                client,
                evidence_id,
            )

        if storage_path:
            _delete_storage_file(
                client,
                storage_path,
            )

        logger.error("Evidence upload failed (error_type=%s)", type(exc).__name__)

        raise EvidenceUploadError(
            500,
            "Evidence upload failed. Check the backend logs for details.",
        ) from None

    finally:

        # -------------------------------------------------------------
        # 8. Remove local temporary file
        # -------------------------------------------------------------

        if temp_file and temp_file.exists():

            try:
                temp_file.unlink()
            except Exception:
                pass


# ---------------------------------------------------------------------
# Evidence listing
# ---------------------------------------------------------------------

def list_evidence_records(user_id: str) -> list[dict[str, Any]]:
    """Return evidence records with their SHA-256 hashes."""

    client = get_supabase_client()
    incident_ids = _owned_incident_ids(client, user_id)
    if not incident_ids:
        return []

    evidence_response = (
        client.table("evidence")
        .select("*")
        .eq("uploaded_by", str(user_id))
        .in_("incident_id", incident_ids)
        .order("uploaded_at", desc=True)
        .execute()
    )

    evidence_rows = evidence_response.data or []

    evidence_ids = [str(row["id"]) for row in evidence_rows if row.get("id")]
    hash_rows = []
    analysis_rows = []
    authenticity_rows = []
    if evidence_ids:
        hash_rows = client.table("evidence_hashes").select(
            "evidence_id,sha256_hash,hash_algorithm,generated_at,verified_at,verification_status"
        ).in_("evidence_id", evidence_ids).execute().data or []
        analysis_rows = client.table("evidence_analysis").select(
            "evidence_id,analysis,extracted_text_preview,extraction_method,created_at"
        ).in_("evidence_id", evidence_ids).execute().data or []
        authenticity_rows = client.table("authenticity_assessments").select(
            "evidence_id,classification,confidence,assessment,created_at"
        ).in_("evidence_id", evidence_ids).order("created_at", desc=True).execute().data or []

    hash_map = {
        str(row["evidence_id"]): row
        for row in hash_rows
        if row.get("evidence_id")
    }
    analysis_map = {str(row["evidence_id"]): row for row in analysis_rows if row.get("evidence_id")}
    authenticity_map: dict[str, dict[str, Any]] = {}
    for row in authenticity_rows:
        if row.get("evidence_id"):
            authenticity_map.setdefault(str(row["evidence_id"]), row)

    result: list[dict[str, Any]] = []

    for evidence in evidence_rows:

        evidence_id = str(evidence["id"])

        hash_record = hash_map.get(evidence_id)
        analysis_record = analysis_map.get(evidence_id)
        authenticity_record = authenticity_map.get(evidence_id)

        result.append(
            {
                **evidence,
                "sha256_hash": (
                    hash_record.get("sha256_hash")
                    if hash_record
                    else None
                ),
                "hash_algorithm": (
                    hash_record.get("hash_algorithm")
                    if hash_record
                    else None
                ),
                "verification_status": (
                    hash_record.get("verification_status")
                    if hash_record
                    else None
                ),
                "evidence_id": evidence_id,
                "file_type": evidence.get("evidence_type"),
                "extraction_status": evidence.get("processing_status"),
                "analysis": analysis_record.get("analysis") if analysis_record else None,
                "extracted_text_preview": analysis_record.get("extracted_text_preview") if analysis_record else None,
                "authenticity_assessment": authenticity_record.get("assessment") if authenticity_record else None,
                "authenticity_classification": authenticity_record.get("classification") if authenticity_record else None,
            }
        )

    return result


# ---------------------------------------------------------------------
# Evidence metadata
# ---------------------------------------------------------------------

def read_evidence_metadata(
    evidence_id: uuid.UUID,
    user_id: str,
) -> dict[str, Any] | None:

    client = get_supabase_client()

    response = (
        client.table("evidence")
        .select("*")
        .eq("id", str(evidence_id))
        .eq("uploaded_by", str(user_id))
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        return None

    evidence = rows[0]
    if not _incident_is_owned(client, str(evidence.get("incident_id", "")), user_id):
        return None
    return evidence


# ---------------------------------------------------------------------
# Local file retrieval
# ---------------------------------------------------------------------

def find_stored_file(
    evidence_id: uuid.UUID,
    user_id: str,
) -> Path:

    client = get_supabase_client()

    evidence = read_evidence_metadata(evidence_id, user_id)

    if not evidence:
        raise EvidenceUploadError(
            404,
            "Evidence was not found.",
        )

    storage_path = evidence.get("storage_path")

    if not storage_path:
        raise EvidenceUploadError(
            500,
            "Evidence does not have a storage path.",
        )

    extension = Path(str(evidence.get("original_filename") or "evidence")).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise EvidenceUploadError(415, "Stored evidence has an unsupported file extension.")
    descriptor, cache_name = tempfile.mkstemp(prefix="evidentai-fetch-", suffix=extension)
    os.close(descriptor)
    cache_path = Path(cache_name)

    try:

        file_bytes = (
            client.storage
            .from_(STORAGE_BUCKET)
            .download(storage_path)
        )

    except Exception:

        cache_path.unlink(missing_ok=True)
        raise EvidenceUploadError(404, "The original evidence file could not be retrieved.") from None

    try:

        with cache_path.open("wb") as destination:
            destination.write(file_bytes)

    except Exception:

        raise EvidenceUploadError(
            500,
            "The evidence file could not be cached locally.",
        ) from None

    return cache_path


# ---------------------------------------------------------------------
# Analysis status
# ---------------------------------------------------------------------

def set_processing_status(
    evidence_id: uuid.UUID,
    user_id: str,
    processing_status: str,
    processing_error: str | None = None,
) -> dict[str, Any]:

    client = get_supabase_client()

    analysis_status = {
        "uploaded": "pending",
        "processing": "processing",
        "processed": "completed",
        "failed": "failed",
    }.get(processing_status, "pending")
    update_data = {
        "processing_status": processing_status,
        "analysis_status": analysis_status,
        "processing_error": processing_error,
    }
    if processing_status in {"processed", "failed"}:
        update_data["processed_at"] = datetime.now(timezone.utc).isoformat()

    response = (
        client.table("evidence")
        .update(update_data)
        .eq("id", str(evidence_id))
        .eq("uploaded_by", str(user_id))
        .execute()
    )

    rows = response.data or []

    if not rows:
        raise EvidenceUploadError(
            404,
            "Evidence was not found while saving the processing result.",
        )

    return rows[0]


def save_analysis_result(
    evidence_id: uuid.UUID,
    user_id: str,
    analysis: dict[str, Any],
    preview: str,
    extraction_method: str,
) -> None:
    """Persist analysis separately from the immutable original file."""
    client = get_supabase_client()
    evidence = read_evidence_metadata(evidence_id, user_id)
    if evidence is None:
        raise EvidenceUploadError(404, "Evidence was not found.")
    client.table("evidence_analysis").upsert(
        {
            "evidence_id": str(evidence_id),
            "analysis": analysis,
            "extracted_text_preview": preview,
            "extraction_method": extraction_method,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="evidence_id",
    ).execute()
    set_processing_status(evidence_id, user_id, "processed")


# ---------------------------------------------------------------------
# Integrity verification
# ---------------------------------------------------------------------

def verify_evidence_integrity(
    evidence_id: uuid.UUID,
    user_id: str,
) -> dict[str, Any]:

    client = get_supabase_client()

    evidence_response = (
        client.table("evidence")
        .select("*")
        .eq("id", str(evidence_id))
        .eq("uploaded_by", str(user_id))
        .limit(1)
        .execute()
    )

    evidence_rows = evidence_response.data or []

    if not evidence_rows:
        raise EvidenceUploadError(
            404,
            "Evidence was not found.",
        )

    evidence = evidence_rows[0]
    if not _incident_is_owned(client, str(evidence.get("incident_id", "")), user_id):
        raise EvidenceUploadError(404, "Evidence was not found.")

    hash_response = (
        client.table("evidence_hashes")
        .select("*")
        .eq("evidence_id", str(evidence_id))
        .limit(1)
        .execute()
    )

    hash_rows = hash_response.data or []

    if not hash_rows:
        raise EvidenceUploadError(
            404,
            "Integrity hash was not found for this evidence.",
        )

    hash_record = hash_rows[0]

    stored_file = find_stored_file(evidence_id, user_id)

    try:
        current_hash = _sha256_file(stored_file)
    finally:
        stored_file.unlink(missing_ok=True)

    original_hash = hash_record.get("sha256_hash")

    verified = (
        current_hash.lower()
        == str(original_hash).lower()
    )

    verification_status = (
        "verified"
        if verified
        else "failed"
    )

    verification_time = datetime.now(
        timezone.utc
    ).isoformat()

    (
        client.table("evidence_hashes")
        .update(
            {
                "verified_at": verification_time,
                "verification_status": verification_status,
            }
        )
        .eq(
            "evidence_id",
            str(evidence_id),
        )
        .execute()
    )

    try:
        stored_file.unlink()
    except Exception:
        pass

    return {
        "evidence_id": str(evidence_id),
        "algorithm": "SHA-256",
        "original_hash": original_hash,
        "current_hash": current_hash,
        "verified": verified,
        "verification_status": verification_status,
        "verified_at": verification_time,
    }
