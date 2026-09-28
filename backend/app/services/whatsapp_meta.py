"""
Checks a hospital's WhatsApp Business credentials against Meta's Graph API and
reads back the number's display details.
"""

import logging
from typing import Any, Dict

import httpx

from app.core.config import settings
from app.services.whatsapp import GRAPH_URL

logger = logging.getLogger("eras.whatsapp.meta")


async def verify_and_fetch_phone_meta(phone_number_id: str, access_token: str) -> Dict[str, Any]:
    """
    Return {"health_status", "display_phone_number", "verified_name"}; the last
    two are None when Meta does not say. Raises ValueError when Meta rejects the
    credentials or cannot be reached.

    Outside WHATSAPP_PROVIDER=meta nothing is checked and the account comes back
    'unverified' with no details, rather than dressed up with ones nobody confirmed.
    """
    clean_id = (phone_number_id or "").strip()
    token = (access_token or "").strip()
    if not clean_id or not token:
        raise ValueError("Phone Number ID and Access Token are required")

    if settings.WHATSAPP_PROVIDER != "meta":
        return {"health_status": "unverified", "display_phone_number": None, "verified_name": None}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"{GRAPH_URL}/{settings.META_API_VERSION}/{clean_id}",
                params={"fields": "display_phone_number,verified_name"},
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("Meta credential check for %s could not complete: %s", clean_id, type(exc).__name__)
        raise ValueError(f"Could not connect to Meta Graph API ({type(exc).__name__})")

    try:
        data = res.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    if res.status_code >= 400:
        err_msg = (data.get("error") or {}).get("message") or f"HTTP {res.status_code}"
        logger.warning("Meta credential check rejected for %s: %s", clean_id, err_msg)
        raise ValueError(f"Meta validation failed: {err_msg}")

    return {
        "health_status": "healthy",
        "display_phone_number": data.get("display_phone_number") or None,
        "verified_name": data.get("verified_name") or None,
    }
