from typing import Literal, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_admin, AuthenticatedAdmin
from app.schemas.alert import (
    AlertAcknowledgeResponse,
    AlertHistoryItem,
    AlertHistoryResponse,
    AlertResolveRequest,
    AlertResolveResponse,
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])

@router.get("", response_model=AlertHistoryResponse)
async def list_alerts(
    status_filter: Literal["all", "open", "acknowledged", "resolved", "expired"] = Query("all", alias="status"),
    tier: Literal["all", "emergency", "critical", "review", "missed"] = "all",
    days: int = Query(30, ge=1, le=365, description="Alerts raised in the last N days"),
    episode_id: Optional[UUID] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Alert history in every state, newest first, with who handled each and how quickly."""
    params = {
        "h_id": current_admin.hospital_id,
        "status": status_filter,
        "tier": tier,
        "days": days,
        "episode_id": episode_id,
    }
    where = """
        e.hospital_id = :h_id
        AND a.raised_at >= now() - make_interval(days => :days)
        AND (:status = 'all' OR a.status = :status)
        AND (:tier = 'all' OR a.tier = :tier)
        AND (CAST(:episode_id AS uuid) IS NULL OR a.episode_id = CAST(:episode_id AS uuid))
    """

    total = (await db.execute(text(f"""
        SELECT count(*) FROM txn.alert a
        JOIN txn.patient_episode e ON e.episode_id = a.episode_id
        WHERE {where}
    """), params)).scalar_one()

    rows = (await db.execute(text(f"""
        SELECT
            a.alert_id, a.episode_id, p.patient_name, p.mrn, a.tier, a.status,
            ev.day_after_discharge, ev.reasons, a.raised_at, a.escalated_at,
            a.acknowledged_at, ack.full_name AS acknowledged_by_name,
            extract(epoch FROM a.acknowledged_at - a.raised_at)::int AS ack_secs,
            h.ack_window_secs,
            a.resolved_at, res.full_name AS resolved_by_name, a.outcome, a.outcome_note
        FROM txn.alert a
        JOIN txn.patient_episode e     ON e.episode_id = a.episode_id
        JOIN txn.patient p             ON p.patient_id = e.patient_id
        JOIN meta.hospital h           ON h.hospital_id = e.hospital_id
        JOIN txn.check_in_evaluation ev ON ev.evaluation_id = a.evaluation_id
        LEFT JOIN meta.admin_user ack  ON ack.admin_user_id = a.acknowledged_by
        LEFT JOIN meta.admin_user res  ON res.admin_user_id = a.resolved_by
        WHERE {where}
        ORDER BY a.raised_at DESC, a.alert_id
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset})).mappings().all()

    return AlertHistoryResponse(
        items=[AlertHistoryItem.model_validate(dict(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )

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
