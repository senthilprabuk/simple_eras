from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_admin, AuthenticatedAdmin
from app.schemas.alert import AlertAcknowledgeResponse, AlertResolveRequest, AlertResolveResponse

router = APIRouter(prefix="/alerts", tags=["Alerts"])

async def _refusal(db: AsyncSession, alert_id: UUID, hospital_id: int, action: str) -> HTTPException:
    """
    Explain why a guarded update touched no row. An alert in another hospital is
    reported as missing (404), never as forbidden, so its existence is not leaked.
    """
    current_status = (await db.execute(
        text("""
            SELECT a.status FROM txn.alert a
            JOIN txn.patient_episode e ON e.episode_id = a.episode_id
            WHERE a.alert_id = :alert_id AND e.hospital_id = :h_id
        """),
        {"alert_id": alert_id, "h_id": hospital_id},
    )).scalar_one_or_none()

    if current_status is None:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Alert is already {current_status} and cannot be {action}",
    )

@router.post("/{alert_id}/acknowledge", response_model=AlertAcknowledgeResponse)
async def acknowledge_alert(
    alert_id: UUID,
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Acknowledge an open alert, stopping its escalation timer.

    The status check and the write are one statement, so when two clinicians
    acknowledge at once exactly one succeeds and the other gets 409. Acknowledged,
    resolved and expired alerts are all refused.
    """
    row = (await db.execute(
        text("""
            UPDATE txn.alert a
               SET status = 'acknowledged',
                   acknowledged_at = now(),
                   acknowledged_by = :admin_id
              FROM txn.patient_episode e
             WHERE a.alert_id = :alert_id
               AND e.episode_id = a.episode_id
               AND e.hospital_id = :h_id
               AND a.status = 'open'
            RETURNING a.alert_id, a.status, a.acknowledged_at, a.acknowledged_by
        """),
        {"alert_id": alert_id, "admin_id": current_admin.admin_user_id, "h_id": current_admin.hospital_id},
    )).mappings().first()

    if row is None:
        raise await _refusal(db, alert_id, current_admin.hospital_id, "acknowledged")

    await db.commit()

    return AlertAcknowledgeResponse(
        **row,
        acknowledged_by_name=current_admin.full_name,
    )

@router.post("/{alert_id}/resolve", response_model=AlertResolveResponse)
async def resolve_alert(
    alert_id: UUID,
    payload: AlertResolveRequest,
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Close an alert with a recorded clinical outcome.

    Resolving an alert nobody acknowledged also acknowledges it at the same
    moment, so the audit trail always shows who first responded and when.
    """
    row = (await db.execute(
        text("""
            UPDATE txn.alert a
               SET status = 'resolved',
                   resolved_at = now(),
                   resolved_by = :admin_id,
                   outcome = :outcome,
                   outcome_note = :note,
                   acknowledged_at = coalesce(a.acknowledged_at, now()),
                   acknowledged_by = coalesce(a.acknowledged_by, :admin_id)
              FROM txn.patient_episode e
             WHERE a.alert_id = :alert_id
               AND e.episode_id = a.episode_id
               AND e.hospital_id = :h_id
               AND a.status IN ('open', 'acknowledged')
            RETURNING a.alert_id, a.status, a.outcome, a.outcome_note,
                      a.acknowledged_at, a.resolved_at, a.resolved_by
        """),
        {
            "alert_id": alert_id,
            "admin_id": current_admin.admin_user_id,
            "h_id": current_admin.hospital_id,
            "outcome": payload.outcome,
            "note": payload.note,
        },
    )).mappings().first()

    if row is None:
        raise await _refusal(db, alert_id, current_admin.hospital_id, "resolved")

    await db.commit()

    return AlertResolveResponse(**row, resolved_by_name=current_admin.full_name)
