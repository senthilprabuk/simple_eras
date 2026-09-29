from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

from tests.support import episode_for_mrn


def _codes(form):
    return [p["code"] for s in form["sections"] for p in s["parameters"]]


def _param(form, code):
    return next(p for s in form["sections"] for p in s["parameters"] if p["code"] == code)


async def _form(client, episode_id, day=None):
    query = f"?episode_id={episode_id}" + (f"&day={day}" if day is not None else "")
    res = await client.get(f"/api/v1/checkin/form{query}")
    assert res.status_code == 200, res.text
    return res.json()


async def test_form_follows_the_rulesets_collection_windows(client, db):
    episode_id = await episode_for_mrn(db, "FX-01")

    early = await _form(client, episode_id, day=1)
    assert [s["key"] for s in early["sections"]] == ["readings", "checks"]
    assert _param(early, "drainage")["is_scored_today"] is False  # collected from 0, scored from 5
    assert _param(early, "breathless")["is_emergency"] is True

    mid = await _form(client, episode_id, day=25)
    assert [s["key"] for s in mid["sections"]] == ["readings", "checks", "progress"]

    late = await _form(client, episode_id, day=50)
    assert set(_codes(late)) == {"pain", "steps", "knee_bend", "walk_aid"}

    for form in (early, mid, late):
        assert "redness" not in _codes(form)


async def test_live_form_uses_the_patients_actual_post_op_day(client, db):
    form = await _form(client, await episode_for_mrn(db, "FX-01"))
    assert form["simulated"] is False
    assert form["effective_day"] == form["episode"]["actual_post_op_day"] == 21


async def test_same_day_resubmission_supersedes_and_replay_is_idempotent(client, db):
    episode_id = await episode_for_mrn(db, "FX-04")
    pain = _param(await _form(client, episode_id, day=30), "pain")["parameter_id"]

    def submit(key, score):
        return client.post("/api/v1/checkin", json={
            "episode_id": str(episode_id), "day_after_discharge": 30, "simulated": True,
            "idempotency_key": key, "values": [{"parameter_id": pain, "value_num": score}],
        })

    first = await submit("resubmit-probe-first", 3)
    assert first.status_code == 201
    assert first.json()["source"] == "synthetic"
    assert first.json()["superseded_count"] == 0

    correction = await submit("resubmit-probe-second", 8)
    assert correction.json()["superseded_count"] == 1

    replay = await submit("resubmit-probe-second", 8)
    assert replay.json()["duplicate"] is True
    assert replay.json()["check_in_id"] == correction.json()["check_in_id"]
    assert replay.json()["superseded_count"] == 0

    live = (await db.execute(text("""
        SELECT count(*) FROM txn.patient_check_in
        WHERE episode_id = :e AND day_after_discharge = 30 AND NOT is_superseded
    """), {"e": episode_id})).scalar_one()
    assert live == 1


async def test_answer_outside_its_collection_window_is_rejected(client, db):
    episode_id = await episode_for_mrn(db, "FX-04")
    knee_bend = _param(await _form(client, episode_id, day=25), "knee_bend")["parameter_id"]
    res = await client.post("/api/v1/checkin", json={
        "episode_id": str(episode_id), "day_after_discharge": 4, "simulated": True,
        "idempotency_key": f"window-probe-{uuid4()}", "values": [{"parameter_id": knee_bend, "value_code": "chair"}],
    })
    assert res.status_code == 400
    assert "outside the collection window" in res.json()["detail"]


async def test_each_answer_carries_exactly_one_value(client, db):
    episode_id = await episode_for_mrn(db, "FX-04")
    res = await client.post("/api/v1/checkin", json={
        "episode_id": str(episode_id), "day_after_discharge": 4, "simulated": True,
        "idempotency_key": f"shape-probe-{uuid4()}",
        "values": [{"parameter_id": 1, "value_num": 37.0, "value_bool": True}],
    })
    assert res.status_code == 422


async def test_unknown_episode_is_not_found(client):
    assert (await client.get(f"/api/v1/checkin/form?episode_id={uuid4()}")).status_code == 404


async def test_the_form_speaks_the_patients_language(client, db):
    lakshmi = await episode_for_mrn(db, "FX-01")  # enrolled in Tamil

    form = (await client.get(f"/api/v1/checkin/form?episode_id={lakshmi}")).json()
    assert (form["language"], form["patient_language"]) == ("ta", "ta")
    questions = {p["code"]: p for s in form["sections"] for p in s["parameters"]}
    assert questions["breathless"]["question_text"].startswith("உங்களுக்குப்")
    assert questions["breathless"]["name"] == "மூச்சுத் திணறல் அல்லது நெஞ்சு வலி"

    english = (await client.get(f"/api/v1/checkin/form?episode_id={lakshmi}&lang=en")).json()
    assert english["language"] == "en"
    assert {p["code"]: p for s in english["sections"] for p in s["parameters"]}["breathless"]["question_text"] == (
        "Are you newly short of breath, or having new chest pain?"
    )

    hindi = (await client.get(f"/api/v1/checkin/form?episode_id={lakshmi}&lang=hi&day=20")).json()
    options = {p["code"]: p for s in hindi["sections"] for p in s["parameters"]}["walk_aid"]["options"]
    assert [o["label"] for o in options][-1] == "कोई सहारा नहीं"


async def test_a_question_reworded_in_a_new_ruleset_falls_back_to_english(client, db):
    lakshmi = await episode_for_mrn(db, "FX-01")
    await db.execute(text("""
        UPDATE meta.procedure_parameter pp SET question_text_i18n = '{}'::jsonb
        FROM meta.parameter p
        WHERE p.parameter_id = pp.parameter_id AND p.parameter_code = 'steps'
    """))
    await db.commit()
    try:
        form = (await client.get(f"/api/v1/checkin/form?episode_id={lakshmi}")).json()
        steps = {p["code"]: p for s in form["sections"] for p in s["parameters"]}["steps"]
        assert steps["question_text"] == "How many steps today?"
    finally:
        await db.execute(text("""
            UPDATE meta.procedure_parameter pp
            SET question_text_i18n = '{"ta": "இன்று எத்தனை அடிகள் நடந்தீர்கள்?", "hi": "आज आप कितने कदम चले?"}'::jsonb
            FROM meta.parameter p
            WHERE p.parameter_id = pp.parameter_id AND p.parameter_code = 'steps'
        """))
        await db.commit()


async def _alert_states(db, episode_id):
    return {r["tier"]: r for r in (await db.execute(text("""
        SELECT tier, status, resolved_at, outcome, outcome_note FROM txn.alert WHERE episode_id = :e
    """), {"e": episode_id})).mappings().all()}


async def test_checking_in_closes_the_missed_alert_and_nothing_else(client, db):
    from tests.support import create_alert, create_hospital

    h = await create_hospital(db, "BACK-AGAIN")
    await create_alert(db, h.episode_id, tier="missed", raised_ago=timedelta(hours=20))
    await create_alert(db, h.episode_id, tier="critical")

    res = await client.post("/api/v1/checkin", json={
        "episode_id": str(h.episode_id), "day_after_discharge": 10,
        "idempotency_key": f"back-{uuid4().hex}", "values": [],
    })
    assert res.status_code == 201

    alerts = await _alert_states(db, h.episode_id)
    assert alerts["missed"]["status"] == "expired"
    assert alerts["missed"]["resolved_at"] is not None
    assert alerts["missed"]["outcome"] is None
    assert alerts["missed"]["outcome_note"] == "Closed automatically: the patient checked in on day 10."
    # A clinical finding still needs a nurse to record an outcome.
    assert alerts["critical"]["status"] == "open"


async def test_a_simulated_day_leaves_a_real_missed_alert_open(client, db):
    from tests.support import create_alert, create_hospital

    h = await create_hospital(db, "SIM-DAY")
    await create_alert(db, h.episode_id, tier="missed")

    res = await client.post("/api/v1/checkin", json={
        "episode_id": str(h.episode_id), "day_after_discharge": 3, "simulated": True,
        "idempotency_key": f"sim-{uuid4().hex}", "values": [],
    })
    assert res.status_code == 201
    assert (await _alert_states(db, h.episode_id))["missed"]["status"] == "open"
