from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models.txn import Alert, PatientEpisode
from app.core.security import get_current_admin, AuthenticatedAdmin
from app.schemas.alert import AlertAcknowledgeResponse

router = APIRouter(prefix="/alerts", tags=["Alerts"])

@router.post("/{alert_id}/acknowledge", response_model=AlertAcknowledgeResponse)
async def acknowledge_alert(
    alert_id: UUID,
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Acknowledge a critical/emergency/review alert.
    Stops the escalation timer and records the clinician identity and timestamp.
    
    Security & Multi-Tenancy:
    - If alert does not exist or belongs to another hospital, returns 404 Not Found
      (prevents tenant enumeration / leaking cross-hospital alert existence).
    - If alert is already acknowledged or resolved, returns 409 Conflict.
    """
    # Query alert joining patient_episode to check hospital ownership
    query = (
        select(Alert)
        .join(PatientEpisode, PatientEpisode.episode_id == Alert.episode_id)
        .where(
            Alert.alert_id == alert_id,
            PatientEpisode.hospital_id == current_admin.hospital_id
        )
    )

    result = await db.execute(query)
    alert = result.scalar_one_or_none()

    # 404 on non-existent OR cross-hospital alert
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )

    # 409 Conflict if already acknowledged or resolved
    if alert.status in ("acknowledged", "resolved"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alert has already been acknowledged or resolved"
        )

    now = datetime.now(timezone.utc)
    alert.status = "acknowledged"
    alert.acknowledged_at = now
    alert.acknowledged_by = current_admin.admin_user_id

    await db.commit()
    await db.refresh(alert)

    return AlertAcknowledgeResponse(
        alert_id=alert.alert_id,
        status=alert.status,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        acknowledged_by_name=current_admin.full_name,
        message="Alert successfully acknowledged"
    )
