"""
Scores one check-in against its ruleset and raises an alert when it warrants one.

Two stages, in strict order:

  1. Hard overrides. An emergency answer, or any signal at the top band, decides
     the tier on its own and never reaches the weighted sum.
  2. A weighted total across everything else, compared with the ruleset's
     review_at and critical_at cut-offs.

A total on its own is not enough. A genuinely critical finding can be diluted
below the cut-off by good scores elsewhere, a bare number tells a nurse nothing
actionable, and a false positive cannot be traced back to the weight that caused
it. So every decision comes back as a tier plus the named reasons behind it, and
the number stays internal.

The evaluator is pure: reading, window and ruleset in, tier and reasons out. That
is what makes it exhaustively testable without a database, a device or a patient,
and what lets a stored decision be reconstructed from its ruleset version years
later. `evaluate_check_in` is the thin database wrapper around it, and the missed
check-in sweep calls the same function with an all-unknown reading rather than
carrying a second copy of the rules that would diverge at the first edit.

Order inside `evaluate` is load-bearing; see the comments on each step.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scoring import band_score, bands_for_day
from app.services.trends import COMPOSITE_DETECTORS, Series, detect, worsening

# A signal at the top band decides the tier by itself, whatever else is normal.
OVERRIDE_SCORE = 3

# Below this fraction of the day's questions answered, the evaluation is reported
# as low confidence: what is missing is unknown, not normal.
LOW_CONFIDENCE_COVERAGE = 0.6

TIER_RANK = {"normal": 0, "missed": 1, "review": 2, "critical": 3, "emergency": 4}

UNIT_SUFFIX = {"C": " °C", "bpm": " bpm", "%": "%"}


@dataclass(frozen=True)
class Binding:
    """One measure as this ruleset asks and scores it."""

    parameter_id: int
    code: str
    name: str
    type: str
    unit: Optional[str]
    weight: int
    score_from: int
    score_to: int
    config: Dict[str, Any]
    option_ranks: Dict[str, int] = field(default_factory=dict)

    @property
    def direction(self) -> Optional[str]:
        return self.config.get("direction")

    @property
    def trends(self) -> List[Dict[str, Any]]:
        """
        This measure's trend signals. The older shape, where a lone detector sits
        at the top of the rule, is read as one trend carrying the measure's own
        weight, so rulesets approved before trends existed keep scoring the same.
        """
        declared = list(self.config.get("trends") or [])
        if "detector" in self.config:
            declared.append({"name": self.code, "weight": self.weight, **self.config})
        return declared


@dataclass(frozen=True)
class Reading:
    """One submission: what the patient answered on one post-operative day."""

    day: int
    answers: Dict[str, Any] = field(default_factory=dict)
    asked: Tuple[str, ...] = ()  # what the form put in front of them, for coverage


@dataclass(frozen=True)
class Window:
    """
    The patient's own history, indexed by post-operative day.

    Indexed by day and never by "the last three submissions": otherwise a patient
    who skips a week has day 9 silently compared against day 2 and every detector
    quietly lies. A day with no answer is simply absent, never a zero.
    """

    values: Dict[str, Dict[int, float]] = field(default_factory=dict)
    observed_days: Tuple[int, ...] = ()
    baselines: Dict[str, float] = field(default_factory=dict)

    def previous_day(self, day: int) -> Optional[int]:
        """The last day this patient submitted anything before `day`."""
        earlier = [d for d in self.observed_days if d < day]
        return max(earlier) if earlier else None


@dataclass(frozen=True)
class RuleSet:
    bindings: Sequence[Binding]
    review_at: int
    critical_at: int
    max_points_per_parameter: int
    composite: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Signal:
    """
    One scored finding.

    `name` identifies the signal in the reasons a nurse reads and in the dedup
    key; `parameter` is the measure it read. They differ where one measure
    produces several signals — pain and pain_rising both read pain — which is why
    the per-parameter cap keys on `parameter` and the dedup key on `name`.
    """

    name: str
    parameter: str
    score: int
    weight: int
    detail: str
    is_trend: bool = False
    is_emergency: bool = False
    holds: bool = True
    points: int = 0

    def __post_init__(self) -> None:
        self.points = self.score * self.weight


@dataclass(frozen=True)
class Evaluation:
    tier: str
    total_score: int
    is_override: bool
    reasons: List[Dict[str, Any]]
    reason_key: str
    coverage: Optional[float] = None
    is_low_confidence: bool = False


# --------------------------------------------------------------- scoring one measure

def _unit(binding: Binding) -> str:
    return UNIT_SUFFIX.get(binding.unit or "", "")


def _numeric_score(binding: Binding, value: Any, day: int, baselines: Dict[str, float]) -> Optional[Tuple[int, str]]:
    config = binding.config
    bands = bands_for_day(config["bands_by_day"], day) if "bands_by_day" in config else config.get("bands")
    if not bands:
        return None  # A trend-only measure has no band to read today's value against.

    measured = float(value)
    detail = f"{binding.name} {measured:g}{_unit(binding)}"

    if config.get("relative_to_baseline"):
        baseline = baselines.get(binding.code)
        if baseline is None:
            return None  # No discharge reading, so the delta means nothing.
        detail += f", {measured - baseline:+g} from discharge"
        # Bands are written as distance in the worsening direction, so a rise and
        # a fall are read by the same band list.
        measured = worsening(binding.direction, measured, baseline)

    score = band_score(bands, measured)
    return None if score is None else (score, detail)


def _milestone_score(binding: Binding, code: Any, day: int) -> Optional[Tuple[int, str]]:
    """Behind the level expected by today? Falling short scores; reaching it says nothing."""
    milestone = binding.config.get("milestone") or {}
    due = [int(d) for d in milestone if int(d) <= day]
    if not due:
        return None
    by_day = max(due)
    expected_code = milestone[str(by_day)]
    expected, reached = binding.option_ranks.get(expected_code), binding.option_ranks.get(str(code))
    if expected is None or reached is None or reached >= expected:
        return None
    return int(binding.config.get("score", 0)), f"{binding.name}: {code}, {expected_code} expected by day {by_day}"


def _threshold_score(binding: Binding, value: Any, day: int, baselines: Dict[str, float]) -> Optional[Tuple[int, str]]:
    """Today's band score for one measure, with the wording a nurse reads."""
    if value is None:
        return None  # A skipped answer is unknown, not reassuring, and is never scored.
    if binding.type == "boolean":
        if value is not True:
            return None
        return int(binding.config.get("binary_score", 0)), f"{binding.name}: yes"
    if binding.type == "ordinal":
        return _milestone_score(binding, value, day)
    if binding.type == "numeric":
        return _numeric_score(binding, value, day, baselines)
    return None


# ------------------------------------------------------------------ the pipeline

def _series(binding: Binding, reading: Reading, window: Window) -> Series:
    """
    One measure's readings and band scores across the whole window.

    Scoring the history as well as today is what lets a detector ask whether this
    settled and came back, rather than only how bad it is now.
    """
    values = dict(window.values.get(binding.code, {}))
    answer = reading.answers.get(binding.code)
    if isinstance(answer, (int, float)) and not isinstance(answer, bool):
        values[reading.day] = float(answer)

    scores: Dict[int, int] = {}
    for day, value in values.items():
        scored = _threshold_score(binding, value, day, window.baselines)
        if scored is not None:
            scores[day] = scored[0]
    return Series(direction=binding.direction or "higher_is_worse", values=values, scores=scores)


def _threshold_signals(active: Sequence[Binding], reading: Reading, window: Window) -> List[Signal]:
    signals = []
    for binding in active:
        scored = _threshold_score(binding, reading.answers.get(binding.code), reading.day, window.baselines)
        if scored is None or scored[0] <= 0:
            continue
        score, detail = scored
        emergency = bool(binding.config.get("emergency"))
        signals.append(Signal(
            name=binding.code, parameter=binding.code, score=score, weight=binding.weight,
            detail=f"{detail} (emergency)" if emergency else detail, is_emergency=emergency,
        ))
    return signals


def _trend_signals(
    active: Sequence[Binding],
    ruleset: RuleSet,
    reading: Reading,
    window: Window,
    abnormal_by_day: Dict[int, bool],
) -> List[Signal]:
    """
    The derived signals. They flow through the same band-and-weight pipeline as
    everything else rather than being bolted on as a bonus, because a trend can
    override on its own and has to appear in the reasons the nurse reads.
    """
    previous = window.previous_day(reading.day)
    signals: List[Signal] = []

    for binding in active:
        series = _series(binding, reading, window)
        for config in binding.trends:
            score = detect(series, reading.day, config)
            if score is None or score <= 0:
                continue
            held = previous is not None and (detect(series, previous, config) or 0) > 0
            signals.append(Signal(
                name=config.get("name", binding.code), parameter=binding.code, score=score,
                weight=int(config.get("weight", binding.weight)),
                detail=_trend_detail(binding, config, series, reading.day),
                is_trend=True, holds=score >= OVERRIDE_SCORE or held,
            ))

    for config in ruleset.composite.get("trends") or []:
        detector = COMPOSITE_DETECTORS[config["detector"]]
        score = detector(abnormal_by_day, reading.day, config)
        if score is None or score <= 0:
            continue
        held = previous is not None and (detector(abnormal_by_day, previous, config) or 0) > 0
        signals.append(Signal(
            name=config["name"], parameter=config["name"], score=score,
            weight=int(config.get("weight", 1)), detail=_COMPOSITE_DETAIL[config["detector"]],
            is_trend=True, holds=score >= OVERRIDE_SCORE or held,
        ))

    return signals


_COMPOSITE_DETAIL = {"streak": "Something has been abnormal several days running"}


def _trend_detail(binding: Binding, config: Dict[str, Any], series: Series, day: int) -> str:
    """Plain wording for a derived signal. The direction decides which way round it reads."""
    rising = series.direction == "higher_is_worse"
    detector = config["detector"]
    if detector == "delta_vs_rolling_mean":
        span = int(config.get("window_days", 3))
        recent = [v for _, v in series.present(day - span, day - 1)]
        moved = series.worsening(series.values[day], sum(recent) / len(recent))
        return f"{binding.name} {'up' if rising else 'down'} {abs(moved):g}{_unit(binding)} on its own {span}-day average"
    if detector == "reemergence":
        return f"{binding.name} settled and has come back"
    if detector == "monotonic_rise":
        return f"{binding.name} {'climbing' if rising else 'falling'} steadily across the window"
    if detector == "drop_from_personal_best":
        pct = round(float(config.get("drop_fraction", 0.5)) * 100)
        return f"{binding.name} below {pct}% of this patient's best"
    return binding.name


def _cap_per_parameter(signals: List[Signal], cap: int) -> List[Signal]:
    """
    Clamp what any one measure contributes.

    A high and rising pain reading scores twice, once on its band and once on its
    trend. That is usually right but compounds fast, so each measure's points are
    capped: the highest-scoring signal keeps its points in full and the rest share
    what is left. Capping is about the composite total, never about suppressing a
    maximal signal, and sorting by score first is what guarantees a top-band
    signal always survives to be seen by the override check.
    """
    by_parameter: Dict[str, List[Signal]] = {}
    for signal in signals:
        by_parameter.setdefault(signal.parameter, []).append(signal)

    for group in by_parameter.values():
        remaining = cap
        for signal in sorted(group, key=lambda s: (s.score, s.weight), reverse=True):
            signal.points = min(signal.points, max(remaining, 0))
            remaining -= signal.points
    return signals


def _reasons(signals: Sequence[Signal]) -> List[Dict[str, Any]]:
    """What the nurse reads, worst first. The score is machinery; the wording is the point."""
    ranked = sorted(signals, key=lambda s: (s.points, s.score, s.name), reverse=True)
    return [{"name": s.name, "detail": s.detail, "score": s.score, "points": s.points} for s in ranked]


def _reason_key(signals: Sequence[Signal]) -> str:
    """A stable hash of the sorted signal names, so the same problem twice is one alert."""
    names = sorted({s.name for s in signals})
    return hashlib.sha1("|".join(names).encode()).hexdigest()[:16] if names else "none"


def _coverage(reading: Reading) -> Optional[float]:
    if not reading.asked:
        return None
    answered = sum(1 for code in reading.asked if reading.answers.get(code) is not None)
    return round(answered / len(reading.asked), 3)


def evaluate(reading: Reading, window: Window, ruleset: RuleSet) -> Evaluation:
    """Pure scoring: the same reading, window and ruleset always give the same tier and reasons."""
    # 1. Rule selection precedes scoring. A value collected on a day it is not
    #    scored is stored and ignored, and the engine enforces that itself rather
    #    than trusting the form: answers also arrive by phone, from an offline
    #    queue crossing a ruleset change, and through the API directly.
    active = [b for b in ruleset.bindings if b.score_from <= reading.day <= b.score_to]

    # 2. Threshold signals first, because the detectors need to know what is
    #    currently abnormal.
    threshold = _threshold_signals(active, reading, window)

    abnormal_by_day: Dict[int, bool] = {day: False for day in window.observed_days}
    abnormal_by_day[reading.day] = bool(threshold)
    for binding in active:
        for day, score in _series(binding, reading, window).scores.items():
            if score > 0:
                abnormal_by_day[day] = True

    # 3. Trend signals, over the same window.
    trend = _trend_signals(active, ruleset, reading, window, abnormal_by_day)

    # 4. The cap, before the overrides.
    signals = _cap_per_parameter(threshold + trend, ruleset.max_points_per_parameter)

    coverage = _coverage(reading)
    low_confidence = coverage is not None and coverage < LOW_CONFIDENCE_COVERAGE

    def result(tier: str, counted: Sequence[Signal], override: bool) -> Evaluation:
        return Evaluation(
            tier=tier,
            total_score=sum(s.points for s in counted if not s.is_emergency),
            is_override=override,
            reasons=_reasons(counted),
            reason_key=_reason_key(counted),
            coverage=coverage,
            is_low_confidence=low_confidence,
        )

    # 5. Emergency precedes the top band: both are overrides, but only an
    #    emergency shows guidance on the patient's own screen, so it is asked first.
    if any(s.is_emergency for s in signals):
        return result("emergency", signals, override=True)

    # 6. Any signal at the top band is sufficient alone. binary_score 3 and a
    #    trend scoring 3 are how a rule declares that, with no separate override
    #    list to fall out of step with the rules.
    if any(s.score >= OVERRIDE_SCORE for s in signals):
        return result("critical", signals, override=True)

    # 7. The weighted sum, over everything that is allowed to count. A trend must
    #    hold across two consecutive submissions before it can raise the tier:
    #    trend states persist for days and would otherwise flap across a band
    #    boundary. An override is never delayed this way.
    counted = [s for s in signals if s.holds]
    total = sum(s.points for s in counted)
    tier = "critical" if total >= ruleset.critical_at else "review" if total >= ruleset.review_at else "normal"
    return result(tier, counted, override=False)


# ------------------------------------------------------------------ database wrapper

RULESET_SQL = """
    SELECT review_at, critical_at, max_points_per_parameter, composite_config
    FROM meta.ruleset WHERE ruleset_id = :r
"""

BINDINGS_SQL = """
    SELECT p.parameter_id, p.parameter_code AS code, p.parameter_name AS name,
           p.parameter_type AS type, p.unit, pp.parameter_weight AS weight,
           pp.score_from_day AS score_from, pp.score_to_day AS score_to, pp.scoring_config AS config,
           coalesce((SELECT jsonb_object_agg(o.option_code, o.ordinal_rank)
                     FROM meta.parameter_option o WHERE o.parameter_id = p.parameter_id), '{}'::jsonb)
               AS option_ranks
    FROM meta.procedure_parameter pp
    JOIN meta.parameter p ON p.parameter_id = pp.parameter_id
    WHERE pp.ruleset_id = :r
    ORDER BY pp.display_order
"""

HISTORY_SQL = """
    SELECT c.day_after_discharge AS day, p.parameter_code AS code, v.value_num
    FROM txn.patient_check_in c
    JOIN txn.patient_check_in_value v ON v.check_in_id = c.check_in_id
    JOIN meta.parameter p ON p.parameter_id = v.parameter_id
    WHERE c.episode_id = :e AND NOT c.is_superseded
      AND c.day_after_discharge <= :day AND v.value_num IS NOT NULL
"""

OBSERVED_DAYS_SQL = """
    SELECT DISTINCT day_after_discharge FROM txn.patient_check_in
    WHERE episode_id = :e AND NOT is_superseded AND day_after_discharge <= :day
"""

ASKED_SQL = """
    SELECT p.parameter_code
    FROM meta.procedure_parameter pp
    JOIN meta.parameter p ON p.parameter_id = pp.parameter_id
    WHERE pp.ruleset_id = :r AND :day BETWEEN pp.collect_from_day AND pp.collect_to_day
"""


async def load_ruleset(db: AsyncSession, ruleset_id: int) -> RuleSet:
    row = (await db.execute(text(RULESET_SQL), {"r": ruleset_id})).mappings().one()
    bindings = [
        Binding(**{**b, "option_ranks": {k: int(v) for k, v in b["option_ranks"].items()}})
        for b in (await db.execute(text(BINDINGS_SQL), {"r": ruleset_id})).mappings().all()
    ]
    return RuleSet(
        bindings=bindings,
        review_at=row["review_at"],
        critical_at=row["critical_at"],
        max_points_per_parameter=row["max_points_per_parameter"],
        composite=row["composite_config"] or {},
    )


async def load_window(db: AsyncSession, episode_id: UUID, day: int) -> Window:
    values: Dict[str, Dict[int, float]] = {}
    for row in (await db.execute(text(HISTORY_SQL), {"e": episode_id, "day": day})).mappings().all():
        values.setdefault(row["code"], {})[row["day"]] = float(row["value_num"])

    observed = (await db.execute(text(OBSERVED_DAYS_SQL), {"e": episode_id, "day": day})).scalars().all()
    baselines = {r["parameter_code"]: float(r["value_num"]) for r in (await db.execute(text("""
        SELECT p.parameter_code, b.value_num
        FROM txn.episode_baseline b JOIN meta.parameter p ON p.parameter_id = b.parameter_id
        WHERE b.episode_id = :e AND b.value_num IS NOT NULL
    """), {"e": episode_id})).mappings().all()}

    return Window(values=values, observed_days=tuple(sorted(observed)), baselines=baselines)


async def _store(
    db: AsyncSession,
    *,
    episode_id: UUID,
    check_in_id: Optional[UUID],
    ruleset_id: int,
    day: int,
    result: Evaluation,
) -> Tuple[Evaluation, Optional[UUID]]:
    """Record the decision, then raise or escalate an alert if it warrants one."""
    evaluation_id = (await db.execute(text("""
        INSERT INTO txn.check_in_evaluation
            (check_in_id, episode_id, ruleset_id, day_after_discharge, tier, total_score,
             is_override, reasons, reason_key, coverage)
        VALUES (:c, :e, :r, :d, :tier, :total, :override, CAST(:reasons AS jsonb), :key, :coverage)
        RETURNING evaluation_id
    """), {
        "c": check_in_id, "e": episode_id, "r": ruleset_id, "d": day, "tier": result.tier,
        "total": result.total_score, "override": result.is_override,
        "reasons": json.dumps(result.reasons), "key": result.reason_key, "coverage": result.coverage,
    })).scalar_one()

    if result.tier == "normal":
        return result, None

    # One alert per problem per day: an identical reason set within 24 hours adds
    # nothing to the queue unless it has got worse, in which case the alert
    # already there is raised to the higher tier rather than joined by a second.
    recent = (await db.execute(text("""
        SELECT alert_id, tier, status FROM txn.alert
        WHERE episode_id = :e AND reason_key = :key AND raised_at > now() - interval '24 hours'
        ORDER BY raised_at DESC LIMIT 1
    """), {"e": episode_id, "key": result.reason_key})).mappings().first()

    if recent and TIER_RANK[result.tier] <= TIER_RANK[recent["tier"]]:
        return result, None

    if recent and recent["status"] in ("open", "acknowledged"):
        await db.execute(text("""
            UPDATE txn.alert
               SET tier = :tier, evaluation_id = :ev, notified_at = NULL, escalated_at = NULL
             WHERE alert_id = :a
        """), {"tier": result.tier, "ev": evaluation_id, "a": recent["alert_id"]})
        return result, recent["alert_id"]

    alert_id = (await db.execute(text("""
        INSERT INTO txn.alert (episode_id, evaluation_id, tier, reason_key)
        VALUES (:e, :ev, :tier, :key)
        ON CONFLICT (episode_id, reason_key) WHERE status IN ('open', 'acknowledged') DO NOTHING
        RETURNING alert_id
    """), {"e": episode_id, "ev": evaluation_id, "tier": result.tier, "key": result.reason_key})).scalar_one_or_none()
    return result, alert_id


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
    ruleset = await load_ruleset(db, ruleset_id)
    window = await load_window(db, episode_id, day)

    codes = {b.parameter_id: b.code for b in ruleset.bindings}
    asked = (await db.execute(text(ASKED_SQL), {"r": ruleset_id, "day": day})).scalars().all()
    reading = Reading(
        day=day,
        answers={codes[pid]: value for pid, value in answers_by_parameter.items() if pid in codes},
        asked=tuple(asked),
    )

    result = evaluate(reading, window, ruleset)
    return await _store(db, episode_id=episode_id, check_in_id=check_in_id,
                        ruleset_id=ruleset_id, day=day, result=result)


async def evaluate_missed_check_in(
    db: AsyncSession, *, episode_id: UUID, ruleset_id: int, day: int, ruleset: Optional[RuleSet] = None,
) -> Tuple[Evaluation, Optional[UUID]]:
    """
    The absence case, from the sweep rather than from ingest.

    The same evaluator runs against an all-unknown reading. A second
    implementation here would diverge from the real one at the first threshold
    change, so the sweep decides nothing itself. Today's detectors all need
    today's value and therefore stay silent, which is why a quiet result becomes
    `missed` rather than `normal`; the check below is what stops a detector that
    reads history alone from being thrown away if one is ever added.
    """
    # The sweep passes the ruleset in: every patient on a version shares one, and
    # reloading it per episode is two more round trips each across a whole ward.
    ruleset = ruleset or await load_ruleset(db, ruleset_id)
    window = await load_window(db, episode_id, day)
    asked = (await db.execute(text(ASKED_SQL), {"r": ruleset_id, "day": day})).scalars().all()

    result = evaluate(Reading(day=day, answers={}, asked=tuple(asked)), window, ruleset)
    if result.tier == "normal":
        missed = Signal(name="missed_check_in", parameter="missed_check_in", score=0, weight=0,
                        detail=f"No check-in received for day {day}")
        result = Evaluation(
            tier="missed", total_score=0, is_override=False,
            reasons=_reasons([missed]), reason_key=_reason_key([missed]),
            coverage=result.coverage, is_low_confidence=True,
        )

    return await _store(db, episode_id=episode_id, check_in_id=None,
                        ruleset_id=ruleset_id, day=day, result=result)
