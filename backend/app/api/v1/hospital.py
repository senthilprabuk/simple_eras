"""The caller's own hospital. A clinician never sees another hospital's profile."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedAdmin, get_current_admin, require_superadmin
from app.db.session import get_db
from app.schemas.hospital import HospitalProfile, HospitalStats, HospitalUpdate, OfferedProcedure

router = APIRouter(prefix="/hospital", tags=["Hospital"])

async def _profile(db: AsyncSession, hospital_id: int) -> HospitalProfile:
    hospital = (await db.execute(text("""
        SELECT hospital_id, hospital_code, hospital_name, city, timezone, ack_window_secs, is_active
        FROM meta.hospital WHERE hospital_id = :h_id
    """), {"h_id": hospital_id})).mappings().one()

    procedures = (await db.execute(text("""
        SELECT sp.procedure_code, sp.procedure_name, sp.observation_days, hp.enabled_on, hp.is_active
        FROM meta.hospital_procedure hp
        JOIN meta.surgical_procedure sp ON sp.procedure_id = hp.procedure_id
        WHERE hp.hospital_id = :h_id
        ORDER BY sp.procedure_name
    """), {"h_id": hospital_id})).mappings().all()

    stats = (await db.execute(text("""
        SELECT
            (SELECT count(*) FROM txn.patient_episode WHERE hospital_id = :h_id AND status = 'active')    AS active_patients,
            (SELECT count(*) FROM txn.patient_episode WHERE hospital_id = :h_id AND status = 'completed') AS completed_patients,
            (SELECT count(*) FROM meta.admin_user WHERE hospital_id = :h_id AND is_active)               AS active_clinicians,
            (SELECT count(*) FROM txn.alert a JOIN txn.patient_episode e ON e.episode_id = a.episode_id
             WHERE e.hospital_id = :h_id AND a.status IN ('open', 'acknowledged'))                      AS unresolved_alerts,
            (SELECT count(*) FROM txn.patient_check_in c JOIN txn.patient_episode e ON e.episode_id = c.episode_id
             WHERE e.hospital_id = :h_id AND c.submitted_at >= now() - interval '7 days')               AS check_ins_last_7_days
    """), {"h_id": hospital_id})).mappings().one()

    return HospitalProfile(
        **hospital,
        procedures=[OfferedProcedure(**p) for p in procedures],
        stats=HospitalStats(**stats),
    )

@router.get("", response_model=HospitalProfile)
async def get_hospital(
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _profile(db, current_admin.hospital_id)

@router.patch("", response_model=HospitalProfile)
async def update_hospital(
    changes: HospitalUpdate,
    current_admin: AuthenticatedAdmin = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """
    Change the hospital's operational settings. The acknowledgement window drives
    escalation, and the timezone decides what "today" and post-op day mean.
    """
    fields = changes.model_dump(exclude_unset=True)
    if not fields:
        return await _profile(db, current_admin.hospital_id)

    if "timezone" in fields:
        known = (await db.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name = :tz)"), {"tz": fields["timezone"]}
        )).scalar_one()
        if not known:
            raise HTTPException(422, detail=f"Unknown timezone {fields['timezone']!r}; use an IANA name such as Asia/Kolkata")

    # Column names come from the model's own field list, never from input.
    assignments = ", ".join(f"{column} = :{column}" for column in fields)
    await db.execute(
        text(f"UPDATE meta.hospital SET {assignments} WHERE hospital_id = :h_id"),
        {**fields, "h_id": current_admin.hospital_id},
    )
    profile = await _profile(db, current_admin.hospital_id)
    await db.commit()
    return profile
