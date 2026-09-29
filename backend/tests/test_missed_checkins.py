"""
The absence sweep. A patient who stops answering is the one the dashboard most
needs to show, and silence produces no submission to score.
"""

import uuid

from sqlalchemy import text

from app.services.missed_checkins import OWED_YESTERDAY, run_missed_checkin_sweep
from app.services.rules_engine import evaluate_missed_check_in
from tests.conftest import isolated_session_factory
from tests.support import add_check_in, create_hospital


async def _episode(db):
    """A hospital whose patient was discharged ten days ago, so yesterday was day 9."""
    return await create_hospital(db, f"MISS-{uuid.uuid4().hex[:6]}")


async def _ruleset_id(db, episode_id):
    return (await db.execute(
        text("SELECT ruleset_id FROM txn.patient_episode WHERE episode_id = :e"), {"e": episode_id},
    )).scalar_one()


async def _evaluations(db, episode_id):
    return (await db.execute(text("""
        SELECT day_after_discharge, tier, check_in_id, coverage FROM txn.check_in_evaluation
        WHERE episode_id = :e ORDER BY day_after_discharge
    """), {"e": episode_id})).mappings().all()


async def _owed(db):
    return {row["episode_id"]: row["day"] for row in (await db.execute(OWED_YESTERDAY)).mappings().all()}


async def test_a_missed_day_is_judged_and_queued_without_a_check_in_to_hang_it_on(db):
    hospital = await _episode(db)
    result, alert_id = await evaluate_missed_check_in(
        db, episode_id=hospital.episode_id, ruleset_id=await _ruleset_id(db, hospital.episode_id), day=9,
    )
    await db.commit()

    assert (result.tier, result.is_low_confidence) == ("missed", True)
    assert result.reasons[0]["detail"] == "No check-in received for day 9"
    assert alert_id is not None

    stored = await _evaluations(db, hospital.episode_id)
    assert [(e["day_after_discharge"], e["tier"], e["check_in_id"]) for e in stored] == [(9, "missed", None)]
    assert stored[0]["coverage"] == 0  # nothing at all was answered

    tier = (await db.execute(text("SELECT tier FROM txn.alert WHERE alert_id = :a"), {"a": alert_id})).scalar_one()
    assert tier == "missed"


async def test_a_history_of_fevers_does_not_get_scored_against_a_day_with_no_answers(db):
    """
    The sweep runs the real evaluator rather than a second copy of the rules, and
    the evaluator will not invent a reading. Four abnormal days followed by
    silence is still only silence: every detector needs today's value, and the
    streak was already reported on the last day the patient actually answered.
    """
    hospital = await _episode(db)
    for day in (5, 6, 7, 8):
        await add_check_in(db, hospital.episode_id, day, {"temp_c": 37.6})

    result, _ = await evaluate_missed_check_in(
        db, episode_id=hospital.episode_id, ruleset_id=await _ruleset_id(db, hospital.episode_id), day=9,
    )
    await db.commit()
    assert (result.tier, {r["name"] for r in result.reasons}) == ("missed", {"missed_check_in"})


async def test_who_owes_yesterday(db):
    quiet = await _episode(db)
    answered = await _episode(db)
    await add_check_in(db, answered.episode_id, 9, {"temp_c": 36.8})

    owed = await _owed(db)
    assert owed.get(quiet.episode_id) == 9
    assert answered.episode_id not in owed


async def test_a_day_already_judged_is_left_alone(db):
    hospital = await _episode(db)
    assert (await _owed(db)).get(hospital.episode_id) == 9

    await evaluate_missed_check_in(
        db, episode_id=hospital.episode_id, ruleset_id=await _ruleset_id(db, hospital.episode_id), day=9,
    )
    await db.commit()
    assert hospital.episode_id not in await _owed(db)


async def test_the_sweep_judges_every_owed_day_once(db):
    hospital = await _episode(db)

    first = await run_missed_checkin_sweep(isolated_session_factory)
    assert first["evaluated"] >= 1
    assert [(e["day_after_discharge"], e["tier"]) for e in await _evaluations(db, hospital.episode_id)] == [(9, "missed")]

    # Idempotent: a second pass finds the day already judged and does nothing.
    again = await run_missed_checkin_sweep(isolated_session_factory)
    assert again["evaluated"] == 0
    assert len(await _evaluations(db, hospital.episode_id)) == 1


async def test_a_patient_who_keeps_missing_has_one_missed_alert(db):
    """The demo seed's missed alert and the sweep's share a reason key, so they are one alert."""
    from app.services.rules_engine import evaluate_missed_check_in
    from tests.support import episode_for_mrn

    suresh = await episode_for_mrn(db, "FX-06")
    ruleset_id = (await db.execute(
        text("SELECT ruleset_id FROM txn.patient_episode WHERE episode_id = :e"), {"e": suresh}
    )).scalar_one()

    # What the sweep does for Suresh alone, so other hospitals' queues are untouched.
    _, raised = await evaluate_missed_check_in(db, episode_id=suresh, ruleset_id=ruleset_id, day=20)
    await db.commit()

    assert raised is None
    open_missed = (await db.execute(text("""
        SELECT count(*) FROM txn.alert
        WHERE episode_id = :e AND tier = 'missed' AND status IN ('open', 'acknowledged')
    """), {"e": suresh})).scalar_one()
    assert open_missed == 1


async def test_a_patient_back_before_the_sweep_gets_no_open_missed_alert(db):
    """Missed yesterday, checked in this morning, swept at ten: the day is recorded, the alert closed."""
    hospital = await _episode(db)
    await add_check_in(db, hospital.episode_id, 10, {"temp_c": 36.8})

    await run_missed_checkin_sweep(isolated_session_factory)

    # add_check_in stores day 10 without scoring it, so the only evaluation is the missed day.
    assert [(e["day_after_discharge"], e["tier"]) for e in await _evaluations(db, hospital.episode_id)] == [
        (9, "missed"),
    ]
    alerts = (await db.execute(text("""
        SELECT status, outcome_note FROM txn.alert WHERE episode_id = :e AND tier = 'missed'
    """), {"e": hospital.episode_id})).mappings().all()
    assert [(a["status"], a["outcome_note"]) for a in alerts] == [
        ("expired", "Closed automatically: the patient checked in on day 10."),
    ]
