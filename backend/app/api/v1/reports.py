"""Service performance over a period, in the hospital's own calendar and SLA."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedAdmin, get_current_admin
from app.db.session import get_db
from app.schemas.report import (
    DailyAdherence,
    ReportResponse,
    ReportSummary,
    WeeklyAcknowledgement,
    WeeklyAlerts,
)

router = APIRouter(prefix="/reports", tags=["Reports"])

TIERS = ["emergency", "critical", "review", "missed"]
OUTCOMES = ["reassured", "plan_adjusted", "same_day_review", "emergency"]

def _pct(part: int, whole: int):
    return round(part * 100.0 / whole, 1) if whole else None

@router.get("", response_model=ReportResponse)
async def get_report(
    days: int = Query(30, ge=7, le=180),
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    params = {"h_id": current_admin.hospital_id, "days": days}

    hospital = (await db.execute(text("""
        SELECT ack_window_secs, timezone, (now() AT TIME ZONE timezone)::date AS today
        FROM meta.hospital WHERE hospital_id = :h_id
    """), params)).mappings().one()

    # Weeks start on Monday in the hospital's timezone; every week in the period
    # is listed, so quiet weeks show as zero instead of disappearing.
    weekly = (await db.execute(text("""
        WITH weeks AS (
            SELECT generate_series(
                date_trunc('week', (now() AT TIME ZONE h.timezone) - make_interval(days => :days - 1))::date,
                date_trunc('week', now() AT TIME ZONE h.timezone)::date,
                interval '7 days')::date AS week_start
            FROM meta.hospital h WHERE h.hospital_id = :h_id
        ),
        alerts AS (
            SELECT date_trunc('week', a.raised_at AT TIME ZONE h.timezone)::date AS week_start,
                   a.tier, a.acknowledged_at, a.raised_at, h.ack_window_secs
            FROM txn.alert a
            JOIN txn.patient_episode e ON e.episode_id = a.episode_id
            JOIN meta.hospital h       ON h.hospital_id = e.hospital_id
            WHERE e.hospital_id = :h_id
              AND a.raised_at >= now() - make_interval(days => :days)
              -- An alert that closed itself inside its window before anyone acknowledged
              -- it (a missed check-in the patient answered) never fell due.
              AND NOT (a.status = 'expired' AND a.acknowledged_at IS NULL
                       AND a.resolved_at <= a.raised_at + make_interval(secs => h.ack_window_secs))
        )
        SELECT w.week_start,
               count(a.tier) FILTER (WHERE a.tier = 'emergency') AS emergency,
               count(a.tier) FILTER (WHERE a.tier = 'critical')  AS critical,
               count(a.tier) FILTER (WHERE a.tier = 'review')    AS review,
               count(a.tier) FILTER (WHERE a.tier = 'missed')    AS missed,
               count(a.tier) FILTER (WHERE a.acknowledged_at <= a.raised_at + make_interval(secs => a.ack_window_secs)) AS met,
               count(a.tier) FILTER (WHERE a.acknowledged_at IS NOT NULL
                                        OR now() > a.raised_at + make_interval(secs => a.ack_window_secs)) AS decided
        FROM weeks w
        LEFT JOIN alerts a ON a.week_start = w.week_start
        GROUP BY w.week_start
        ORDER BY w.week_start
    """), params)).mappings().all()

    summary = (await db.execute(text("""
        SELECT count(*) AS alerts_raised,
               count(*) FILTER (WHERE a.escalated_at IS NOT NULL) AS escalated,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM a.acknowledged_at - a.raised_at))
                   FILTER (WHERE a.acknowledged_at IS NOT NULL) AS median_ack_secs
        FROM txn.alert a
        JOIN txn.patient_episode e ON e.episode_id = a.episode_id
        WHERE e.hospital_id = :h_id AND a.raised_at >= now() - make_interval(days => :days)
    """), params)).mappings().one()

    outcomes = {o: 0 for o in OUTCOMES}
    for r in (await db.execute(text("""
        SELECT a.outcome, count(*) AS n
        FROM txn.alert a
        JOIN txn.patient_episode e ON e.episode_id = a.episode_id
        WHERE e.hospital_id = :h_id AND a.status = 'resolved'
          AND a.resolved_at >= now() - make_interval(days => :days)
        GROUP BY a.outcome
    """), params)).mappings().all():
        outcomes[r["outcome"]] = r["n"]

    # A patient is expected to check in on each day from discharge to the end of
    # monitoring (withdrawn episodes excluded); a day counts once however many
    # submissions it had.
    adherence = (await db.execute(text("""
        WITH days AS (
            SELECT generate_series(CAST(:today AS date) - (:days - 1), CAST(:today AS date), interval '1 day')::date AS d
        )
        SELECT d.d AS date,
               count(DISTINCT e.episode_id) AS expected,
               count(DISTINCT c.episode_id) AS submitted
        FROM days d
        LEFT JOIN txn.patient_episode e
               ON e.hospital_id = :h_id AND e.status <> 'withdrawn'
              AND d.d BETWEEN e.discharge_date AND e.monitoring_ends_on
        LEFT JOIN txn.patient_check_in c
               ON c.episode_id = e.episode_id AND NOT c.is_superseded
              AND e.discharge_date + c.day_after_discharge = d.d
        GROUP BY d.d
        ORDER BY d.d
    """), {**params, "today": hospital["today"]})).mappings().all()

    decided = sum(w["decided"] for w in weekly)
    expected = sum(r["expected"] for r in adherence)
    median = summary["median_ack_secs"]

    return ReportResponse(
        days=days,
        ack_window_secs=hospital["ack_window_secs"],
        summary=ReportSummary(
            alerts_raised=summary["alerts_raised"],
            escalated=summary["escalated"],
            median_ack_secs=round(median) if median is not None else None,
            ack_compliance_pct=_pct(sum(w["met"] for w in weekly), decided),
            adherence_pct=_pct(sum(r["submitted"] for r in adherence), expected),
        ),
        alerts_by_week=[WeeklyAlerts(week_start=w["week_start"], counts={t: w[t] for t in TIERS}) for w in weekly],
        ack_by_week=[
            WeeklyAcknowledgement(week_start=w["week_start"], decided=w["decided"], met=w["met"],
                                  pct=_pct(w["met"], w["decided"]))
            for w in weekly
        ],
        outcomes=outcomes,
        adherence_by_day=[
            DailyAdherence(date=r["date"], expected=r["expected"], submitted=r["submitted"],
                           pct=_pct(r["submitted"], r["expected"]))
            for r in adherence
        ],
    )
