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
