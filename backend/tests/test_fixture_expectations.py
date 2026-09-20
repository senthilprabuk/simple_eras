"""
The clinical governance gate.

Every fixture patient in db/seed/02_fixtures.sql carries the day their recovery
should first be escalated and how far it should go. Replaying all of them through
the evaluator on every change is what stops a threshold edit quietly moving the
day a real patient would have been caught. A failure here is not a bug report: it
says the change is a clinical change, and needs a new ruleset version and a
clinician's signature rather than a green build.

Absence and deterioration are judged on separate axes. A fixture with deliberate
gaps is testing that the gaps are not read as deterioration, so its missed days
are not escalations; the drop-out fixture is testing the opposite.

Confidence is a third axis, and independent of both. A patient who submits every
day but answers two questions has no gaps and no deterioration, and the tier is
honest at normal — what the fixture asserts is that the engine says out loud how
little it was given to reach that answer.
"""

from typing import Dict, Optional, Tuple

from sqlalchemy import text

from app.services.rules_engine import (
    ASKED_SQL,
    Reading,
    Window,
    evaluate,
    load_ruleset,
    load_window,
)

CLINICAL_RANK = {"normal": 0, "review": 2, "critical": 3, "emergency": 4}

EXPECTATIONS_SQL = """
    SELECT x.fixture, x.episode_id, x.escalate_from, x.escalate_to, x.expect_tier,
           x.must_not_escalate, x.expect_reasons, x.expect_low_confidence, x.note,
           e.ruleset_id,
           (SELECT max(day_after_discharge) FROM txn.patient_check_in c
            WHERE c.episode_id = x.episode_id AND NOT c.is_superseded) AS last_submitted
    FROM txn.fixture_expectation x
    JOIN txn.patient_episode e ON e.episode_id = x.episode_id
    ORDER BY x.fixture
"""

ANSWERS_SQL = """
    SELECT c.day_after_discharge AS day, p.parameter_code AS code,
           v.value_num, v.value_bool, v.value_code
    FROM txn.patient_check_in c
    JOIN txn.patient_check_in_value v ON v.check_in_id = c.check_in_id
    JOIN meta.parameter p ON p.parameter_id = v.parameter_id
    WHERE c.episode_id = :e AND NOT c.is_superseded
"""

# The last day of monitoring these fixtures are generated across.
LAST_DAY = 21


async def _answers_by_day(db, episode_id) -> Dict[int, Dict[str, object]]:
    answers: Dict[int, Dict[str, object]] = {}
    for row in (await db.execute(text(ANSWERS_SQL), {"e": episode_id})).mappings().all():
        value = row["value_num"] if row["value_num"] is not None else (
            row["value_bool"] if row["value_bool"] is not None else row["value_code"]
        )
        answers.setdefault(row["day"], {})[row["code"]] = float(value) if row["value_num"] is not None else value
    return answers


async def _asked_by_day(db, ruleset_id) -> Dict[int, Tuple[str, ...]]:
    """
    What the form would have put in front of the patient on each day.

    Coverage is answered-over-asked, so without this the denominator is empty and
    the engine reports no coverage at all — which is how the suite managed to
    replay twelve patients without ever exercising the low-confidence flag.
    """
    return {
        day: tuple((await db.execute(text(ASKED_SQL), {"r": ruleset_id, "day": day})).scalars().all())
        for day in range(LAST_DAY + 1)
    }


async def _replay(db, episode_id, ruleset_id, ruleset=None, asked_by_day=None):
    """
    Every day of this patient's recovery, scored the way the check-in endpoint would.

    The whole history is read once and sliced per day in memory. Reloading it for
    each of twenty-two days across fourteen patients is several hundred round trips
    to the database, which is slow enough to time out against a hosted one.
    """
    ruleset = ruleset or await load_ruleset(db, ruleset_id)
    asked_by_day = asked_by_day if asked_by_day is not None else await _asked_by_day(db, ruleset_id)
    answers = await _answers_by_day(db, episode_id)
    whole = await load_window(db, episode_id, LAST_DAY)

    def window_on(day):
        return Window(
            values={code: {d: v for d, v in readings.items() if d <= day} for code, readings in whole.values.items()},
            observed_days=tuple(d for d in whole.observed_days if d <= day),
            baselines=whole.baselines,
        )

    tiers, reasons, low_confidence = {}, {}, {}
    for day in range(LAST_DAY + 1):
        if day not in answers:
            tiers[day] = "missed"
            continue
        reading = Reading(day=day, answers=answers[day], asked=asked_by_day.get(day, ()))
        result = evaluate(reading, window_on(day), ruleset)
        tiers[day] = result.tier
        reasons[day] = {r["name"] for r in result.reasons}
        low_confidence[day] = result.is_low_confidence
    return tiers, reasons, low_confidence


def _first_day_at(tiers: Dict[int, str], tier: str) -> Optional[int]:
    """The day this patient first reached that tier, or anything more serious."""
    wanted = CLINICAL_RANK[tier]
    return next((day for day in sorted(tiers) if CLINICAL_RANK.get(tiers[day], -1) >= wanted), None)


def _verdict(row, tiers) -> str:
    """What this replay actually did, in the words the fixture states its expectation in."""
    if row["expect_tier"] == "missed":
        first = next((d for d, tier in sorted(tiers.items()) if tier == "missed"), None)
        return "never went quiet" if first is None else f"missed from day {first}"

    # Absence is a separate axis: a fixture with deliberate gaps is testing that
    # the gaps are not read as deterioration.
    clinical = {day: tier for day, tier in tiers.items() if tier != "missed"}
    if row["must_not_escalate"]:
        ceiling = CLINICAL_RANK[row["expect_tier"]]
        above = sorted(day for day, tier in clinical.items() if CLINICAL_RANK[tier] > ceiling)
        return f"stayed at or below {row['expect_tier']}" if not above else (
            f"reached {clinical[above[0]]} on day {above[0]}"
        )

    first = _first_day_at(clinical, row["expect_tier"])
    return f"never reached {row['expect_tier']}" if first is None else f"{row['expect_tier']} from day {first}"


def _expected(row) -> str:
    if row["must_not_escalate"]:
        return f"stayed at or below {row['expect_tier']}"
    return f"{row['expect_tier']} from day {row['escalate_from']}-{row['escalate_to']}"


def _matches(row, verdict: str) -> bool:
    """Any day inside the fixture's window counts, so ordinary noise cannot move the build."""
    if row["must_not_escalate"]:
        return verdict.startswith("stayed at or below")
    tier, _, day = verdict.partition(" from day ")
    return tier in ("missed", row["expect_tier"]) and row["escalate_from"] <= int(day) <= row["escalate_to"]


def _confidence_verdict(low_confidence: Dict[int, bool]) -> str:
    """Whether the engine trusted this patient's answers, in the words the fixture uses."""
    if not low_confidence:
        return "no day was evaluated"
    if all(low_confidence.values()):
        return "low confidence on every day"
    if any(low_confidence.values()):
        days = sorted(day for day, low in low_confidence.items() if low)
        return f"low confidence on days {days}"
    return "confident on every day"


async def test_every_fixture_patient_escalates_when_the_ruleset_says_they_should(db):
    rows = (await db.execute(text(EXPECTATIONS_SQL))).mappings().all()
    assert len(rows) == 14

    actual, expected = {}, {}
    ruleset = await load_ruleset(db, rows[0]["ruleset_id"])  # every fixture is on the same approved version
    asked = await _asked_by_day(db, rows[0]["ruleset_id"])
    for row in rows:
        tiers, _, _ = await _replay(db, row["episode_id"], row["ruleset_id"], ruleset, asked)
        verdict = _verdict(row, tiers)
        actual[row["fixture"]] = verdict
        expected[row["fixture"]] = verdict if _matches(row, verdict) else f"{_expected(row)}  ({row['note']})"

    assert actual == expected


async def test_a_patient_who_leaves_most_questions_blank_is_flagged_low_confidence(db):
    """
    Coverage is the engine's own statement about how much it was given to work
    with. A patient who answers two of twelve questions can still score normal,
    and the flag is what stops that normal being read as a clean bill of health.
    """
    rows = (await db.execute(text(EXPECTATIONS_SQL))).mappings().all()
    ruleset = await load_ruleset(db, rows[0]["ruleset_id"])
    asked = await _asked_by_day(db, rows[0]["ruleset_id"])

    actual, expected = {}, {}
    for row in rows:
        _, _, low_confidence = await _replay(db, row["episode_id"], row["ruleset_id"], ruleset, asked)
        actual[row["fixture"]] = _confidence_verdict(low_confidence)
        expected[row["fixture"]] = (
            "low confidence on every day" if row["expect_low_confidence"] else "confident on every day"
        )

    assert actual == expected
