from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_admin, AuthenticatedAdmin
from app.schemas.dashboard import QueueRow, QueueResponse, KpiResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/queue", response_model=QueueResponse)
async def get_queue(
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch prioritized clinical risk queue for the authenticated admin's hospital.
    Ordering is pre-sorted server-side by txn.v_alert_queue:
    Severity tier (emergency > critical > review > missed), then raised_at ASC.
    NOTE: Numeric evaluation scores are strictly excluded from response.
    """
    stmt = text("""
        SELECT 
            alert_id,
            patient_id,
            patient_name,
            mrn,
            episode_id,
            hospital_id,
            hospital_name,
            procedure_code,
            day_after_discharge,
            tier,
            reasons,
            raised_at,
            age_secs,
            acknowledged,
            acknowledged_at,
            acknowledged_by_name
        FROM txn.v_alert_queue
        WHERE hospital_id = :h_id;
    """)

    result = await db.execute(stmt, {"h_id": current_admin.hospital_id})
    rows = result.mappings().all()

    items: List[QueueRow] = []
    for r in rows:
        items.append(QueueRow(
            alert_id=r["alert_id"],
            patient_id=r["patient_id"],
            patient_name=r["patient_name"],
            mrn=r["mrn"],
            episode_id=r["episode_id"],
            hospital_id=r["hospital_id"],
            hospital_name=r["hospital_name"],
            procedure_code=r["procedure_code"],
            day_after_discharge=r["day_after_discharge"],
            tier=r["tier"],
            reasons=r["reasons"] if isinstance(r["reasons"], list) else [],
            raised_at=r["raised_at"],
            age_secs=r["age_secs"],
            acknowledged=bool(r["acknowledged"]),
            acknowledged_at=r["acknowledged_at"],
            acknowledged_by_name=r["acknowledged_by_name"]
        ))

    return QueueResponse(items=items, total=len(items))

@router.get("/kpis", response_model=KpiResponse)
async def get_kpis(
    window_days: int = Query(7, ge=1, le=90, description="Rolling window in days for SLA compliance rate"),
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Compute Key Performance Indicators for the Page 1 dashboard cards,
    strictly scoped to the caller's hospital_id:
    1. active_patients
    2. open_alerts
    3. ack_rate_15min (% acknowledged within 15m window)
    4. missed_checkins_today
    """
    h_id = current_admin.hospital_id

    # 1. Active Patients
    active_patients_stmt = text("""
        SELECT count(*) FROM txn.patient_episode
        WHERE hospital_id = :h_id AND status = 'active';
    """)
    res = await db.execute(active_patients_stmt, {"h_id": h_id})
    active_patients = res.scalar() or 0

    # 2. Open Alerts
    open_alerts_stmt = text("""
        SELECT count(*) FROM txn.alert a
        JOIN txn.patient_episode e ON e.episode_id = a.episode_id
        WHERE e.hospital_id = :h_id AND a.status IN ('open', 'acknowledged');
    """)
    res = await db.execute(open_alerts_stmt, {"h_id": h_id})
    open_alerts = res.scalar() or 0

    # 3. Ack Rate (<15 mins) over rolling window
    ack_rate_stmt = text("""
        SELECT 
            CASE 
                WHEN count(*) = 0 THEN 100.0
                ELSE ROUND(
                    (count(*) FILTER (WHERE EXTRACT(epoch FROM (a.acknowledged_at - a.raised_at)) <= 900) * 100.0) / count(*),
                    1
                )
            END AS ack_rate
        FROM txn.alert a
        JOIN txn.patient_episode e ON e.episode_id = a.episode_id
        WHERE e.hospital_id = :h_id
          AND a.acknowledged_at IS NOT NULL
          AND a.raised_at >= (now() - (make_interval(days => :days)));
    """)
    res = await db.execute(ack_rate_stmt, {"h_id": h_id, "days": window_days})
    ack_rate = float(res.scalar() or 100.0)

    # 4. Missed Check-ins Today
    missed_stmt = text("""
        SELECT count(*) FROM txn.check_in_evaluation ev
        JOIN txn.patient_episode e ON e.episode_id = ev.episode_id
        WHERE e.hospital_id = :h_id
          AND ev.tier = 'missed'
          AND ev.evaluated_at::date = CURRENT_DATE;
    """)
    res = await db.execute(missed_stmt, {"h_id": h_id})
    missed_checkins = res.scalar() or 0

    return KpiResponse(
        active_patients=active_patients,
        open_alerts=open_alerts,
        ack_rate_15min=ack_rate,
        missed_checkins_today=missed_checkins,
        window_days=window_days
    )
