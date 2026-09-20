"""
The platform admin area: hospitals and scoring rulesets across every tenant.

Every endpoint runs as eras_platform (see get_app_admin), which cannot read
patient data; patient numbers arrive as counts from meta.platform_usage().
Rulesets change only as drafts. Approving a draft retires the version before
it, and patients already enrolled stay scored by the version they joined under.

The platform role ends at commit, so each endpoint builds its response first.
"""

import json
from typing import Dict, List, Sequence

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.security import AuthenticatedAppAdmin, get_app_admin, get_password_hash
from app.db.session import get_db
from app.schemas.app_admin import (
    ApprovalRequest,
    AvailableParameter,
    BindingInput,
    DraftCreate,
    HospitalAccount,
    HospitalCreate,
    HospitalFields,
    HospitalUpdate,
    PlatformHospital,
    PlatformHospitalDetail,
    PlatformOptions,
    PlatformProcedureRulesets,
    PlatformRulesetDetail,
    PlatformRulesetVersion,
    ProcedureOption,
    RulesetBinding,
    RulesetUpdate,
)
from app.schemas.clinician import ClinicianCreate
from app.services.scoring import describe_scoring, describe_trends
from app.services.scoring_config import (
    ScoringConfigError,
    validate_composite_config,
    validate_scoring_config,
)

router = APIRouter(prefix="/app-admin", tags=["App admin"])

PRIVACY_LAWS = ["DPDP-2023", "HIPAA"]


@router.get("/options", response_model=PlatformOptions)
async def platform_options(
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    procedures = (await db.execute(text("""
        SELECT sp.procedure_code, sp.procedure_name,
               (SELECT r.version FROM meta.ruleset r
                WHERE r.procedure_id = sp.procedure_id AND r.status = 'approved') AS approved_version
        FROM meta.surgical_procedure sp
        WHERE sp.is_active
        ORDER BY sp.procedure_name
    """))).mappings().all()
    timezones = (await db.execute(text("""
        SELECT name FROM pg_timezone_names
        WHERE name ~ '^(Africa|America|Asia|Atlantic|Australia|Europe|Indian|Pacific)/' OR name = 'UTC'
        ORDER BY name
    """))).scalars().all()
    return PlatformOptions(
        procedures=[ProcedureOption(**p) for p in procedures],
        privacy_laws=PRIVACY_LAWS,
        timezones=list(timezones),
    )


# ------------------------------------------------------------------ hospitals

HOSPITAL_SQL = """
    WITH usage AS (
        SELECT hospital_id, sum(active_episodes)::int AS active_patients
        FROM meta.platform_usage()
        GROUP BY hospital_id
    )
    SELECT h.hospital_id, h.hospital_code, h.hospital_name, h.city, h.timezone, h.ack_window_secs,
           h.privacy_law, h.is_active, h.created_at,
           coalesce((SELECT array_agg(sp.procedure_code ORDER BY sp.procedure_code)
                     FROM meta.hospital_procedure hp
                     JOIN meta.surgical_procedure sp ON sp.procedure_id = hp.procedure_id
                     WHERE hp.hospital_id = h.hospital_id AND hp.is_active), '{}') AS procedure_codes,
           (SELECT count(*) FROM meta.admin_user u
            WHERE u.hospital_id = h.hospital_id AND u.is_active) AS account_count,
           coalesce(usage.active_patients, 0) AS active_patients
    FROM meta.hospital h
    LEFT JOIN usage ON usage.hospital_id = h.hospital_id
"""


async def _hospital(db: AsyncSession, hospital_id: int) -> PlatformHospitalDetail:
    row = (await db.execute(text(HOSPITAL_SQL + " WHERE h.hospital_id = :id"), {"id": hospital_id})).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Hospital not found")
    accounts = (await db.execute(text("""
        SELECT admin_user_id, email, full_name, role, is_active, created_at
        FROM meta.admin_user
        WHERE hospital_id = :id
        ORDER BY is_active DESC, role DESC, full_name
    """), {"id": hospital_id})).mappings().all()
    return PlatformHospitalDetail(**row, accounts=[HospitalAccount(**a) for a in accounts])


async def _checked_procedures(db: AsyncSession, fields: HospitalFields) -> List[int]:
    """Validate the timezone and procedure codes; return the procedures' ids."""
    known_zone = (await db.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name = :tz)"), {"tz": fields.timezone}
    )).scalar_one()
    if not known_zone:
        raise HTTPException(422, detail=f"Unknown timezone {fields.timezone!r}; use an IANA name such as Asia/Kolkata")

    codes = sorted(set(fields.procedure_codes))
    found: Dict[str, int] = dict((await db.execute(text("""
        SELECT procedure_code, procedure_id FROM meta.surgical_procedure
        WHERE procedure_code = ANY(:codes) AND is_active
    """), {"codes": codes})).all())
    missing = [c for c in codes if c not in found]
    if missing:
        raise HTTPException(422, detail=f"Unknown procedure {', '.join(missing)}")
    return list(found.values())


async def _offer_procedures(db: AsyncSession, hospital_id: int, procedure_ids: Sequence[int]) -> None:
    """Offer exactly these procedures. Rows are switched off rather than deleted, keeping the history."""
    await db.execute(text("""
        UPDATE meta.hospital_procedure SET is_active = (procedure_id = ANY(:ids)) WHERE hospital_id = :h
    """), {"h": hospital_id, "ids": list(procedure_ids)})
    if procedure_ids:
        await db.execute(text("""
            INSERT INTO meta.hospital_procedure (hospital_id, procedure_id)
            SELECT :h, unnest(CAST(:ids AS integer[]))
            ON CONFLICT (hospital_id, procedure_id) DO UPDATE SET is_active = true
        """), {"h": hospital_id, "ids": list(procedure_ids)})


@router.get("/hospitals", response_model=List[PlatformHospital])
async def list_hospitals(
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(text(HOSPITAL_SQL + " ORDER BY h.is_active DESC, h.hospital_name"))).mappings().all()
    return [PlatformHospital(**r) for r in rows]


@router.get("/hospitals/{hospital_id}", response_model=PlatformHospitalDetail)
async def get_hospital(
    hospital_id: int,
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _hospital(db, hospital_id)


@router.post("/hospitals", response_model=PlatformHospitalDetail, status_code=status.HTTP_201_CREATED)
async def create_hospital(
    new: HospitalCreate,
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    procedure_ids = await _checked_procedures(db, new)
    try:
        hospital_id = (await db.execute(text("""
            INSERT INTO meta.hospital
                (hospital_code, hospital_name, city, timezone, ack_window_secs, privacy_law, is_active)
            VALUES (:code, :name, :city, :tz, :window, :law, :active)
            RETURNING hospital_id
        """), {
            "code": new.hospital_code, "name": new.hospital_name, "city": new.city, "tz": new.timezone,
            "window": new.ack_window_secs, "law": new.privacy_law, "active": new.is_active,
        })).scalar_one()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Hospital code {new.hospital_code} is already in use")

    await _offer_procedures(db, hospital_id, procedure_ids)
    detail = await _hospital(db, hospital_id)
    await db.commit()
    return detail


@router.put("/hospitals/{hospital_id}", response_model=PlatformHospitalDetail)
async def update_hospital(
    hospital_id: int,
    changes: HospitalUpdate,
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    """Deactivating a hospital signs its clinicians out and stops them signing in."""
    procedure_ids = await _checked_procedures(db, changes)
    updated = (await db.execute(text("""
        UPDATE meta.hospital
           SET hospital_name = :name, city = :city, timezone = :tz, ack_window_secs = :window,
               privacy_law = :law, is_active = :active
         WHERE hospital_id = :id
        RETURNING hospital_id
    """), {
        "id": hospital_id, "name": changes.hospital_name, "city": changes.city, "tz": changes.timezone,
        "window": changes.ack_window_secs, "law": changes.privacy_law, "active": changes.is_active,
    })).scalar_one_or_none()
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Hospital not found")

    await _offer_procedures(db, hospital_id, procedure_ids)
    detail = await _hospital(db, hospital_id)
    await db.commit()
    return detail


@router.post("/hospitals/{hospital_id}/accounts", response_model=PlatformHospitalDetail,
             status_code=status.HTTP_201_CREATED)
async def create_hospital_account(
    hospital_id: int,
    new: ClinicianCreate,
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    """A clinician account at a hospital, typically its first superadmin, who can then add the rest."""
    exists = (await db.execute(text("SELECT EXISTS (SELECT 1 FROM meta.hospital WHERE hospital_id = :id)"),
                               {"id": hospital_id})).scalar_one()
    if not exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Hospital not found")

    hashed = await run_in_threadpool(get_password_hash, new.password)
    try:
        await db.execute(text("""
            INSERT INTO meta.admin_user (hospital_id, email, hashed_password, full_name, role)
            VALUES (:h, :email, :pwd, :name, :role)
        """), {"h": hospital_id, "email": new.email, "pwd": hashed, "name": new.full_name, "role": new.role})
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This hospital already has an account with that email")

    detail = await _hospital(db, hospital_id)
    await db.commit()
    return detail


# ------------------------------------------------------------------- rulesets

VERSION_SQL = """
    WITH usage AS (
        SELECT ruleset_id, sum(active_episodes)::int AS active_episodes, sum(total_episodes)::int AS total_episodes
        FROM meta.platform_usage()
        GROUP BY ruleset_id
    )
    SELECT sp.procedure_code, sp.procedure_name, sp.observation_days,
           r.ruleset_id, r.version, r.status, r.review_at, r.critical_at, r.max_points_per_parameter,
           r.composite_config, r.approved_by, r.approved_at, r.notes, r.created_at,
           (SELECT count(*) FROM meta.procedure_parameter pp WHERE pp.ruleset_id = r.ruleset_id) AS parameter_count,
           coalesce(u.active_episodes, 0) AS active_episodes,
           coalesce(u.total_episodes, 0) AS total_episodes
    FROM meta.ruleset r
    JOIN meta.surgical_procedure sp ON sp.procedure_id = r.procedure_id
    LEFT JOIN usage u ON u.ruleset_id = r.ruleset_id
"""

VERSION_FIELDS = set(PlatformRulesetVersion.model_fields)


async def _ruleset(db: AsyncSession, ruleset_id: int) -> PlatformRulesetDetail:
    row = (await db.execute(text(VERSION_SQL + " WHERE r.ruleset_id = :id"), {"id": ruleset_id})).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ruleset not found")

    bindings = (await db.execute(text("""
        SELECT p.parameter_code, p.parameter_name, p.parameter_type, p.unit,
               pp.display_section, pp.display_order, pp.collect_from_day, pp.collect_to_day,
               pp.score_from_day, pp.score_to_day, pp.parameter_weight AS weight, pp.is_mandatory,
               pp.question_text, pp.nurse_script, pp.scoring_config
        FROM meta.procedure_parameter pp
        JOIN meta.parameter p ON p.parameter_id = pp.parameter_id
        WHERE pp.ruleset_id = :id
        ORDER BY pp.display_order
    """), {"id": ruleset_id})).mappings().all()

    available = (await db.execute(text("""
        SELECT p.parameter_code, p.parameter_name, p.parameter_type, p.unit,
               coalesce((SELECT array_agg(o.option_code ORDER BY o.ordinal_rank)
                         FROM meta.parameter_option o WHERE o.parameter_id = p.parameter_id), '{}') AS option_codes
        FROM meta.parameter p
        WHERE p.is_active
          AND NOT EXISTS (SELECT 1 FROM meta.procedure_parameter pp
                          WHERE pp.ruleset_id = :id AND pp.parameter_id = p.parameter_id)
        ORDER BY p.parameter_name
    """), {"id": ruleset_id})).mappings().all()

    return PlatformRulesetDetail(
        **row,
        composite_summary=describe_trends(row["composite_config"] or {}),
        bindings=[
            RulesetBinding(**b, scoring_summary=describe_scoring(b["scoring_config"]),
                           direction=b["scoring_config"].get("direction"))
            for b in bindings
        ],
        available_parameters=[AvailableParameter(**a) for a in available],
    )


async def _draft(db: AsyncSession, ruleset_id: int):
    """The ruleset, if it is still a draft; published versions never change."""
    row = (await db.execute(text("""
        SELECT r.ruleset_id, r.procedure_id, r.status, r.version, r.composite_config, sp.observation_days
        FROM meta.ruleset r
        JOIN meta.surgical_procedure sp ON sp.procedure_id = r.procedure_id
        WHERE r.ruleset_id = :id
    """), {"id": ruleset_id})).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ruleset not found")
    if row["status"] != "draft":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Version {row['version']} is {row['status']} and cannot change. Start a new draft from it instead.",
        )
    return row


async def _parameter(db: AsyncSession, code: str):
    row = (await db.execute(text("""
        SELECT p.parameter_id, p.parameter_type,
               coalesce((SELECT array_agg(o.option_code ORDER BY o.ordinal_rank)
                         FROM meta.parameter_option o WHERE o.parameter_id = p.parameter_id), '{}') AS option_codes
        FROM meta.parameter p
        WHERE p.parameter_code = :code AND p.is_active
    """), {"code": code})).mappings().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"No measure called {code}")
    return row


def _check_rule(code: str, config, parameter_type: str, option_codes, observation_days: int,
                collect_to_day: int) -> None:
    if collect_to_day > observation_days:
        raise HTTPException(422, detail=f"{code}: monitoring lasts {observation_days} days, so it cannot be asked on day {collect_to_day}")
    try:
        validate_scoring_config(config, parameter_type, option_codes, observation_days)
    except ScoringConfigError as err:
        raise HTTPException(422, detail=f"{code}: {err}")


@router.get("/rulesets", response_model=List[PlatformProcedureRulesets])
async def list_rulesets(
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    procedures = (await db.execute(text("""
        SELECT sp.procedure_code, sp.procedure_name, sp.observation_days,
               (SELECT count(*) FROM meta.hospital_procedure hp
                WHERE hp.procedure_id = sp.procedure_id AND hp.is_active) AS hospitals_offering
        FROM meta.surgical_procedure sp
        WHERE sp.is_active
        ORDER BY sp.procedure_name
    """))).mappings().all()
    versions = (await db.execute(text(
        VERSION_SQL + " ORDER BY array_position(ARRAY['draft', 'approved', 'retired'], r.status), r.created_at DESC"
    ))).mappings().all()

    by_procedure: Dict[str, List[PlatformRulesetVersion]] = {}
    for v in versions:
        by_procedure.setdefault(v["procedure_code"], []).append(
            PlatformRulesetVersion(**{k: v[k] for k in VERSION_FIELDS})
        )
    return [PlatformProcedureRulesets(**p, versions=by_procedure.get(p["procedure_code"], [])) for p in procedures]


@router.get("/rulesets/{ruleset_id}", response_model=PlatformRulesetDetail)
async def get_ruleset(
    ruleset_id: int,
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _ruleset(db, ruleset_id)


@router.post("/rulesets/{ruleset_id}/drafts", response_model=PlatformRulesetDetail,
             status_code=status.HTTP_201_CREATED)
async def start_draft(
    ruleset_id: int,
    new: DraftCreate,
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    """A new draft version, copied from this one: its cut-offs and every measure's rule."""
    try:
        draft_id = (await db.execute(text("""
            INSERT INTO meta.ruleset (procedure_id, version, review_at, critical_at,
                                      max_points_per_parameter, composite_config, status, notes)
            SELECT procedure_id, :version, review_at, critical_at,
                   max_points_per_parameter, composite_config, 'draft', :notes
            FROM meta.ruleset
            WHERE ruleset_id = :id
            RETURNING ruleset_id
        """), {"id": ruleset_id, "version": new.version, "notes": new.notes})).scalar_one_or_none()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Version {new.version} already exists for this procedure")
    if draft_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ruleset not found")

    await db.execute(text("""
        INSERT INTO meta.procedure_parameter
            (ruleset_id, parameter_id, display_order, display_section, collect_from_day, collect_to_day,
             score_from_day, score_to_day, is_mandatory, parameter_weight, scoring_config, question_text, nurse_script)
        SELECT :draft, parameter_id, display_order, display_section, collect_from_day, collect_to_day,
               score_from_day, score_to_day, is_mandatory, parameter_weight, scoring_config, question_text, nurse_script
        FROM meta.procedure_parameter
        WHERE ruleset_id = :id
    """), {"draft": draft_id, "id": ruleset_id})

    detail = await _ruleset(db, draft_id)
    await db.commit()
    return detail


@router.patch("/rulesets/{ruleset_id}", response_model=PlatformRulesetDetail)
async def update_draft(
    ruleset_id: int,
    changes: RulesetUpdate,
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    draft = await _draft(db, ruleset_id)
    notes_given = "notes" in changes.model_fields_set
    if changes.composite_config is not None:
        try:
            validate_composite_config(changes.composite_config, draft["observation_days"])
        except ScoringConfigError as err:
            raise HTTPException(422, detail=f"Cross-measure signals: {err}")
    try:
        await db.execute(text("""
            UPDATE meta.ruleset
               SET review_at = coalesce(:review_at, review_at),
                   critical_at = coalesce(:critical_at, critical_at),
                   max_points_per_parameter = coalesce(:max_points, max_points_per_parameter),
                   composite_config = coalesce(CAST(:composite AS jsonb), composite_config),
                   notes = CASE WHEN :notes_given THEN :notes ELSE notes END
             WHERE ruleset_id = :id
        """), {
            "id": ruleset_id, "review_at": changes.review_at, "critical_at": changes.critical_at,
            "max_points": changes.max_points_per_parameter, "notes_given": notes_given,
            "composite": None if changes.composite_config is None else json.dumps(changes.composite_config),
            "notes": (changes.notes or "").strip() or None,
        })
    except IntegrityError:
        await db.rollback()
        raise HTTPException(422, detail="The critical cut-off must be higher than the review cut-off")

    detail = await _ruleset(db, ruleset_id)
    await db.commit()
    return detail


@router.put("/rulesets/{ruleset_id}/parameters/{parameter_code}", response_model=PlatformRulesetDetail)
async def save_binding(
    ruleset_id: int,
    parameter_code: str,
    binding: BindingInput,
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add a measure to a draft, or change how it is asked and scored."""
    draft = await _draft(db, ruleset_id)
    param = await _parameter(db, parameter_code)
    _check_rule(parameter_code, binding.scoring_config, param["parameter_type"], param["option_codes"],
                draft["observation_days"], binding.collect_to_day)

    try:
        await db.execute(text("""
            INSERT INTO meta.procedure_parameter
                (ruleset_id, parameter_id, display_order, display_section, collect_from_day, collect_to_day,
                 score_from_day, score_to_day, is_mandatory, parameter_weight, scoring_config,
                 question_text, nurse_script)
            VALUES (:ruleset, :param, :order, :section, :c_from, :c_to, :s_from, :s_to, :mandatory, :weight,
                    CAST(:config AS jsonb), :question, :script)
            ON CONFLICT (ruleset_id, parameter_id) DO UPDATE SET
                display_order = excluded.display_order, display_section = excluded.display_section,
                collect_from_day = excluded.collect_from_day, collect_to_day = excluded.collect_to_day,
                score_from_day = excluded.score_from_day, score_to_day = excluded.score_to_day,
                is_mandatory = excluded.is_mandatory, parameter_weight = excluded.parameter_weight,
                scoring_config = excluded.scoring_config, question_text = excluded.question_text,
                nurse_script = excluded.nurse_script
        """), {
            "ruleset": ruleset_id, "param": param["parameter_id"], "order": binding.display_order,
            "section": binding.display_section, "c_from": binding.collect_from_day, "c_to": binding.collect_to_day,
            "s_from": binding.score_from_day, "s_to": binding.score_to_day, "mandatory": binding.is_mandatory,
            "weight": binding.weight, "config": json.dumps(binding.scoring_config),
            "question": binding.question_text, "script": (binding.nurse_script or "").strip() or None,
        })
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"Another measure is already at position {binding.display_order}")

    detail = await _ruleset(db, ruleset_id)
    await db.commit()
    return detail


@router.delete("/rulesets/{ruleset_id}/parameters/{parameter_code}", response_model=PlatformRulesetDetail)
async def remove_binding(
    ruleset_id: int,
    parameter_code: str,
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    await _draft(db, ruleset_id)
    param = await _parameter(db, parameter_code)
    removed = (await db.execute(text("""
        DELETE FROM meta.procedure_parameter WHERE ruleset_id = :ruleset AND parameter_id = :param
    """), {"ruleset": ruleset_id, "param": param["parameter_id"]})).rowcount
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{parameter_code} is not in this version")

    detail = await _ruleset(db, ruleset_id)
    await db.commit()
    return detail


@router.post("/rulesets/{ruleset_id}/approve", response_model=PlatformRulesetDetail)
async def approve_draft(
    ruleset_id: int,
    approval: ApprovalRequest,
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Publish a draft. New enrollments use it from now on; the version it replaces
    is retired, and patients enrolled under that version stay on it.
    """
    draft = await _draft(db, ruleset_id)
    bindings = (await db.execute(text("""
        SELECT p.parameter_code, p.parameter_type, pp.scoring_config, pp.collect_to_day,
               coalesce((SELECT array_agg(o.option_code ORDER BY o.ordinal_rank)
                         FROM meta.parameter_option o WHERE o.parameter_id = p.parameter_id), '{}') AS option_codes
        FROM meta.procedure_parameter pp
        JOIN meta.parameter p ON p.parameter_id = pp.parameter_id
        WHERE pp.ruleset_id = :id
    """), {"id": ruleset_id})).mappings().all()
    if not bindings:
        raise HTTPException(422, detail="Add at least one measure before approving")
    for b in bindings:
        _check_rule(b["parameter_code"], b["scoring_config"], b["parameter_type"], b["option_codes"],
                    draft["observation_days"], b["collect_to_day"])
    try:
        validate_composite_config(draft["composite_config"] or {}, draft["observation_days"])
    except ScoringConfigError as err:
        raise HTTPException(422, detail=f"Cross-measure signals: {err}")

    try:
        await db.execute(text("""
            UPDATE meta.ruleset SET status = 'retired' WHERE procedure_id = :p AND status = 'approved'
        """), {"p": draft["procedure_id"]})
        await db.execute(text("""
            UPDATE meta.ruleset SET status = 'approved', approved_by = :by, approved_at = now()
            WHERE ruleset_id = :id
        """), {"id": ruleset_id, "by": approval.approved_by})
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Another version was approved at the same moment. Refresh and check.")

    detail = await _ruleset(db, ruleset_id)
    await db.commit()
    return detail


@router.delete("/rulesets/{ruleset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def discard_draft(
    ruleset_id: int,
    _: AuthenticatedAppAdmin = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
):
    await _draft(db, ruleset_id)
    await db.execute(text("DELETE FROM meta.ruleset WHERE ruleset_id = :id AND status = 'draft'"), {"id": ruleset_id})
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
