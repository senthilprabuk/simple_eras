"""
Scoring rulesets, read-only. Rules change through a new version and clinical
approval, not by editing an approved ruleset in place, so there is no write API.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedAdmin, get_current_admin
from app.db.session import get_db
from app.schemas.ruleset import RulesetDetail, RulesetParameter, RulesetSummary
from app.services.scoring import describe_scoring

router = APIRouter(prefix="/rulesets", tags=["Rulesets"])

# Only rulesets for procedures this hospital offers; RLS limits hospital_procedure
# to the caller's own hospital.
SUMMARY_SQL = """
    SELECT
        r.ruleset_id, sp.procedure_code, sp.procedure_name, sp.observation_days,
        r.version, r.status, r.review_at, r.critical_at, r.max_points_per_parameter,
        r.approved_by, r.approved_at, r.notes,
        (SELECT count(*) FROM meta.procedure_parameter pp WHERE pp.ruleset_id = r.ruleset_id) AS parameter_count,
        (SELECT count(*) FROM txn.patient_episode e
         WHERE e.ruleset_id = r.ruleset_id AND e.hospital_id = :h_id) AS episodes_using
    FROM meta.ruleset r
    JOIN meta.surgical_procedure sp ON sp.procedure_id = r.procedure_id
    JOIN meta.hospital_procedure hp ON hp.procedure_id = r.procedure_id AND hp.hospital_id = :h_id
"""

@router.get("", response_model=List[RulesetSummary])
async def list_rulesets(
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        text(SUMMARY_SQL + " ORDER BY sp.procedure_name, (r.status = 'approved') DESC, r.created_at DESC"),
        {"h_id": current_admin.hospital_id},
    )).mappings().all()
    return [RulesetSummary(**r) for r in rows]

@router.get("/{ruleset_id}", response_model=RulesetDetail)
async def get_ruleset(
    ruleset_id: int,
    current_admin: AuthenticatedAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    summary = (await db.execute(
        text(SUMMARY_SQL + " WHERE r.ruleset_id = :ruleset_id"),
        {"h_id": current_admin.hospital_id, "ruleset_id": ruleset_id},
    )).mappings().first()
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ruleset not found")

    rows = (await db.execute(text("""
        SELECT p.parameter_code, p.parameter_name, p.parameter_type, p.unit,
               pp.display_section, pp.display_order, pp.collect_from_day, pp.collect_to_day,
               pp.score_from_day, pp.score_to_day, pp.parameter_weight, pp.is_mandatory,
               pp.question_text, pp.scoring_config
        FROM meta.procedure_parameter pp
        JOIN meta.parameter p ON p.parameter_id = pp.parameter_id
        WHERE pp.ruleset_id = :ruleset_id
        ORDER BY pp.display_order
    """), {"ruleset_id": ruleset_id})).mappings().all()

    return RulesetDetail(
        **summary,
        parameters=[
            RulesetParameter(
                code=r["parameter_code"],
                name=r["parameter_name"],
                type=r["parameter_type"],
                unit=r["unit"],
                section=r["display_section"],
                display_order=r["display_order"],
                collect_from_day=r["collect_from_day"],
                collect_to_day=r["collect_to_day"],
                score_from_day=r["score_from_day"],
                score_to_day=r["score_to_day"],
                weight=r["parameter_weight"],
                is_mandatory=r["is_mandatory"],
                is_emergency=bool(r["scoring_config"].get("emergency")),
                question_text=r["question_text"],
                scoring_summary=describe_scoring(r["scoring_config"]),
                scoring_config=r["scoring_config"],
            )
            for r in rows
        ],
    )
