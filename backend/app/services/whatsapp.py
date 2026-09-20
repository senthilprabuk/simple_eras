"""
WhatsApp messaging service for patient check-ins and clinical guidance.

Supports:
- Meta WhatsApp Cloud API (Graph API v21.0)
- Local dev logger / mock dispatch
- Disabled safety mode
"""

import logging
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from app.core.config import settings

logger = logging.getLogger("eras.whatsapp")


def normalize_phone(phone: str) -> str:
    """Normalize phone number to international digits-only (stripping +, spaces, hyphens)."""
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def _get_meta_url(phone_number_id: Optional[str] = None, endpoint: str = "messages") -> str:
    pid = phone_number_id or settings.META_PHONE_NUMBER_ID or ""
    return f"https://graph.facebook.com/{settings.META_API_VERSION}/{pid}/{endpoint}"


async def send_whatsapp_text(
    to: str,
    body: str,
    preview_url: bool = True,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send an outbound text message via WhatsApp.
    Uses hospital-specific phone_number_id and access_token if provided,
    otherwise falls back to system settings.
    """
    clean_phone = normalize_phone(to)
    active_token = access_token or settings.META_ACCESS_TOKEN
    active_pid = phone_number_id or settings.META_PHONE_NUMBER_ID

    if settings.WHATSAPP_PROVIDER == "disabled":
        logger.warning(
            "WHATSAPP_PROVIDER is 'disabled'. Message to %s suppressed.", clean_phone
        )
        return {"status": "queued", "message_id": None}

    if settings.WHATSAPP_PROVIDER == "log" or not active_token or active_token.startswith("mock_"):
        mock_id = f"wamid.mock_{uuid4().hex}"
        logger.info(
            "\n" + "=" * 70 + "\n"
            "[WHATSAPP DISPATCH] To: +%s (from pid: %s, wamid: %s)\n"
            "%s\n" + "=" * 70,
            clean_phone,
            active_pid or "default",
            mock_id,
            body,
        )
        return {"status": "sent", "message_id": mock_id}

    # Meta Cloud API
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_phone,
        "type": "text",
        "text": {
            "preview_url": preview_url,
            "body": body,
        },
    }

    headers = {
        "Authorization": f"Bearer {active_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(
                _get_meta_url(phone_number_id=active_pid, endpoint="messages"),
                headers=headers,
                json=payload,
            )
            data = response.json()
            if response.status_code >= 400:
                err_detail = data.get("error", {}).get("message", response.text)
                logger.error("Meta WhatsApp API error (%s): %s", response.status_code, err_detail)
                return {"status": "failed", "error": err_detail, "message_id": None}

            wamid = None
            if "messages" in data and len(data["messages"]) > 0:
                wamid = data["messages"][0].get("id")

            return {"status": "sent", "message_id": wamid}
        except Exception as exc:
            logger.exception("Failed to dispatch WhatsApp message to %s: %s", clean_phone, exc)
            return {"status": "failed", "error": str(exc), "message_id": None}


async def send_whatsapp_template(
    to: str,
    template_name: str,
    language_code: str = "en",
    components: Optional[List[Dict[str, Any]]] = None,
    phone_number_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send an approved Meta WhatsApp template message.
    """
    clean_phone = normalize_phone(to)
    active_token = access_token or settings.META_ACCESS_TOKEN
    active_pid = phone_number_id or settings.META_PHONE_NUMBER_ID

    if settings.WHATSAPP_PROVIDER == "disabled":
        return {"status": "queued", "message_id": None}

    if settings.WHATSAPP_PROVIDER == "log" or not settings.META_ACCESS_TOKEN:
        mock_id = f"wamid.mock_tpl_{uuid4().hex}"
        logger.info(
            "[WHATSAPP TEMPLATE MOCK] To: +%s | Template: %s (%s) | Components: %s",
            clean_phone,
            template_name,
            language_code,
            components,
        )
        return {"status": "sent", "message_id": mock_id}

    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components or [],
        },
    }

    headers = {
        "Authorization": f"Bearer {settings.META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(
                _get_meta_url("messages"),
                headers=headers,
                json=payload,
            )
            data = response.json()
            if response.status_code >= 400:
                err_detail = data.get("error", {}).get("message", response.text)
                logger.error("Meta Template API error (%s): %s", response.status_code, err_detail)
                return {"status": "failed", "error": err_detail, "message_id": None}

            wamid = None
            if "messages" in data and len(data["messages"]) > 0:
                wamid = data["messages"][0].get("id")
            return {"status": "sent", "message_id": wamid}
        except Exception as exc:
            logger.exception("Failed to dispatch WhatsApp template to %s: %s", clean_phone, exc)
            return {"status": "failed", "error": str(exc), "message_id": None}
