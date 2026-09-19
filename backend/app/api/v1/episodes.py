from datetime import date
from typing import Dict, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_admin, AuthenticatedAdmin
from app.schemas.episode import (
    Address,
    BodyMeasurements,
    ConsentDecision,
    EmergencyContact,
    EpisodeSummary,
    LatestCheckIn,
    ParameterReading,
    ReadingValue,
)

router = APIRouter(prefix="/episodes", tags=["Episodes"])

ADDRESS_FIELDS = ("line", "city", "district", "state", "postal_code")

def _value(kind: str, num, flag, label) -> Optional[ReadingValue]:
    if kind == "boolean":
        return flag
    if kind == "ordinal":
        return label
    return float(num) if num is not None else None

def _age(born: Optional[date], today: date) -> Optional[int]:
    if born is None:
        return None
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

def _body(values: Dict[str, float]) -> BodyMeasurements:
    height, weight = values.get("height_cm"), values.get("weight_kg")
    bp_sys, bp_dia = values.get("bp_sys"), values.get("bp_dia")
    return BodyMeasurements(
        height_cm=height,
        weight_kg=weight,
        bmi=round(weight / (height / 100) ** 2, 1) if height and weight else None,
        bp_systolic=int(bp_sys) if bp_sys is not None else None,
        bp_diastolic=int(bp_dia) if bp_dia is not None else None,
    )

@router.get("/{episode_id}/summary", response_model=EpisodeSummary)
async def get_episode_summary(
    episode_id: UUID,
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    The patient behind an alert: who to call and where they live, discharge
    baseline and latest check-in.
    """
    episode = (await db.execute(
        text("""
            SELECT
                e.episode_id, e.patient_id, e.ruleset_id, e.discharge_date, e.status,
                e.checkin_window_start, e.checkin_window_end,
                p.patient_name, p.mrn, p.phone_e164, p.alt_phone_e164, p.email,
                p.gender, p.date_of_birth,
                p.address_line AS line, p.address_city AS city, p.address_district AS district,
                p.address_state AS state, p.address_postal_code AS postal_code,
                h.hospital_name,
                sp.procedure_code, sp.procedure_name,
                r.version AS ruleset_version,
                (now() AT TIME ZONE h.timezone)::date AS today,
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

    contacts = (await db.execute(text("""
        SELECT contact_name AS name, relationship, phone_e164
        FROM txn.patient_contact
        WHERE patient_id = :patient_id
        ORDER BY priority
    """), {"patient_id": episode["patient_id"]})).mappings().all()

    consents = (await db.execute(text("""
        SELECT consent_code AS code, granted, privacy_law, recorded_at
        FROM txn.episode_consent
        WHERE episode_id = :episode_id
        ORDER BY array_position(ARRAY['remote_monitoring', 'data_processing', 'contact_sharing'], consent_code)
    """), {"episode_id": episode_id})).mappings().all()

    body = {r["parameter_code"]: float(r["value_num"]) for r in (await db.execute(text("""
        SELECT p.parameter_code, b.value_num
        FROM txn.episode_baseline b
        JOIN meta.parameter p ON p.parameter_id = b.parameter_id
        WHERE b.episode_id = :episode_id
          AND p.parameter_code IN ('height_cm', 'weight_kg', 'bp_sys', 'bp_dia')
          AND b.value_num IS NOT NULL
    """), {"episode_id": episode_id})).mappings().all()}

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

    has_address = any(episode[f] for f in ADDRESS_FIELDS)
    return EpisodeSummary(
        episode_id=episode["episode_id"],
        patient_name=episode["patient_name"],
        mrn=episode["mrn"],
        phone_e164=episode["phone_e164"],
        alt_phone_e164=episode["alt_phone_e164"],
        email=episode["email"],
        gender=episode["gender"],
        date_of_birth=episode["date_of_birth"],
        age_years=_age(episode["date_of_birth"], episode["today"]),
        address=Address(**{f: episode[f] for f in ADDRESS_FIELDS}) if has_address else None,
        emergency_contacts=[EmergencyContact(**c) for c in contacts],
        hospital_name=episode["hospital_name"],
        procedure_code=episode["procedure_code"],
        procedure_name=episode["procedure_name"],
        discharge_date=episode["discharge_date"],
        post_op_day=episode["post_op_day"],
        status=episode["status"],
        ruleset_version=episode["ruleset_version"],
        checkin_window_start=episode["checkin_window_start"],
        checkin_window_end=episode["checkin_window_end"],
        consents=[ConsentDecision(**c) for c in consents],
        body=_body(body),
        latest_check_in=LatestCheckIn(**latest) if latest else None,
        readings=readings,
    )
