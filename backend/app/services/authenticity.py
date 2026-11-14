"""Conservative authenticity indicators based only on readable file metadata."""

from __future__ import annotations

import csv
import io
import wave
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader


DISCLAIMER = (
    "Automated assessment only. This result is not a legal determination "
    "of authenticity or fraud."
)


def assess_file(path: Path, file_type: str) -> dict[str, Any]:
    """Return observable metadata and limitations; never infer genuineness."""
    metadata: dict[str, Any] = {"file_type": file_type, "size_bytes": path.stat().st_size}
    signals: list[dict[str, str]] = []
    limitations: list[str] = []

    if file_type == "pdf":
        try:
            reader = PdfReader(str(path), strict=False)
            metadata.update({
                "page_count": len(reader.pages),
                "document_info": {
                    str(key).lstrip("/"): str(value)[:500]
                    for key, value in (reader.metadata or {}).items()
                    if value is not None
                },
                "encrypted": reader.is_encrypted,
            })
            limitations.append("Digital signature validity and incremental revision history were not verified.")
            if reader.metadata:
                signals.append({
                    "type": "metadata",
                    "severity": "informational",
                    "description": "PDF document metadata is present; metadata can be edited and does not prove provenance.",
                })
        except Exception:
            metadata["parse_status"] = "unreadable"
            limitations.append("PDF metadata could not be read by the available parser.")

    elif file_type == "image":
        try:
            with Image.open(path) as image:
                exif = image.getexif()
                metadata.update({
                    "format": image.format,
                    "width": image.width,
                    "height": image.height,
                    "exif_tag_count": len(exif),
                    "exif_tags": {str(key): str(value)[:300] for key, value in list(exif.items())[:40]},
                })
                if exif:
                    signals.append({
                        "type": "metadata",
                        "severity": "informational",
                        "description": "EXIF metadata is present; it may be absent or modified and is not proof of provenance.",
                    })
        except Exception:
            metadata["parse_status"] = "unreadable"
            limitations.append("Image metadata could not be read by the available parser.")
        limitations.append("No AI-image detector, C2PA validation, or pixel-level manipulation analysis was run.")

    elif file_type == "audio":
        if path.suffix.lower() == ".wav":
            try:
                with wave.open(str(path), "rb") as source:
                    metadata.update({
                        "codec_container": "WAV",
                        "channels": source.getnchannels(),
                        "sample_width_bytes": source.getsampwidth(),
                        "sample_rate_hz": source.getframerate(),
                        "duration_seconds": round(source.getnframes() / source.getframerate(), 3),
                        "frame_count": source.getnframes(),
                    })
            except (wave.Error, OSError, ZeroDivisionError):
                metadata["parse_status"] = "unreadable"
                limitations.append("WAV technical metadata could not be read.")
        else:
            limitations.append("Technical metadata extraction for MP3/M4A is not configured.")
        limitations.append("No voice-cloning or audio-manipulation detector was run.")

    elif file_type == "text":
        raw = path.read_bytes()[:2_000_000]
        text = raw.decode("utf-8-sig", errors="replace")
        lines = text.splitlines()
        metadata.update({
            "encoding": "utf-8 (replacement decoding used if needed)",
            "sampled_characters": len(text),
            "line_count": len(lines),
            "truncated_for_metadata": path.stat().st_size > len(raw),
        })
        if path.suffix.lower() == ".csv":
            try:
                rows = list(csv.reader(io.StringIO(text)))
                widths = [len(row) for row in rows[:10_000]]
                metadata["csv"] = {
                    "sampled_row_count": len(rows),
                    "header_width": widths[0] if widths else 0,
                    "inconsistent_row_widths": len(set(widths)) > 1,
                }
                if len(set(widths)) > 1:
                    signals.append({
                        "type": "structure",
                        "severity": "low",
                        "description": "CSV rows in the sampled content have inconsistent column counts; review the source format.",
                    })
            except csv.Error:
                metadata["csv_parse_status"] = "malformed"
                limitations.append("CSV structure could not be parsed reliably.")
        limitations.append("No reliable AI-text detector or source-provenance verification was run.")

    return {
        "classification": "INCONCLUSIVE",
        "confidence": 0.0,
        "signals": signals,
        "risk_flags": [],
        "provenance_information": {"storage_original_preserved": True},
        "metadata_analysis": metadata,
        "integrity_information": {"status": "not_checked_by_assessment"},
        "limitations": [DISCLAIMER, *limitations],
        "recommended_verification": [
            "Compare against the original source or device.",
            "Verify the creator or issuing organization through an independent channel.",
            "Review cryptographic signatures or content credentials with a qualified tool when available.",
        ],
    }
