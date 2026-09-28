"""
WhatsApp transport: one call to Meta's Cloud API per message.

WHATSAPP_PROVIDER selects what happens:
  disabled  send nothing and report the message still queued, so an unconfigured
            deployment never looks as though a patient was told when they were not
  log       write a line to the application log and report it sent (development)
  meta      send through the Graph API with the hospital's own credentials, or the
            platform's META_* settings when the hospital has none

Patient details stay out of the log. The number and text are in
txn.patient_message, and a reminder's text carries a check-in link that works as
a credential for the patient's day.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from app.core.config import settings

logger = logging.getLogger("eras.whatsapp")

GRAPH_URL = "https://graph.facebook.com"
SEND_TIMEOUT_SECS = 15.0


@dataclass(frozen=True)
class Credentials:
    phone_number_id: str
    access_token: str


@dataclass(frozen=True)
class SendResult:
    status: str  # sent, queued (nothing attempted) or failed
    message_id: Optional[str] = None
    error: Optional[str] = None
    # A timeout, rate limit or Meta outage may pass; a rejected number or template will not.
    retryable: bool = False


def normalize_phone(phone: str) -> str:
    """Digits only, as the Graph API and wa.me links expect: '+91 98765 43210' -> '919876543210'."""
    return re.sub(r"\D", "", phone or "")


def resolve_credentials(phone_number_id: Optional[str], access_token: Optional[str]) -> Optional[Credentials]:
    """The hospital's own account if it has one, else the platform's, else None."""
    if phone_number_id and access_token:
        return Credentials(phone_number_id, access_token)
    if settings.META_PHONE_NUMBER_ID and settings.META_ACCESS_TOKEN:
        return Credentials(settings.META_PHONE_NUMBER_ID, settings.META_ACCESS_TOKEN)
    return None


async def send_whatsapp_text(
    to: str, body: str, credentials: Optional[Credentials], *, reference: str
) -> SendResult:
    """
    Free text. WhatsApp delivers it only within 24 hours of the recipient last
    writing to this number, so patient messages go as templates instead.
    """
    return await _send(
        to,
        {"type": "text", "text": {"preview_url": False, "body": body}},
        credentials,
        reference=reference,
        described_as="free text",
    )


async def send_whatsapp_template(
    to: str,
    template_name: str,
    language_code: str,
    parameters: List[str],
    credentials: Optional[Credentials],
    *,
    reference: str,
) -> SendResult:
    """An approved Meta template; parameters fill its {{1}}, {{2}}... in order."""
    template: Dict[str, Any] = {"name": template_name, "language": {"code": language_code}}
    if parameters:
        template["components"] = [
            {"type": "body", "parameters": [{"type": "text", "text": p} for p in parameters]}
        ]
    return await _send(
        to,
        {"type": "template", "template": template},
        credentials,
        reference=reference,
        described_as=f"template {template_name} ({language_code}) with {len(parameters)} variable(s)",
    )


async def _send(
    to: str, content: Dict[str, Any], credentials: Optional[Credentials], *, reference: str, described_as: str
) -> SendResult:
    if settings.WHATSAPP_PROVIDER == "disabled":
        return SendResult("queued")

    if settings.WHATSAPP_PROVIDER == "log":
        logger.info("[whatsapp:log] %s: %s", reference, described_as)
        return SendResult("sent", message_id=f"log.{uuid4().hex}")

    if credentials is None:
        return SendResult("failed", error="No WhatsApp account is connected for this hospital")

    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": normalize_phone(to), **content}
    return await _post(credentials, payload, reference)


async def _post(credentials: Credentials, payload: Dict[str, Any], reference: str) -> SendResult:
    url = f"{GRAPH_URL}/{settings.META_API_VERSION}/{credentials.phone_number_id}/messages"
    try:
        async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECS) as client:
            response = await client.post(
                url, headers={"Authorization": f"Bearer {credentials.access_token}"}, json=payload
            )
    except httpx.HTTPError as exc:
        # A timeout can mean Meta sent it anyway, so a retry may duplicate the
        # message; that is better than the patient never hearing.
        logger.warning("WhatsApp send for %s did not complete: %s", reference, type(exc).__name__)
        return SendResult("failed", error=f"Could not reach Meta ({type(exc).__name__})", retryable=True)

    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    if response.status_code >= 400:
        error = (data.get("error") or {}).get("message") or f"HTTP {response.status_code}"
        logger.warning("Meta rejected WhatsApp send for %s (%s): %s", reference, response.status_code, error)
        return SendResult(
            "failed", error=error, retryable=response.status_code == 429 or response.status_code >= 500
        )

    messages = data.get("messages") or [{}]
    return SendResult("sent", message_id=messages[0].get("id"))
