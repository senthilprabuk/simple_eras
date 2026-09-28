"""
Signed check-in links for WhatsApp reminders.

A link carries the episode and the post-op day it was sent for, signed so it
cannot be altered, and expires after a day. It is a credential for that
patient's check-in: it is minted when the reminder is sent and never stored.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
from uuid import UUID

import jwt

from app.core.config import settings

MAGIC_TOKEN_PURPOSE = "checkin"
DEFAULT_EXPIRY_HOURS = 24


class InvalidCheckInLink(Exception):
    """The link is missing, altered, expired or not a check-in link. str() is safe to show the patient."""


def generate_magic_token(
    episode_id: Union[UUID, str],
    day: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """A URL-safe signed token for one episode's check-in on one post-op day."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(hours=DEFAULT_EXPIRY_HOURS))

    payload = {
        "sub": str(episode_id),
        "day": int(day),
        "purpose": MAGIC_TOKEN_PURPOSE,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def validate_magic_token(token: str) -> Dict[str, Any]:
    """Return {"episode_id": UUID, "day": int}, or raise InvalidCheckInLink."""
    if not token or not token.strip():
        raise InvalidCheckInLink("Check-in token is missing")

    try:
        payload = jwt.decode(
            token.strip(),
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "day", "purpose", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise InvalidCheckInLink(
            "This check-in link has expired. Please wait for your next daily reminder or contact the clinic."
        )
    except jwt.PyJWTError:
        raise InvalidCheckInLink("Invalid check-in link.")

    if payload.get("purpose") != MAGIC_TOKEN_PURPOSE:
        raise InvalidCheckInLink("Token is not valid for patient check-in.")

    try:
        return {"episode_id": UUID(payload["sub"]), "day": int(payload["day"])}
    except (ValueError, KeyError, TypeError):
        raise InvalidCheckInLink("Malformed check-in token payload.")
