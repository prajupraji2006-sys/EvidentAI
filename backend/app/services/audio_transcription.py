"""Gemini-backed transcription of stored audio evidence."""

import os
from pathlib import Path

from google import genai

from app.config import require_gemini_api_key
from app.services.ai_analysis import GeminiServiceError


class AudioTranscriptionError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def transcribe_audio(audio_path: Path) -> str:
    """Transcribe supported audio through Gemini's audio transcription model."""
    api_key = require_gemini_api_key()
    client = None
    uploaded_file = None
    try:
        client = genai.Client(api_key=api_key)
        uploaded_file = client.files.upload(file=str(audio_path))
        interaction = client.interactions.create(
            model=os.getenv("GEMINI_AUDIO_MODEL", "gemini-3.5-transcribe"),
            input=[{
                "type": "audio",
                "uri": uploaded_file.uri,
                "mime_type": uploaded_file.mime_type,
            }],
        )
        transcript = (getattr(interaction, "output_text", None) or "").strip()
    except Exception:
        # SDK errors can include request details. Never return or log them here.
        raise GeminiServiceError(
            "Audio transcription is temporarily unavailable. Check the Gemini connection and try again."
        ) from None
    finally:
        if client is not None and uploaded_file is not None:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    if not transcript:
        raise AudioTranscriptionError(
            422,
            "No speech could be transcribed from this audio file.",
        )
    return transcript
