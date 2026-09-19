from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedAdmin, get_current_admin
from app.db.session import get_db
from app.schemas.checkin import OrdinalOption
from app.schemas.enrollment import (
    BaselineParameter,
    EnrollmentOptions,
    EnrollmentProcedure,
    EnrollmentRequest,
    EnrollmentResponse,
)

router = APIRouter(prefix="/enrollment", tags=["Enrollment"])

# Discharge readings the rules engine compares later check-ins against.
BASELINE_CODES = ["temp_c", "hr", "spo2", "pain", "knee_bend", "walk_aid"]

async def _baseline_parameters(db: AsyncSession) -> List[BaselineParameter]:
    rows = (await db.execute(text("""
        SELECT p.parameter_id, p.parameter_code, p.parameter_name, p.parameter_type, p.unit,
               p.value_min, p.value_max, p.decimal_places
        FROM meta.parameter p
        WHERE p.parameter_code = ANY(:codes) AND p.is_active
        ORDER BY array_position(:codes, p.parameter_code)
    """), {"codes": BASELINE_CODES})).mappings().all()

    options = {}
    for o in (await db.execute(text("""
        SELECT parameter_id, option_code, option_label, ordinal_rank
        FROM meta.parameter_option
        WHERE parameter_id = ANY(:ids)
        ORDER BY parameter_id, ordinal_rank
    """), {"ids": [r["parameter_id"] for r in rows]})).mappings().all():
        options.setdefault(o["parameter_id"], []).append(
            OrdinalOption(code=o["option_code"], label=o["option_label"], rank=o["ordinal_rank"])
        )

    return [
        BaselineParameter(
            code=r["parameter_code"],
            name=r["parameter_name"],
            type=r["parameter_type"],
            unit=r["unit"],
            value_min=float(r["value_min"]) if r["value_min"] is not None else None,
            value_max=float(r["value_max"]) if r["value_max"] is not None else None,
            decimals=r["decimal_places"],
            options=options.get(r["parameter_id"], []),
        )
        for r in rows
    ]

@router.get("/options", response_model=EnrollmentOptions)
async def enrollment_options(
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """What the enrollment form needs: procedures this hospital offers and the baseline measures."""
    procedures = (await db.execute(text("""
        SELECT sp.procedure_code, sp.procedure_name, sp.observation_days, r.version AS ruleset_version
        FROM meta.hospital_procedure hp
        JOIN meta.surgical_procedure sp ON sp.procedure_id = hp.procedure_id
        JOIN meta.ruleset r ON r.procedure_id = sp.procedure_id AND r.status = 'approved'
        WHERE hp.hospital_id = :h_id AND hp.is_active AND sp.is_active
        ORDER BY sp.procedure_name
    """), {"h_id": current_admin.hospital_id})).mappings().all()

    today = (await db.execute(text(
        "SELECT (now() AT TIME ZONE timezone)::date FROM meta.hospital WHERE hospital_id = :h_id"
    ), {"h_id": current_admin.hospital_id})).scalar_one()

    return EnrollmentOptions(
        procedures=[EnrollmentProcedure(**p) for p in procedures],
        languages=["en", "ta", "hi"],
        baseline_parameters=await _baseline_parameters(db),
        today=today,
    )

@router.post("", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def enroll_patient(
    req: EnrollmentRequest,
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Start monitoring a patient after surgery. An MRN already registered here is
    treated as a returning patient (a second surgery) only if the name matches;
    otherwise it is refused, since a mistyped MRN would merge two people's records.
    """
    h_id = current_admin.hospital_id

    procedure = (await db.execute(text("""
        SELECT sp.procedure_id, sp.observation_days, r.ruleset_id,
               (SELECT (now() AT TIME ZONE h.timezone)::date FROM meta.hospital h WHERE h.hospital_id = :h_id) AS today
        FROM meta.hospital_procedure hp
        JOIN meta.surgical_procedure sp ON sp.procedure_id = hp.procedure_id
        JOIN meta.ruleset r ON r.procedure_id = sp.procedure_id AND r.status = 'approved'
        WHERE hp.hospital_id = :h_id AND hp.is_active AND sp.is_active AND sp.procedure_code = :code
    """), {"h_id": h_id, "code": req.procedure_code})).mappings().first()

    if procedure is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This hospital does not offer that procedure")
    if req.discharge_date > procedure["today"]:
        raise HTTPException(422, detail="Discharge date cannot be in the future")

    parameters = {p.code: p for p in await _baseline_parameters(db)}
    baseline_rows = []
    for code, value in req.baseline.items():
        param = parameters.get(code)
        if param is None:
            raise HTTPException(422, detail=f"{code} is not a baseline measure")
        if param.type == "ordinal":
            if value not in {o.code for o in param.options}:
                raise HTTPException(422, detail=f"{param.name}: unknown option {value!r}")
            baseline_rows.append({"code": code, "num": None, "code_value": value})
        else:
            if isinstance(value, str) or not (param.value_min <= value <= param.value_max):
                raise HTTPException(
                    422,
                    detail=f"{param.name} must be between {param.value_min:g} and {param.value_max:g}",
                )
            baseline_rows.append({"code": code, "num": round(float(value), param.decimals), "code_value": None})

    existing = (await db.execute(text("""
        SELECT patient_id, patient_name,
               EXISTS (SELECT 1 FROM txn.patient_episode e
                       WHERE e.patient_id = p.patient_id AND e.status = 'active') AS has_active_episode
        FROM txn.patient p
        WHERE p.hospital_id = :h_id AND p.mrn = :mrn
    """), {"h_id": h_id, "mrn": req.mrn})).mappings().first()

    if existing and existing["patient_name"].strip().lower() != req.patient_name.lower():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"MRN {req.mrn} is already registered to a different patient. Check the MRN.",
        )
    if existing and existing["has_active_episode"]:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This patient is already being monitored")

    try:
        if existing:
            patient_id = existing["patient_id"]
        else:
            patient_id = (await db.execute(text("""
                INSERT INTO txn.patient (hospital_id, mrn, patient_name, phone_e164, language_code, date_of_birth)
                VALUES (:h_id, :mrn, :name, :phone, :lang, :dob)
                RETURNING patient_id
            """), {
                "h_id": h_id, "mrn": req.mrn, "name": req.patient_name, "phone": req.phone_e164,
                "lang": req.language_code, "dob": req.date_of_birth,
            })).scalar_one()

        monitoring_ends_on = req.discharge_date + timedelta(days=procedure["observation_days"])
        episode_id = (await db.execute(text("""
            INSERT INTO txn.patient_episode
                (patient_id, hospital_id, procedure_id, ruleset_id, surgery_date, discharge_date,
                 monitoring_ends_on, consent_version, consent_at, enrolled_by, status)
            VALUES (:patient_id, :h_id, :procedure_id, :ruleset_id, :surgery, :discharge,
                    :ends, :consent, now(), :admin_id, 'active')
            RETURNING episode_id
        """), {
            "patient_id": patient_id, "h_id": h_id, "procedure_id": procedure["procedure_id"],
            "ruleset_id": procedure["ruleset_id"], "surgery": req.surgery_date, "discharge": req.discharge_date,
            "ends": monitoring_ends_on, "consent": req.consent_version, "admin_id": current_admin.admin_user_id,
        })).scalar_one()

        if baseline_rows:
            await db.execute(text("""
                INSERT INTO txn.episode_baseline (episode_id, parameter_id, value_num, value_code)
                SELECT CAST(:episode_id AS uuid), p.parameter_id, CAST(:num AS numeric), CAST(:code_value AS text)
                FROM meta.parameter p WHERE p.parameter_code = :code
            """), [{"episode_id": episode_id, **row} for row in baseline_rows])

        await db.commit()
    except IntegrityError:
        # Lost a race with a simultaneous enrollment of the same MRN or patient.
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This patient was enrolled at the same moment. Refresh and check.")

    return EnrollmentResponse(
        episode_id=episode_id,
        patient_id=patient_id,
        returning_patient=existing is not None,
        monitoring_ends_on=monitoring_ends_on,
        post_op_day=(procedure["today"] - req.discharge_date).days,
        baseline_recorded=len(baseline_rows),
    )
