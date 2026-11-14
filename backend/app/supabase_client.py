import os

from supabase import Client, create_client

from app import config as _config  # Ensure backend/.env is loaded for direct service use.


def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SECRET_KEY", "").strip()

    if not url:
        raise RuntimeError("SUPABASE_URL is not configured.")

    if not key:
        raise RuntimeError("SUPABASE_SECRET_KEY is not configured.")

    return create_client(url, key)
