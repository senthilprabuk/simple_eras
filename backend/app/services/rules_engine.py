"""
Scores a check-in against its ruleset and raises an alert when it warrants one.

Basic engine, run inside the check-in request:
  1. A yes to an emergency question (scoring_config.emergency) -> emergency.
  2. A yes to a red-flag question at the top binary score     -> critical.
  3. Other measures are scored by band (flat, by post-op day, or relative to
     the discharge baseline), weighted, capped per measure, and the total is
     compared with the ruleset's review_at / critical_at cut-offs.
  4. Every submission gets an evaluation row; a non-normal tier raises an
     alert, deduplicated against a live alert with the same reasons.

Not built yet: trend detectors (fever_returned, drop_from_personal_best),
milestones, hysteresis across days, and the missed-check-in sweep.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scoring import bands_for_day

# A yes/no flag scoring this much bypasses the weighted total.
OVERRIDE_SCORE = 3

@dataclass
class Binding:
    parameter_id: int
    code: str
    name: str
    type: str
    unit: Optional[str]
    weight: int
    score_from: int
    score_to: int
    config: Dict[str, Any]

@dataclass
class Evaluation:
    tier: str
    total_score: int
    is_override: bool
    reasons: List[Dict[str, Any]]
    reason_key: str

def band_score(bands: Sequence[Sequence[float]], value: float) -> int:
    for low, high, score in bands:
        if low <= value < high:
            return int(score)
    return 0

def _unit(binding: Binding) -> str:
    return {"C": " °C", "bpm": " bpm", "%": "%"}.get(binding.unit or "", "")

def evaluate(
    bindings: Sequence[Binding],
    answers: Dict[str, Any],
    baselines: Dict[str, float],
    day: int,
    review_at: int,
    critical_at: int,
    max_points: int,
) -> Evaluation:
    """Pure scoring: the same answers always give the same tier and reasons."""
    reasons: List[Dict[str, Any]] = []
    total = 0
    override: Optional[str] = None

    for b in bindings:
        if not (b.score_from <= day <= b.score_to) or answers.get(b.code) is None:
            continue
        value, config = answers[b.code], b.config

        if b.type == "boolean":
            if value is not True:
                continue
            score = int(config.get("binary_score", 0))
            if config.get("emergency"):
                override = "emergency"
                reasons.append({"name": b.code, "detail": f"{b.name}: yes (emergency)", "score": score})
                continue
            if score >= OVERRIDE_SCORE and override is None:
                override = "critical"
            detail = f"{b.name}: yes"
        elif b.type == "numeric":
            bands = bands_for_day(config["bands_by_day"], day) if "bands_by_day" in config else config.get("bands")
            if not bands:
                continue
            measured = float(value)
            detail = f"{b.name} {measured:g}{_unit(b)}"
            if config.get("relative_to_baseline"):
                if b.code not in baselines:
                    continue
                measured -= baselines[b.code]
                detail += f", {measured:+g} from discharge"
            score = band_score(bands, measured)
        else:
            continue

        if score <= 0:
            continue
        points = min(score * b.weight, max_points)
        total += points
        reasons.append({"name": b.code, "detail": detail, "score": score, "points": points})

    tier = override or ("critical" if total >= critical_at else "review" if total >= review_at else "normal")
    names = sorted(r["name"] for r in reasons)
    reason_key = hashlib.sha1("|".join(names).encode()).hexdigest()[:16] if names else "none"
    return Evaluation(tier, total, override is not None, reasons, reason_key)

async def evaluate_check_in(
    db: AsyncSession,
    *,
    episode_id: UUID,
    check_in_id: UUID,
    ruleset_id: int,
    day: int,
    answers_by_parameter: Dict[int, Any],
) -> Tuple[Evaluation, Optional[UUID]]:
    """Score one submission, store the evaluation, and raise an alert if warranted. Caller commits."""
    ruleset = (await db.execute(text("""
        SELECT review_at, critical_at, max_points_per_parameter FROM meta.ruleset WHERE ruleset_id = :r
    """), {"r": ruleset_id})).mappings().one()

    bindings = [Binding(**r) for r in (await db.execute(text("""
        SELECT p.parameter_id, p.parameter_code AS code, p.parameter_name AS name, p.parameter_type AS type,
               p.unit, pp.parameter_weight AS weight, pp.score_from_day AS score_from,
               pp.score_to_day AS score_to, pp.scoring_config AS config
        FROM meta.procedure_parameter pp
        JOIN meta.parameter p ON p.parameter_id = pp.parameter_id
        WHERE pp.ruleset_id = :r
        ORDER BY pp.display_order
    """), {"r": ruleset_id})).mappings().all()]

    baselines = {r["parameter_code"]: float(r["value_num"]) for r in (await db.execute(text("""
        SELECT p.parameter_code, b.value_num
        FROM txn.episode_baseline b JOIN meta.parameter p ON p.parameter_id = b.parameter_id
        WHERE b.episode_id = :e AND b.value_num IS NOT NULL
    """), {"e": episode_id})).mappings().all()}

    codes = {b.parameter_id: b.code for b in bindings}
    answers = {codes[pid]: value for pid, value in answers_by_parameter.items() if pid in codes}

    result = evaluate(bindings, answers, baselines, day, ruleset["review_at"], ruleset["critical_at"],
                      ruleset["max_points_per_parameter"])

    evaluation_id = (await db.execute(text("""
        INSERT INTO txn.check_in_evaluation
            (check_in_id, episode_id, ruleset_id, day_after_discharge, tier, total_score,
             is_override, reasons, reason_key)
        VALUES (:c, :e, :r, :d, :tier, :total, :override, CAST(:reasons AS jsonb), :key)
        RETURNING evaluation_id
    """), {
        "c": check_in_id, "e": episode_id, "r": ruleset_id, "d": day, "tier": result.tier,
        "total": result.total_score, "override": result.is_override,
        "reasons": json.dumps(result.reasons), "key": result.reason_key,
    })).scalar_one()

    alert_id = None
    if result.tier != "normal":
        # One live alert per reason set: a repeat report of the same problem
        # does not stack up a second copy in the queue.
        alert_id = (await db.execute(text("""
            INSERT INTO txn.alert (episode_id, evaluation_id, tier, reason_key)
            VALUES (:e, :ev, :tier, :key)
            ON CONFLICT (episode_id, reason_key) WHERE status IN ('open', 'acknowledged') DO NOTHING
            RETURNING alert_id
        """), {"e": episode_id, "ev": evaluation_id, "tier": result.tier, "key": result.reason_key})).scalar_one_or_none()

    return result, alert_id
