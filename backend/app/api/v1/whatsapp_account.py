"""
The hospital's WhatsApp Business account: its credentials, the click-to-chat QR
code patients scan, and a test send.

The Meta access token is a long-lived credential the tenant-scoped role cannot
read, so the endpoints that need it use get_system_db, like the password
endpoints in clinicians.py. Row-level security does not apply to them: every
query filters on the caller's hospital explicitly.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import AuthenticatedAdmin, get_current_admin, require_superadmin
from app.db.session import get_db, get_system_db
from app.schemas.whatsapp import (
    WhatsAppAccountCreate,
    WhatsAppAccountResponse,
    WhatsAppTestSendRequest,
    WhatsAppTestSendResponse,
)
from app.services.whatsapp import Credentials, send_whatsapp_text
from app.services.whatsapp_meta import verify_and_fetch_phone_meta
from app.services.whatsapp_qr import generate_whatsapp_qr_code

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Account"])

TOKEN_MASK = "••••••••"
ACCOUNT_COLUMNS = """account_id, hospital_id, display_name, display_phone_number, phone_number_id,
                     waba_id, meta_app_id, verify_token, health_status, is_active, created_at"""


def _account_response(row, current_admin: AuthenticatedAdmin) -> WhatsAppAccountResponse:
    click_url, qr_data_url = generate_whatsapp_qr_code(
        row["display_phone_number"], prefilled_message=f"Hello {row['display_name']} care team"
    )
    return WhatsAppAccountResponse(
        account_id=row["account_id"],
        hospital_id=row["hospital_id"],
        display_name=row["display_name"],
        display_phone_number=row["display_phone_number"],
        phone_number_id=row["phone_number_id"],
        waba_id=row["waba_id"],
        meta_app_id=row["meta_app_id"],
        access_token_masked=TOKEN_MASK,
        # A secret shared with Meta: only someone who can change it needs to see it.
        verify_token=row["verify_token"] if current_admin.role == "superadmin" else None,
        health_status=row["health_status"],
        is_active=row["is_active"],
        qr_code_url=qr_data_url,
        click_to_chat_url=click_url,
        webhook_url=f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}/api/v1/whatsapp/webhook",
        created_at=row["created_at"],
    )


def _first_filled(*values: Optional[str]) -> Optional[str]:
    return next((v.strip() for v in values if v and v.strip()), None)


@router.get("/account", response_model=Optional[WhatsAppAccountResponse])
async def get_whatsapp_account(
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """The hospital's connected WhatsApp Business Account and its QR code, or null."""
    row = (await db.execute(
        text(f"SELECT {ACCOUNT_COLUMNS} FROM meta.hospital_whatsapp WHERE hospital_id = :h_id AND is_default"),
        {"h_id": current_admin.hospital_id},
    )).mappings().first()
    return _account_response(row, current_admin) if row else None


@router.post("/account", response_model=WhatsAppAccountResponse)
async def save_whatsapp_account(
    payload: WhatsAppAccountCreate,
    current_admin: AuthenticatedAdmin = Depends(require_superadmin),
    db: AsyncSession = Depends(get_system_db),
):
    """
    Connect or update the hospital's WhatsApp Business Account. With the meta
    provider the credentials are checked against the Graph API, which also
    supplies the display name and number when the form leaves them out.
    """
    existing = (await db.execute(text("""
        SELECT access_token, display_name, display_phone_number
        FROM meta.hospital_whatsapp
        WHERE hospital_id = :h_id AND is_default
    """), {"h_id": current_admin.hospital_id})).mappings().first()

    token = _first_filled(payload.access_token, existing["access_token"] if existing else None)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access Token is required to connect a new WhatsApp Business Account",
        )

    try:
        meta_info = await verify_and_fetch_phone_meta(phone_number_id=payload.phone_number_id, access_token=token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Patients message whatever number this is, so it comes from the form, from
    # Meta, or from what was saved before, and is never made up.
    display_name = _first_filled(
        payload.display_name, meta_info["verified_name"], existing["display_name"] if existing else None
    )
    display_phone = _first_filled(
        payload.display_phone_number, meta_info["display_phone_number"],
        existing["display_phone_number"] if existing else None,
    )
    if not display_name or not display_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter the WhatsApp number and display name: Meta has not confirmed them",
        )

    try:
        row = (await db.execute(text(f"""
            INSERT INTO meta.hospital_whatsapp (
                hospital_id, display_name, display_phone_number, phone_number_id, waba_id,
                access_token, verify_token, meta_app_id, health_status, is_default, is_active
            ) VALUES (
                :h_id, :disp_name, :disp_phone, :phone_id, :waba_id,
                :token, :verify, :app_id, :health, true, true
            )
            ON CONFLICT (hospital_id) WHERE is_default = true DO UPDATE SET
                display_name = excluded.display_name,
                display_phone_number = excluded.display_phone_number,
                phone_number_id = excluded.phone_number_id,
                waba_id = excluded.waba_id,
                access_token = excluded.access_token,
                verify_token = excluded.verify_token,
                meta_app_id = excluded.meta_app_id,
                health_status = excluded.health_status,
                is_active = true
            RETURNING {ACCOUNT_COLUMNS}
        """), {
            "h_id": current_admin.hospital_id,
            "disp_name": display_name,
            "disp_phone": display_phone,
            "phone_id": payload.phone_number_id.strip(),
            "waba_id": payload.waba_id.strip(),
            "token": token,
            "verify": payload.verify_token.strip(),
            "app_id": _first_filled(payload.meta_app_id),
            "health": meta_info["health_status"],
        })).mappings().one()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That Phone Number ID is already connected to another hospital",
        )
    await db.commit()
    return _account_response(row, current_admin)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_whatsapp_account(
    current_admin: AuthenticatedAdmin = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect and remove the hospital's WhatsApp Business Account."""
    await db.execute(
        text("DELETE FROM meta.hospital_whatsapp WHERE hospital_id = :h_id"),
        {"h_id": current_admin.hospital_id},
    )
    await db.commit()
    return None


@router.post("/test", response_model=WhatsAppTestSendResponse)
async def send_test_message(
    payload: WhatsAppTestSendRequest,
    current_admin: AuthenticatedAdmin = Depends(require_superadmin),
    db: AsyncSession = Depends(get_system_db),
):
    """
    Send free text from the hospital's own number. WhatsApp delivers it only to
    someone who has written to that number in the last 24 hours, for instance by
    scanning the QR code.
    """
    acc = (await db.execute(text("""
        SELECT display_name, phone_number_id, access_token
        FROM meta.hospital_whatsapp
        WHERE hospital_id = :h_id AND is_default AND is_active
    """), {"h_id": current_admin.hospital_id})).mappings().first()
    if acc is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connect a WhatsApp number before sending a test message",
        )

    result = await send_whatsapp_text(
        payload.to_phone,
        payload.message or f"This is a test message from {acc['display_name']} on ERAS.",
        Credentials(acc["phone_number_id"], acc["access_token"]),
        reference=f"test message for hospital {current_admin.hospital_id}",
    )
    error = result.error
    if result.status == "queued":
        error = "WhatsApp sending is disabled on this server (WHATSAPP_PROVIDER=disabled): nothing was sent"
    return WhatsAppTestSendResponse(status=result.status, message_id=result.message_id, error=error)
