from typing import Dict, List, Literal, Optional
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedAdmin, get_current_admin
from app.db.session import get_db
from app.schemas.patient import (
    ObservationCell,
    ObservationColumn,
    ObservationRow,
    PatientListItem,
    PatientListResponse,
    PatientTimeline,
    Trend,
    TrendPoint,
)
from app.services.scoring import daily_thresholds, describe_scoring

router = APIRouter(prefix="/patients", tags=["Patients"])

TREND_CODES = ["temp_c", "pain", "steps"]
OBSERVATION_CODES = ["breathless", "calf_pain", "drainage", "chills"]

ORDER_BY = {
    "priority": """
        CASE oa.top_tier WHEN 'emergency' THEN 1 WHEN 'critical' THEN 2
                         WHEN 'review' THEN 3 WHEN 'missed' THEN 4 ELSE 5 END,
        p.patient_name
    """,
    "recent": "e.created_at DESC",
    "name": "p.patient_name",
}

def _like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"

def _check_in_today(row, monitored_days: int) -> str:
    """
    Whether today's check-in is in, from the post-operative day the row already
    carries. That day is computed in the hospital's own timezone, which is the
    reason this is answered here and not in the browser: a workstation an hour
    ahead would call a patient overdue who is not.

    A closed episode, or one whose monitoring window has passed, is not waiting
    on anything, so it reads as not_due rather than as a patient who has failed
    to report.
    """
    day = row["post_op_day"]
    if row["status"] != "active" or day < 0 or day > monitored_days:
        return "not_due"
    if row["last_day"] == day:
        return "done"
    return "none_yet" if not row["check_in_days"] else "pending"

@router.get("", response_model=PatientListResponse)
async def list_patients(
    status_filter: Literal["active", "completed", "withdrawn", "all"] = Query("active", alias="status"),
    search: str = Query("", max_length=100),
    sort: Literal["priority", "recent", "name"] = "priority",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """The hospital's monitored patients with check-in adherence and open alerts."""
    params = {
        "h_id": current_admin.hospital_id,
        "status": status_filter,
        "search": search.strip(),
        "pattern": _like_pattern(search.strip()),
    }
    where = """
        e.hospital_id = :h_id
        AND (:status = 'all' OR e.status = :status)
        AND (:search = '' OR p.patient_name ILIKE :pattern ESCAPE '\\' OR p.mrn ILIKE :pattern ESCAPE '\\')
    """

    total = (await db.execute(text(f"""
        SELECT count(*) FROM txn.patient_episode e
        JOIN txn.patient p ON p.patient_id = e.patient_id
        WHERE {where}
    """), params)).scalar_one()

    rows = (await db.execute(text(f"""
        SELECT
            e.episode_id, p.patient_id, p.patient_name, p.mrn, p.phone_e164, p.language_code,
            sp.procedure_code, e.operative_side, e.discharge_date, e.monitoring_ends_on, e.status,
            e.created_at AS enrolled_at, au.full_name AS enrolled_by_name,
            ((now() AT TIME ZONE h.timezone)::date - e.discharge_date) AS post_op_day,
            ci.last_day, ci.last_at, coalesce(ci.days, 0) AS check_in_days,
            coalesce(oa.open_alerts, 0) AS open_alerts, oa.top_tier
        FROM txn.patient_episode e
        JOIN txn.patient p              ON p.patient_id    = e.patient_id
        JOIN meta.hospital h            ON h.hospital_id   = e.hospital_id
        JOIN meta.surgical_procedure sp ON sp.procedure_id = e.procedure_id
        LEFT JOIN meta.admin_user au    ON au.admin_user_id = e.enrolled_by
        LEFT JOIN LATERAL (
            SELECT max(c.day_after_discharge) AS last_day, max(c.submitted_at) AS last_at,
                   count(DISTINCT c.day_after_discharge) AS days
            FROM txn.patient_check_in c
            WHERE c.episode_id = e.episode_id AND NOT c.is_superseded
        ) ci ON true
        LEFT JOIN LATERAL (
            SELECT count(*) AS open_alerts,
                   (array_agg(a.tier ORDER BY CASE a.tier WHEN 'emergency' THEN 1 WHEN 'critical' THEN 2
                                                           WHEN 'review' THEN 3 ELSE 4 END))[1] AS top_tier
            FROM txn.alert a
            WHERE a.episode_id = e.episode_id AND a.status IN ('open', 'acknowledged')
        ) oa ON true
        WHERE {where}
        ORDER BY {ORDER_BY[sort]}, e.episode_id
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": limit, "offset": offset})).mappings().all()

    items = []
    for r in rows:
        monitored_days = (r["monitoring_ends_on"] - r["discharge_date"]).days
        expected = max(0, min(r["post_op_day"], monitored_days) + 1)
        items.append(PatientListItem(
            episode_id=r["episode_id"],
            patient_id=r["patient_id"],
            patient_name=r["patient_name"],
            mrn=r["mrn"],
            phone_e164=r["phone_e164"],
            language_code=r["language_code"],
            procedure_code=r["procedure_code"],
            operative_side=r["operative_side"],
            check_in_today=_check_in_today(r, monitored_days),
            discharge_date=r["discharge_date"],
            monitoring_ends_on=r["monitoring_ends_on"],
            status=r["status"],
            post_op_day=r["post_op_day"],
            enrolled_at=r["enrolled_at"],
            enrolled_by_name=r["enrolled_by_name"],
            last_check_in_day=r["last_day"],
            last_check_in_at=r["last_at"],
            check_in_days=r["check_in_days"],
            expected_check_in_days=expected,
            adherence_pct=round(r["check_in_days"] * 100.0 / expected, 1) if expected else None,
            open_alerts=r["open_alerts"],
            top_open_tier=r["top_tier"],
        ))

    return PatientListResponse(items=items, total=total, limit=limit, offset=offset)

@router.get("/{episode_id}/timeline", response_model=PatientTimeline)
async def get_patient_timeline(
    episode_id: UUID,
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Day-by-day record for the drilldown: trend measures with the ruleset's
    scoring thresholds, and the red-flag symptom answers. Days without a
    check-in stay in the series as gaps rather than being dropped.
    """
    episode = (await db.execute(text("""
        SELECT e.episode_id, e.ruleset_id, e.discharge_date, e.monitoring_ends_on,
               ((now() AT TIME ZONE h.timezone)::date - e.discharge_date) AS post_op_day
        FROM txn.patient_episode e
        JOIN meta.hospital h ON h.hospital_id = e.hospital_id
        WHERE e.episode_id = :episode_id AND e.hospital_id = :h_id
    """), {"episode_id": episode_id, "h_id": current_admin.hospital_id})).mappings().first()

    if episode is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    monitored_days = (episode["monitoring_ends_on"] - episode["discharge_date"]).days
    last_day = min(episode["post_op_day"], monitored_days)
    days = list(range(0, last_day + 1))
    codes = TREND_CODES + OBSERVATION_CODES

    bindings = {r["parameter_code"]: r for r in (await db.execute(text("""
        SELECT p.parameter_code, p.parameter_name, p.unit, p.decimal_places,
               pp.question_text, pp.collect_from_day, pp.collect_to_day,
               pp.score_from_day, pp.score_to_day, pp.scoring_config
        FROM meta.procedure_parameter pp
        JOIN meta.parameter p ON p.parameter_id = pp.parameter_id
        WHERE pp.ruleset_id = :ruleset_id AND p.parameter_code = ANY(:codes)
    """), {"ruleset_id": episode["ruleset_id"], "codes": codes})).mappings().all()}

    # The latest live submission for each day.
    check_ins = {r["day_after_discharge"]: r for r in (await db.execute(text("""
        SELECT DISTINCT ON (day_after_discharge) check_in_id, day_after_discharge, source
        FROM txn.patient_check_in
        WHERE episode_id = :episode_id AND NOT is_superseded
        ORDER BY day_after_discharge, submitted_at DESC
    """), {"episode_id": episode_id})).mappings().all()}

    answers: Dict[UUID, Dict[str, object]] = {}
    if check_ins:
        for r in (await db.execute(text("""
            SELECT v.check_in_id, p.parameter_code, v.value_num, v.value_bool
            FROM txn.patient_check_in_value v
            JOIN meta.parameter p ON p.parameter_id = v.parameter_id
            WHERE v.check_in_id = ANY(:ids) AND p.parameter_code = ANY(:codes)
        """), {"ids": [c["check_in_id"] for c in check_ins.values()], "codes": codes})).mappings().all():
            value = r["value_bool"] if r["value_bool"] is not None else r["value_num"]
            answers.setdefault(r["check_in_id"], {})[r["parameter_code"]] = value

    baselines = {r["parameter_code"]: float(r["value_num"]) for r in (await db.execute(text("""
        SELECT p.parameter_code, b.value_num
        FROM txn.episode_baseline b
        JOIN meta.parameter p ON p.parameter_id = b.parameter_id
        WHERE b.episode_id = :episode_id AND p.parameter_code = ANY(:codes) AND b.value_num IS NOT NULL
    """), {"episode_id": episode_id, "codes": TREND_CODES})).mappings().all()}

    def answer(day: int, code: str):
        check_in = check_ins.get(day)
        return answers.get(check_in["check_in_id"], {}).get(code) if check_in else None

    trends: List[Trend] = []
    for code in TREND_CODES:
        binding = bindings.get(code)
        if binding is None:
            continue
        values: List[Optional[float]] = [
            float(v) if (v := answer(d, code)) is not None else None for d in days
        ]
        thresholds, direction = daily_thresholds(
            binding["scoring_config"], days, values, binding["score_from_day"], binding["score_to_day"],
        )
        trends.append(Trend(
            code=code,
            name=binding["parameter_name"],
            unit=binding["unit"],
            decimals=binding["decimal_places"],
            baseline=baselines.get(code),
            threshold_direction=direction,
            scoring_rule=describe_scoring(binding["scoring_config"]),
            points=[
                TrendPoint(
                    day=d,
                    date=episode["discharge_date"] + timedelta(days=d),
                    value=values[i],
                    threshold=round(thresholds[i], 2) if thresholds[i] is not None else None,
                    collected=binding["collect_from_day"] <= d <= binding["collect_to_day"],
                )
                for i, d in enumerate(days)
            ],
        ))

    columns = [
        ObservationColumn(
            code=code,
            name=bindings[code]["parameter_name"],
            question_text=bindings[code]["question_text"],
            is_emergency=bool(bindings[code]["scoring_config"].get("emergency")),
        )
        for code in OBSERVATION_CODES if code in bindings
    ]

    observations = [
        ObservationRow(
            day=d,
            date=episode["discharge_date"] + timedelta(days=d),
            checked_in=d in check_ins,
            source=check_ins[d]["source"] if d in check_ins else None,
            values={
                col.code: ObservationCell(
                    value=answer(d, col.code),
                    asked=bindings[col.code]["collect_from_day"] <= d <= bindings[col.code]["collect_to_day"],
                )
                for col in columns
            },
        )
        for d in days
    ]

    return PatientTimeline(
        episode_id=episode["episode_id"],
        post_op_day=episode["post_op_day"],
        trends=trends,
        observation_columns=columns,
        observations=observations,
    )
