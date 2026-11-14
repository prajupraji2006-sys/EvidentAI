"""Backend-only environment configuration for external AI services."""

import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=BACKEND_ENV_FILE, override=False)


def require_gemini_api_key() -> str:
    """Return the configured Gemini key or raise a safe, actionable error."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Add it to backend/.env "
            "or set it in the backend process environment before using Gemini features."
        )
    return api_key
