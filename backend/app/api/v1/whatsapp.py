"""
WhatsApp webhook endpoint for Meta Cloud API.

Handles:
1. GET /webhook: Webhook subscription handshake (hub.challenge verification).
2. POST /webhook: Delivery status receipts (sent -> delivered -> read) and incoming patient messages.
"""

import hashlib
import hmac
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db

logger = logging.getLogger("eras.whatsapp.webhook")

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Webhook"])

STATUS_RANK = {
    "queued": 0,
    "sent": 1,
    "failed": 2,
    "delivered": 2,
    "read": 3,
}


def _verify_meta_signature(body_bytes: bytes, signature_header: Optional[str]) -> bool:
    """Verify Meta's sha256 HMAC signature when META_APP_SECRET is configured."""
    if not settings.META_APP_SECRET:
        return True
    if not signature_header:
        return False
    parts = signature_header.split("=")
    if len(parts) != 2 or parts[0] != "sha256":
        return False
    expected = hmac.new(
        settings.META_APP_SECRET.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(parts[1], expected)


@router.get("/webhook")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """
    Meta Webhook Verification handshake.
    Meta hits this GET endpoint with hub.mode, hub.verify_token, and hub.challenge.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.META_WEBHOOK_VERIFY_TOKEN:
        logger.info("Meta webhook verification accepted.")
        return PlainTextResponse(content=hub_challenge or "", status_code=status.HTTP_200_OK)

    logger.warning("Meta webhook verification rejected: token mismatch.")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed")


@router.post("/webhook")
async def process_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_hub_signature_256: Optional[str] = Header(None),
):
    """
    Receive webhook event payloads from Meta WhatsApp Cloud API.
    Updates delivery statuses (sent, delivered, read) for outbound patient messages.
    """
    body_bytes = await request.body()

    if not _verify_meta_signature(body_bytes, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature",
        )

    try:
        payload = await request.json()
    except Exception:
        return {"ok": True, "processed": 0}

    if not payload or payload.get("object") != "whatsapp_business_account":
        return {"ok": True, "processed": 0}

    entries = payload.get("entry", [])
    updated_statuses = 0

    for entry in entries:
        for change in entry.get("changes", []):
            val = change.get("value", {})
            if val.get("messaging_product") != "whatsapp":
                continue

            # Process delivery status receipts (sent, delivered, read, failed)
            for st in val.get("statuses", []):
                wamid = st.get("id")
                new_status = st.get("status")
                if not wamid or not new_status:
                    continue

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
                    err_msg = None
                    errors = st.get("errors", [])
                    if errors:
                        err_msg = errors[0].get("message") or errors[0].get("title")
                    stmt = text("""
                        UPDATE txn.patient_message
                        SET status = 'failed', error_message = :err
                        WHERE meta_message_id = :wamid AND status IN ('queued', 'sent')
                    """)
                else:
                    stmt = None

                if stmt is not None:
                    params: Dict[str, Any] = {"wamid": wamid}
                    if new_status == "failed":
                        params["err"] = err_msg or "Meta delivery failed"
                    res = await db.execute(stmt, params)
                    if res.rowcount > 0:
                        updated_statuses += res.rowcount

    await db.commit()
    return {"ok": True, "status_updates": updated_statuses}
