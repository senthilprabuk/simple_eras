"""
Meta WhatsApp Cloud API account verification service.

Validates Phone Number ID and Access Token against Meta Graph API
and auto-detects the verified hospital business name and display phone number.
"""

import logging
import re
from typing import Any, Dict

import httpx

from app.core.config import settings

logger = logging.getLogger("eras.whatsapp.meta")


async def verify_and_fetch_phone_meta(
    phone_number_id: str,
    access_token: str,
) -> Dict[str, Any]:
    """
    Validate credentials with Meta Graph API and retrieve phone details.
    Falls back gracefully to mock verification in dev/offline mode.
    """
    clean_id = (phone_number_id or "").strip()
    token = (access_token or "").strip()

    if not clean_id or not token:
        raise ValueError("Phone Number ID and Access Token are required")

    # If mock token or non-meta provider, simulate successful lookup
    if token.startswith("mock_") or token.startswith("test_") or settings.WHATSAPP_PROVIDER != "meta":
        logger.info("Using mock Meta phone metadata for phone_number_id: %s", clean_id)
        # Format dummy phone number nicely
        return {
            "display_phone_number": "+91 98765 43210",
            "verified_name": "St. Mary's Orthopedic Center",
            "health_status": "healthy",
            "quality_rating": "GREEN",
        }

    # Live Meta Graph API lookup
    url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{clean_id}"
    params = {
        "fields": "display_phone_number,verified_name,code_verification_status,quality_rating",
    }
    headers = {
        "Authorization": f"Bearer {token}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, params=params, headers=headers)
            data = res.json()

            if res.status_code >= 400:
                err_msg = data.get("error", {}).get("message", res.text)
                logger.warning("Meta credential check rejected for %s: %s", clean_id, err_msg)
                raise ValueError(f"Meta validation failed: {err_msg}")

            display_phone = data.get("display_phone_number") or ""
            verified_name = data.get("verified_name") or f"Hospital Line ({clean_id[-4:]})"
            quality = data.get("quality_rating") or "UNKNOWN"

            return {
                "display_phone_number": display_phone,
                "verified_name": verified_name,
                "health_status": "healthy",
                "quality_rating": quality,
            }
    except ValueError:
        raise
    except Exception as exc:
        logger.exception("Error checking Meta credentials for %s: %s", clean_id, exc)
        raise ValueError(f"Could not connect to Meta Graph API: {str(exc)}")
