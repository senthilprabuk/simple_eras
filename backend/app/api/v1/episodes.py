from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_admin, AuthenticatedAdmin
from app.schemas.episode import EpisodeSummary, LatestCheckIn, ParameterReading, ReadingValue

router = APIRouter(prefix="/episodes", tags=["Episodes"])

def _value(kind: str, num, flag, label) -> Optional[ReadingValue]:
    if kind == "boolean":
        return flag
    if kind == "ordinal":
        return label
    return float(num) if num is not None else None

@router.get("/{episode_id}/summary", response_model=EpisodeSummary)
async def get_episode_summary(
    episode_id: UUID,
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """The patient behind an alert: contact details, discharge baseline and latest check-in."""
    episode = (await db.execute(
        text("""
            SELECT
                e.episode_id, e.ruleset_id, e.discharge_date, e.status,
                p.patient_name, p.mrn, p.phone_e164,
                h.hospital_name,
                sp.procedure_code, sp.procedure_name,
                r.version AS ruleset_version,
                ((now() AT TIME ZONE h.timezone)::date - e.discharge_date) AS post_op_day
            FROM txn.patient_episode e
            JOIN txn.patient p              ON p.patient_id    = e.patient_id
            JOIN meta.hospital h            ON h.hospital_id   = e.hospital_id
            JOIN meta.surgical_procedure sp ON sp.procedure_id = e.procedure_id
            JOIN meta.ruleset r             ON r.ruleset_id    = e.ruleset_id
            WHERE e.episode_id = :episode_id AND e.hospital_id = :h_id
        """),
        {"episode_id": episode_id, "h_id": current_admin.hospital_id},
    )).mappings().first()

    if episode is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    latest = (await db.execute(
        text("""
            SELECT check_in_id, day_after_discharge, submitted_at, source,
                   photo_key IS NOT NULL AS photo_submitted
            FROM txn.patient_check_in
            WHERE episode_id = :episode_id AND NOT is_superseded
            ORDER BY day_after_discharge DESC, submitted_at DESC
            LIMIT 1
        """),
        {"episode_id": episode_id},
    )).mappings().first()

    rows = (await db.execute(
        text("""
            SELECT
                p.parameter_code, p.parameter_name, p.parameter_type, p.unit,
                p.decimal_places, p.concerning_when_true,
                b.value_num AS baseline_num, b.value_bool AS baseline_bool,
                coalesce(bo.option_label, b.value_code) AS baseline_label,
                v.value_num AS current_num, v.value_bool AS current_bool,
                coalesce(vo.option_label, v.value_code) AS current_label
            FROM meta.procedure_parameter pp
            JOIN meta.parameter p ON p.parameter_id = pp.parameter_id
            LEFT JOIN txn.episode_baseline b
                   ON b.episode_id = :episode_id AND b.parameter_id = p.parameter_id
            LEFT JOIN meta.parameter_option bo
                   ON bo.parameter_id = p.parameter_id AND bo.option_code = b.value_code
            LEFT JOIN txn.patient_check_in_value v
                   ON v.check_in_id = :check_in_id AND v.parameter_id = p.parameter_id
            LEFT JOIN meta.parameter_option vo
                   ON vo.parameter_id = p.parameter_id AND vo.option_code = v.value_code
            WHERE pp.ruleset_id = :ruleset_id
            ORDER BY pp.display_order
        """),
        {
            "episode_id": episode_id,
            "check_in_id": latest["check_in_id"] if latest else None,
            "ruleset_id": episode["ruleset_id"],
        },
    )).mappings().all()

    readings = []
    for r in rows:
        kind = r["parameter_type"]
        baseline = _value(kind, r["baseline_num"], r["baseline_bool"], r["baseline_label"])
        current = _value(kind, r["current_num"], r["current_bool"], r["current_label"])
        if baseline is None and current is None:
            continue
        readings.append(ParameterReading(
            code=r["parameter_code"],
            name=r["parameter_name"],
            type=kind,
            unit=r["unit"],
            decimals=r["decimal_places"],
            concerning_when_true=r["concerning_when_true"],
            baseline=baseline,
            current=current,
        ))

    return EpisodeSummary(
        episode_id=episode["episode_id"],
        patient_name=episode["patient_name"],
        mrn=episode["mrn"],
        phone_e164=episode["phone_e164"],
        hospital_name=episode["hospital_name"],
        procedure_code=episode["procedure_code"],
        procedure_name=episode["procedure_name"],
        discharge_date=episode["discharge_date"],
        post_op_day=episode["post_op_day"],
        status=episode["status"],
        ruleset_version=episode["ruleset_version"],
        latest_check_in=LatestCheckIn(**latest) if latest else None,
        readings=readings,
    )
