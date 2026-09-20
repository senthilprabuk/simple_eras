"""
Magic Token service for Patient WhatsApp Check-in Links.

Generates and validates tamper-proof, time-bound signed tokens embedding
the patient's episode_id and target post-op day.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
from uuid import UUID

import jwt
from fastapi import HTTPException, status

from app.core.config import settings


MAGIC_TOKEN_PURPOSE = "checkin"
DEFAULT_EXPIRY_HOURS = 24


def generate_magic_token(
    episode_id: Union[UUID, str],
    day: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generate a signed URL-safe JWT for a 1-click patient check-in.
    Default validity: 24 hours from dispatch.
    """
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(hours=DEFAULT_EXPIRY_HOURS)
    expire = now + delta

    payload = {
        "sub": str(episode_id),
        "day": int(day),
        "purpose": MAGIC_TOKEN_PURPOSE,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def validate_magic_token(token: str) -> Dict[str, Any]:
    """
    Validate a magic token signature and expiration.
    Returns {"episode_id": UUID, "day": int}.
    Raises HTTPException(401) on any signature or expiry error.
    """
    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Check-in token is missing",
        )

    try:
        payload = jwt.decode(
            token.strip(),
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "day", "purpose", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This check-in link has expired. Please wait for your next daily reminder or contact the clinic.",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid check-in link.",
        )

    if payload.get("purpose") != MAGIC_TOKEN_PURPOSE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not valid for patient check-in.",
        )

    try:
        episode_uuid = UUID(payload["sub"])
        day = int(payload["day"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed check-in token payload.",
        )

    return {
        "episode_id": episode_uuid,
        "day": day,
    }
