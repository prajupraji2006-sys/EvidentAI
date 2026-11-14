"""Authentication and audit helpers for protected API operations."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, str]:
    """Validate a Supabase access token and return its stable user id."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        response = get_supabase_client().auth.get_user(credentials.credentials)
        user = getattr(response, "user", None)
        user_id = getattr(user, "id", None)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured.",
        ) from None
    except Exception:
        user_id = None

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The session is invalid or expired. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"id": str(user_id)}


def append_audit_event(
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Append an event through the database's serialized hash-chain function."""
    try:
        get_supabase_client().rpc(
            "append_audit_log",
            {
                "p_actor_id": actor_id,
                "p_action": action,
                "p_resource_type": resource_type,
                "p_resource_id": resource_id,
                "p_metadata": metadata or {},
            },
        ).execute()
        return True
    except Exception:
        # The exception can include request details; log only the event category.
        logger.error("Audit event append failed for action=%s", action)
        return False
