from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_admin, AuthenticatedAdmin
from app.schemas.dashboard import QueueRow, QueueResponse, KpiResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/queue", response_model=QueueResponse)
async def get_queue(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    The hospital's unresolved alerts: most severe tier first, then oldest first.
    The ordering is applied here because a view's own ORDER BY is not guaranteed
    to survive an outer query; alert_id breaks ties so pages are stable.
    """
    params = {"h_id": current_admin.hospital_id}

    total = (await db.execute(
        text("SELECT count(*) FROM txn.v_alert_queue WHERE hospital_id = :h_id"), params
    )).scalar_one()

    rows = (await db.execute(
        text("""
            SELECT
                alert_id, patient_id, patient_name, mrn, episode_id, hospital_id,
                hospital_name, procedure_code, day_after_discharge, tier, reasons,
                raised_at, age_secs, acknowledged, acknowledged_at,
                acknowledged_by_name, ack_window_secs, unanswered
            FROM txn.v_alert_queue
            WHERE hospital_id = :h_id
            ORDER BY
                CASE tier
                    WHEN 'emergency' THEN 1
                    WHEN 'critical'  THEN 2
                    WHEN 'review'    THEN 3
                    WHEN 'missed'    THEN 4
                    ELSE 5
                END,
                raised_at,
                alert_id
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": limit, "offset": offset},
    )).mappings().all()

    return QueueResponse(
        items=[QueueRow.model_validate(dict(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )

@router.get("/kpis", response_model=KpiResponse)
async def get_kpis(
    window_days: int = Query(7, ge=1, le=90, description="Rolling window in days for SLA compliance"),
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Dashboard header figures, scoped to the caller's hospital and its own SLA and timezone."""
    params = {"h_id": current_admin.hospital_id, "days": window_days}

    ack_window_secs = (await db.execute(
        text("SELECT ack_window_secs FROM meta.hospital WHERE hospital_id = :h_id"), params
    )).scalar_one()

    census = (await db.execute(text("""
        SELECT
            (SELECT count(*) FROM txn.patient_episode
             WHERE hospital_id = :h_id AND status = 'active')            AS active_patients,
            count(DISTINCT a.episode_id) FILTER (WHERE e.status = 'active') AS patients_with_open_alerts,
            count(*)                                                     AS unresolved_alerts,
            count(*) FILTER (WHERE a.status = 'open')                    AS unacknowledged_alerts
        FROM txn.alert a
        JOIN txn.patient_episode e ON e.episode_id = a.episode_id
        WHERE e.hospital_id = :h_id
          AND a.status IN ('open', 'acknowledged')
    """), params)).mappings().one()

    # An alert has a verdict once it is acknowledged or its deadline has passed.
    # Alerts still inside their window are left out rather than counted as met.
    ack = (await db.execute(text("""
        SELECT
            count(*) FILTER (
                WHERE a.acknowledged_at <= a.raised_at + make_interval(secs => h.ack_window_secs)
            ) AS met,
            count(*) FILTER (
                WHERE a.acknowledged_at IS NOT NULL
                   OR now() > a.raised_at + make_interval(secs => h.ack_window_secs)
            ) AS decided
        FROM txn.alert a
        JOIN txn.patient_episode e ON e.episode_id = a.episode_id
        JOIN meta.hospital h       ON h.hospital_id = e.hospital_id
        WHERE e.hospital_id = :h_id
          AND a.raised_at >= now() - make_interval(days => :days)
          -- An alert that closed itself inside its window before anyone acknowledged
          -- it (a missed check-in the patient answered) never fell due.
          AND NOT (a.status = 'expired' AND a.acknowledged_at IS NULL
                   AND a.resolved_at <= a.raised_at + make_interval(secs => h.ack_window_secs))
    """), params)).mappings().one()

    # "Today" is the hospital's calendar day, not the database server's.
    missed_checkins = (await db.execute(text("""
        SELECT count(*)
        FROM txn.check_in_evaluation ev
        JOIN txn.patient_episode e ON e.episode_id = ev.episode_id
        JOIN meta.hospital h       ON h.hospital_id = e.hospital_id
        WHERE e.hospital_id = :h_id
          AND ev.tier = 'missed'
          AND ev.evaluated_at >= date_trunc('day', now() AT TIME ZONE h.timezone) AT TIME ZONE h.timezone
          AND ev.evaluated_at <  (date_trunc('day', now() AT TIME ZONE h.timezone) + interval '1 day')
                                  AT TIME ZONE h.timezone
    """), params)).scalar_one()

    decided = ack["decided"]
    return KpiResponse(
        active_patients=census["active_patients"],
        patients_with_open_alerts=census["patients_with_open_alerts"],
        unresolved_alerts=census["unresolved_alerts"],
        unacknowledged_alerts=census["unacknowledged_alerts"],
        ack_compliance_pct=round(ack["met"] * 100.0 / decided, 1) if decided else None,
        ack_decided_alerts=decided,
        ack_window_secs=ack_window_secs,
        missed_checkins_today=missed_checkins,
        window_days=window_days,
    )
