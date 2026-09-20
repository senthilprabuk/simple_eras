"""
API Router for Hospital WhatsApp Business Account management and QR code pairing.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import AuthenticatedAdmin, get_current_admin
from app.db.session import get_db
from app.schemas.whatsapp import (
    WhatsAppAccountCreate,
    WhatsAppAccountResponse,
    WhatsAppTestSendRequest,
    WhatsAppTestSendResponse,
)
from app.services.whatsapp import send_whatsapp_text
from app.services.whatsapp_meta import verify_and_fetch_phone_meta
from app.services.whatsapp_qr import generate_whatsapp_qr_code

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Account"])


def _mask_token(tok: str) -> str:
    if not tok:
        return "••••••••"
    if len(tok) <= 8:
        return "••••••••"
    return tok[:4] + "••••••••" + tok[-4:]


def _get_webhook_url() -> str:
    # Build webhook URL relative to base URL
    base = settings.FRONTEND_BASE_URL.replace(":3000", ":8000")
    return f"{base.rstrip('/')}/api/v1/whatsapp/webhook"


@router.get("/account", response_model=Optional[WhatsAppAccountResponse])
async def get_whatsapp_account(
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the connected WhatsApp Business Account and live QR code for the current hospital."""
    row = (
        await db.execute(
            text("""
            SELECT account_id, hospital_id, display_name, display_phone_number,
                   phone_number_id, waba_id, access_token, verify_token, meta_app_id,
                   health_status, is_active, created_at
            FROM meta.hospital_whatsapp
            WHERE hospital_id = :h_id AND is_default = true
        """),
            {"h_id": current_admin.hospital_id},
        )
    ).mappings().first()

    if not row:
        return None

    prefill = f"Hello {row['display_name']} care team"
    click_url, qr_data_url = generate_whatsapp_qr_code(row["display_phone_number"], prefilled_message=prefill)

    return WhatsAppAccountResponse(
        account_id=row["account_id"],
        hospital_id=row["hospital_id"],
        display_name=row["display_name"],
        display_phone_number=row["display_phone_number"],
        phone_number_id=row["phone_number_id"],
        waba_id=row["waba_id"],
        meta_app_id=row["meta_app_id"],
        access_token_masked=_mask_token(row["access_token"]),
        verify_token=row["verify_token"],
        health_status=row["health_status"],
        is_active=row["is_active"],
        qr_code_url=qr_data_url,
        click_to_chat_url=click_url,
        webhook_url=_get_webhook_url(),
        created_at=row["created_at"],
    )


@router.post("/account", response_model=WhatsAppAccountResponse)
async def save_whatsapp_account(
    payload: WhatsAppAccountCreate,
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Connect or update the hospital's WhatsApp Business Account.
    Validates the credentials against Meta Graph API and auto-detects
    verified name and display phone number.
    """
    if current_admin.role not in ("admin", "superadmin", "app_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only hospital administrators can manage WhatsApp settings",
        )

    # Check for existing account to preserve token or phone if not passed
    existing = (
        await db.execute(
            text("SELECT account_id, access_token, display_phone_number, display_name FROM meta.hospital_whatsapp WHERE hospital_id = :h_id"),
            {"h_id": current_admin.hospital_id},
        )
    ).mappings().first()

    token_to_use = (payload.access_token or "").strip()
    if not token_to_use and existing:
        token_to_use = existing["access_token"]

    if not token_to_use:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access Token is required to connect a new WhatsApp Business Account",
        )

    try:
        meta_info = await verify_and_fetch_phone_meta(
            phone_number_id=payload.phone_number_id,
            access_token=token_to_use,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Use explicitly submitted phone number and display name if provided,
    # otherwise fall back to Meta Graph API lookup or existing stored values.
    display_name = (
        payload.display_name.strip()
        if payload.display_name and payload.display_name.strip()
        else (meta_info.get("verified_name") or (existing["display_name"] if existing else None) or f"Hospital Line ({payload.phone_number_id[-4:]})")
    )
    display_phone = (
        payload.display_phone_number.strip()
        if payload.display_phone_number and payload.display_phone_number.strip()
        else (meta_info.get("display_phone_number") or (existing["display_phone_number"] if existing else None) or "+91 98765 43210")
    )
    health_status = meta_info.get("health_status") or "healthy"

    params = {
        "h_id": current_admin.hospital_id,
        "disp_name": display_name,
        "disp_phone": display_phone,
        "phone_id": payload.phone_number_id.strip(),
        "waba_id": payload.waba_id.strip(),
        "token": token_to_use,
        "verify": payload.verify_token.strip(),
        "app_id": payload.meta_app_id.strip() if payload.meta_app_id else None,
        "health": health_status,
    }

    if existing:
        row = (
            await db.execute(
                text("""
                UPDATE meta.hospital_whatsapp SET
                    display_name = :disp_name,
                    display_phone_number = :disp_phone,
                    phone_number_id = :phone_id,
                    waba_id = :waba_id,
                    access_token = :token,
                    verify_token = :verify,
                    meta_app_id = :app_id,
                    health_status = :health,
                    is_active = true,
                    updated_at = now()
                WHERE hospital_id = :h_id
                RETURNING account_id, hospital_id, display_name, display_phone_number,
                          phone_number_id, waba_id, meta_app_id, access_token, verify_token,
                          health_status, is_active, created_at
            """),
                params,
            )
        ).mappings().one()
    else:
        row = (
            await db.execute(
                text("""
                INSERT INTO meta.hospital_whatsapp (
                    hospital_id, display_name, display_phone_number,
                    phone_number_id, waba_id, access_token, verify_token,
                    meta_app_id, health_status, is_default, is_active, updated_at
                ) VALUES (
                    :h_id, :disp_name, :disp_phone,
                    :phone_id, :waba_id, :token, :verify,
                    :app_id, :health, true, true, now()
                )
                RETURNING account_id, hospital_id, display_name, display_phone_number,
                          phone_number_id, waba_id, meta_app_id, access_token, verify_token,
                          health_status, is_active, created_at
            """),
                params,
            )
        ).mappings().one()

    await db.commit()

    prefill = f"Hello {row['display_name']} care team"
    click_url, qr_data_url = generate_whatsapp_qr_code(row["display_phone_number"], prefilled_message=prefill)

    return WhatsAppAccountResponse(
        account_id=row["account_id"],
        hospital_id=row["hospital_id"],
        display_name=row["display_name"],
        display_phone_number=row["display_phone_number"],
        phone_number_id=row["phone_number_id"],
        waba_id=row["waba_id"],
        meta_app_id=row["meta_app_id"],
        access_token_masked=_mask_token(row["access_token"]),
        verify_token=row["verify_token"],
        health_status=row["health_status"],
        is_active=row["is_active"],
        qr_code_url=qr_data_url,
        click_to_chat_url=click_url,
        webhook_url=_get_webhook_url(),
        created_at=row["created_at"],
    )


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_whatsapp_account(
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect and remove the hospital's WhatsApp Business Account."""
    if current_admin.role not in ("admin", "superadmin", "app_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    await db.execute(
        text("DELETE FROM meta.hospital_whatsapp WHERE hospital_id = :h_id"),
        {"h_id": current_admin.hospital_id},
    )
    await db.commit()
    return None


@router.post("/test", response_model=WhatsAppTestSendResponse)
async def send_test_message(
    payload: WhatsAppTestSendRequest,
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Send a test WhatsApp message from the connected hospital number to a specified recipient."""
    acc = (
        await db.execute(
            text("""
            SELECT display_name, display_phone_number, phone_number_id, access_token
            FROM meta.hospital_whatsapp
            WHERE hospital_id = :h_id AND is_default = true AND is_active = true
        """),
            {"h_id": current_admin.hospital_id},
        )
    ).mappings().first()

    hospital_name = acc["display_name"] if acc else "St. Mary's Orthopedic Center"
    text_body = (
        payload.message
        or f"Hello from {hospital_name}! 🏥\nThis is a test check-in message sent from your verified hospital WhatsApp number."
    )

    res = await send_whatsapp_text(to=payload.to_phone, body=text_body)

    return WhatsAppTestSendResponse(
        status=res.get("status", "sent"),
        message_id=res.get("message_id"),
        error=res.get("error"),
    )
