"""
Patient daily check-in: form definition and submission.

PROTOTYPE SCOPE — these routes are deliberately unauthenticated because patient
identity does not exist yet (enrolment links / OTP are a later phase). They expose
patient names and write clinical values, so they must be gated behind patient auth
before this reaches real patients.
"""

from datetime import date
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.checkin import (
    CheckInForm,
    CheckInReceipt,
    CheckInSubmit,
    EpisodeContext,
    EpisodeOption,
    FormParameter,
    FormSection,
    OrdinalOption,
)

router = APIRouter(prefix="/checkin", tags=["Patient Check-in"])

# Post-op day is taken in the hospital's own timezone, not the server's, so the
# day does not roll over at 05:30 local for an Asia/Kolkata clinic.
POST_OP_DAY_SQL = "((now() AT TIME ZONE h.timezone)::date - e.discharge_date)::int"

EPISODE_SQL = f"""
    SELECT
        e.episode_id,
        e.ruleset_id,
        e.monitoring_ends_on,
        e.status,
        p.patient_name,
        p.mrn,
        h.hospital_name,
        sp.procedure_code,
        {POST_OP_DAY_SQL} AS post_op_day
    FROM txn.patient_episode e
    JOIN txn.patient p             ON p.patient_id = e.patient_id
    JOIN meta.hospital h           ON h.hospital_id = e.hospital_id
    JOIN meta.surgical_procedure sp ON sp.procedure_id = e.procedure_id
"""

async def _load_episode(db: AsyncSession, episode_id: UUID):
    result = await db.execute(
        text(EPISODE_SQL + " WHERE e.episode_id = :episode_id"),
        {"episode_id": episode_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return row

@router.get("/episodes", response_model=List[EpisodeOption])
async def list_episodes(db: AsyncSession = Depends(get_db)):
    """Active episodes available to the check-in simulator, with today's submission state."""
    stmt = text(
        EPISODE_SQL
        + f"""
        WHERE e.status = 'active'
        ORDER BY p.patient_name
        """
    )
    result = await db.execute(stmt)
    episodes = result.mappings().all()

    if not episodes:
        return []

    submitted = await db.execute(
        text(
            """
            SELECT DISTINCT c.episode_id, c.day_after_discharge
            FROM txn.patient_check_in c
            WHERE c.episode_id = ANY(:ids)
            """
        ),
        {"ids": [e["episode_id"] for e in episodes]},
    )
    submitted_days = {(r["episode_id"], r["day_after_discharge"]) for r in submitted.mappings().all()}

    return [
        EpisodeOption(
            episode_id=e["episode_id"],
            patient_name=e["patient_name"],
            mrn=e["mrn"],
            procedure_code=e["procedure_code"],
            post_op_day=e["post_op_day"],
            monitoring_ends_on=e["monitoring_ends_on"],
            checked_in_today=(e["episode_id"], e["post_op_day"]) in submitted_days,
        )
        for e in episodes
    ]

@router.get("/form", response_model=CheckInForm)
async def get_checkin_form(
    episode_id: UUID = Query(..., description="Episode to build the form for"),
    day: Optional[int] = Query(
        None,
        ge=0,
        le=365,
        description="Override the post-op day to preview an earlier or later stage of recovery",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Build the day-appropriate check-in form from the episode's approved ruleset.

    Only parameters whose collection window (collect_from_day..collect_to_day)
    contains the effective day are returned, ordered and grouped exactly as
    meta.procedure_parameter specifies.
    """
    episode = await _load_episode(db, episode_id)
    effective_day = day if day is not None else episode["post_op_day"]

    params_result = await db.execute(
        text(
            """
            SELECT
                p.parameter_id,
                p.parameter_code,
                p.parameter_name,
                p.parameter_type,
                p.unit,
                p.value_min,
                p.value_max,
                p.decimal_places,
                pp.question_text,
                pp.display_section,
                pp.display_order,
                pp.is_mandatory,
                COALESCE((pp.scoring_config->>'emergency')::boolean, false) AS is_emergency,
                (:day BETWEEN pp.score_from_day AND pp.score_to_day) AS is_scored_today
            FROM meta.procedure_parameter pp
            JOIN meta.parameter p ON p.parameter_id = pp.parameter_id
            WHERE pp.ruleset_id = :ruleset_id
              AND p.is_active = true
              AND :day BETWEEN pp.collect_from_day AND pp.collect_to_day
            ORDER BY pp.display_order
            """
        ),
        {"ruleset_id": episode["ruleset_id"], "day": effective_day},
    )
    rows = params_result.mappings().all()

    options_by_param: Dict[int, List[OrdinalOption]] = {}
    ordinal_ids = [r["parameter_id"] for r in rows if r["parameter_type"] == "ordinal"]
    if ordinal_ids:
        opt_result = await db.execute(
            text(
                """
                SELECT parameter_id, option_code, option_label, ordinal_rank
                FROM meta.parameter_option
                WHERE parameter_id = ANY(:ids)
                ORDER BY parameter_id, ordinal_rank
                """
            ),
            {"ids": ordinal_ids},
        )
        for opt in opt_result.mappings().all():
            options_by_param.setdefault(opt["parameter_id"], []).append(
                OrdinalOption(
                    code=opt["option_code"],
                    label=opt["option_label"],
                    rank=opt["ordinal_rank"],
                )
            )

    sections: List[FormSection] = []
    section_index: Dict[str, FormSection] = {}
    for r in rows:
        parameter = FormParameter(
            parameter_id=r["parameter_id"],
            code=r["parameter_code"],
            name=r["parameter_name"],
            question_text=r["question_text"] or r["parameter_name"],
            type=r["parameter_type"],
            section=r["display_section"],
            unit=r["unit"],
            value_min=float(r["value_min"]) if r["value_min"] is not None else None,
            value_max=float(r["value_max"]) if r["value_max"] is not None else None,
            decimals=r["decimal_places"] or 0,
            is_mandatory=r["is_mandatory"],
            is_emergency=r["is_emergency"],
            is_scored_today=r["is_scored_today"],
            options=options_by_param.get(r["parameter_id"], []),
        )
        section = section_index.get(parameter.section)
        if section is None:
            section = FormSection(key=parameter.section, parameters=[])
            section_index[parameter.section] = section
            sections.append(section)
        section.parameters.append(parameter)

    submitted = await db.execute(
        text(
            """
            SELECT 1 FROM txn.patient_check_in
            WHERE episode_id = :episode_id AND day_after_discharge = :day
            LIMIT 1
            """
        ),
        {"episode_id": episode_id, "day": effective_day},
    )

    patient_name = episode["patient_name"]
    return CheckInForm(
        episode=EpisodeContext(
            episode_id=episode["episode_id"],
            patient_name=patient_name,
            first_name=patient_name.split(" ")[0],
            mrn=episode["mrn"],
            hospital_name=episode["hospital_name"],
            procedure_code=episode["procedure_code"],
            actual_post_op_day=episode["post_op_day"],
            monitoring_ends_on=episode["monitoring_ends_on"],
        ),
        ruleset_id=episode["ruleset_id"],
        effective_day=effective_day,
        simulated=day is not None and day != episode["post_op_day"],
        already_submitted_today=submitted.first() is not None,
        sections=sections,
    )

@router.post("", response_model=CheckInReceipt, status_code=status.HTTP_201_CREATED)
async def submit_checkin(payload: CheckInSubmit, db: AsyncSession = Depends(get_db)):
    """
    Persist a daily check-in.

    Unanswered parameters are omitted rather than sent as null, so a missing row
    in txn.patient_check_in_value keeps meaning "unknown" rather than "normal".
    Replaying the same idempotency_key returns the original submission instead of
    creating a duplicate.
    """
    episode = await _load_episode(db, payload.episode_id)
    if episode["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Episode is no longer active",
        )

    # Reject answers the ruleset does not collect on this day.
    if payload.values:
        allowed = await db.execute(
            text(
                """
                SELECT parameter_id FROM meta.procedure_parameter
                WHERE ruleset_id = :ruleset_id
                  AND :day BETWEEN collect_from_day AND collect_to_day
                """
            ),
            {"ruleset_id": episode["ruleset_id"], "day": payload.day_after_discharge},
        )
        allowed_ids = {r[0] for r in allowed.all()}
        submitted_ids = {v.parameter_id for v in payload.values}
        out_of_window = sorted(submitted_ids - allowed_ids)
        if out_of_window:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Parameters {out_of_window} are outside the collection window "
                    f"for day {payload.day_after_discharge}"
                ),
            )

    source = "synthetic" if payload.simulated else "patient"

    # Serialise submissions for this episode. Without it two concurrent same-day
    # check-ins each supersede the other and the day is left with no live row.
    await db.execute(
        text("SELECT 1 FROM txn.patient_episode WHERE episode_id = :episode_id FOR UPDATE"),
        {"episode_id": payload.episode_id},
    )

    inserted = await db.execute(
        text(
            """
            INSERT INTO txn.patient_check_in (
                episode_id, day_after_discharge, source, idempotency_key, captured_at
            ) VALUES (
                :episode_id, :day, :source, :key, now()
            )
            ON CONFLICT (episode_id, idempotency_key) WHERE idempotency_key IS NOT NULL
            DO NOTHING
            RETURNING check_in_id, submitted_at, source, day_after_discharge
            """
        ),
        {
            "episode_id": payload.episode_id,
            "day": payload.day_after_discharge,
            "source": source,
            "key": payload.idempotency_key,
        },
    )
    row = inserted.mappings().first()

    if row is None:
        existing = await db.execute(
            text(
                """
                SELECT c.check_in_id, c.submitted_at, c.source, c.day_after_discharge,
                       (SELECT count(*) FROM txn.patient_check_in_value v
                        WHERE v.check_in_id = c.check_in_id) AS value_count
                FROM txn.patient_check_in c
                WHERE c.episode_id = :episode_id AND c.idempotency_key = :key
                """
            ),
            {"episode_id": payload.episode_id, "key": payload.idempotency_key},
        )
        prior = existing.mappings().one()
        await db.commit()
        return CheckInReceipt(
            check_in_id=prior["check_in_id"],
            episode_id=payload.episode_id,
            day_after_discharge=prior["day_after_discharge"],
            source=prior["source"],
            submitted_at=prior["submitted_at"],
            values_recorded=prior["value_count"],
            superseded_count=0,
            duplicate=True,
        )

    # A correction later the same day replaces the earlier submission; the
    # check_in_by_day index reads the newest row that is still live.
    superseded = await db.execute(
        text(
            """
            UPDATE txn.patient_check_in
            SET is_superseded = true
            WHERE episode_id = :episode_id
              AND day_after_discharge = :day
              AND check_in_id <> :new_id
              AND is_superseded = false
            """
        ),
        {
            "episode_id": payload.episode_id,
            "day": row["day_after_discharge"],
            "new_id": row["check_in_id"],
        },
    )
    superseded_count = superseded.rowcount

    if payload.values:
        await db.execute(
            text(
                """
                INSERT INTO txn.patient_check_in_value (
                    check_in_id, parameter_id, value_num, value_bool, value_code
                ) VALUES (
                    :check_in_id, :parameter_id, :value_num, :value_bool, :value_code
                )
                """
            ),
            [
                {
                    "check_in_id": row["check_in_id"],
                    "parameter_id": v.parameter_id,
                    "value_num": v.value_num,
                    "value_bool": v.value_bool,
                    "value_code": v.value_code,
                }
                for v in payload.values
            ],
        )

    await db.commit()

    return CheckInReceipt(
        check_in_id=row["check_in_id"],
        episode_id=payload.episode_id,
        day_after_discharge=row["day_after_discharge"],
        source=row["source"],
        submitted_at=row["submitted_at"],
        values_recorded=len(payload.values),
        superseded_count=superseded_count,
        duplicate=False,
    )
