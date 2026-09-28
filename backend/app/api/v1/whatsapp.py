"""
WhatsApp webhook for Meta's Cloud API.

GET  /webhook  the subscription handshake: Meta echoes hub.challenge back once
               the verify token matches the platform's or a connected hospital's
POST /webhook  delivery receipts (sent -> delivered -> read, or failed) for
               outbound patient messages; inbound patient messages are ignored

Neither call carries a user, so both read across hospitals as the connecting
role, like the background jobs. A POST is trusted only once its X-Hub-Signature-256
matches META_APP_SECRET; without that secret every POST is refused.
"""

import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db

logger = logging.getLogger("eras.whatsapp.webhook")

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Webhook"])


def _signature_is_valid(body_bytes: bytes, signature_header: Optional[str]) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.META_APP_SECRET.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.removeprefix("sha256=").encode("utf-8"), expected.encode("utf-8"))


async def _is_known_verify_token(db: AsyncSession, token: str) -> bool:
    platform = settings.META_WEBHOOK_VERIFY_TOKEN
    if platform and hmac.compare_digest(token.encode("utf-8"), platform.encode("utf-8")):
        return True
    return (await db.execute(
        text("SELECT 1 FROM meta.hospital_whatsapp WHERE verify_token = :token AND is_active LIMIT 1"),
        {"token": token},
    )).first() is not None


@router.get("/webhook")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    db: AsyncSession = Depends(get_db),
):
    """Meta's subscription handshake."""
    if hub_mode == "subscribe" and hub_verify_token and await _is_known_verify_token(db, hub_verify_token):
        logger.info("Meta webhook verification accepted.")
        return PlainTextResponse(content=hub_challenge or "", status_code=status.HTTP_200_OK)

    logger.warning("Meta webhook verification rejected: unknown verify token.")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed")


@router.post("/webhook")
async def process_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_hub_signature_256: Optional[str] = Header(None),
):
    """Record delivery receipts for outbound patient messages."""
    if not settings.META_APP_SECRET:
        logger.error("WhatsApp webhook call refused: META_APP_SECRET is not set, so its signature cannot be checked.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook signature cannot be verified",
        )

    body_bytes = await request.body()
    if not _signature_is_valid(body_bytes, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature",
        )

    try:
        payload = json.loads(body_bytes)
    except ValueError:
        return {"ok": True, "status_updates": 0}

    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return {"ok": True, "status_updates": 0}

    updated_statuses = 0

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            val = change.get("value", {})
            if val.get("messaging_product") != "whatsapp":
                continue

            for st in val.get("statuses", []):
                wamid = st.get("id")
                new_status = st.get("status")
                if not wamid or not new_status:
                    continue

                params: Dict[str, Any] = {"wamid": wamid}
                if new_status == "delivered":
                    stmt = text("""
                        UPDATE txn.patient_message
                        SET status = 'delivered', delivered_at = now()
                        WHERE meta_message_id = :wamid AND status IN ('queued', 'sent')
                    """)
                elif new_status == "read":
                    stmt = text("""
                        UPDATE txn.patient_message
                        SET status = 'read', read_at = COALESCE(read_at, now()),
                            delivered_at = COALESCE(delivered_at, now())
                        WHERE meta_message_id = :wamid AND status IN ('queued', 'sent', 'delivered')
                    """)
                elif new_status == "failed":
                    errors = st.get("errors") or [{}]
                    params["err"] = errors[0].get("message") or errors[0].get("title") or "Meta delivery failed"
                    stmt = text("""
                        UPDATE txn.patient_message
                        SET status = 'failed', error_message = :err
                        WHERE meta_message_id = :wamid AND status IN ('queued', 'sent')
                    """)
                else:
                    continue

                updated_statuses += max((await db.execute(stmt, params)).rowcount, 0)

    await db.commit()
    return {"ok": True, "status_updates": updated_statuses}
