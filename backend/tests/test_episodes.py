from uuid import uuid4

from sqlalchemy import text

from tests.support import episode_for_mrn

DAY_ZERO_SQL = """
    SELECT v.value_num
    FROM txn.patient_check_in c
    JOIN txn.patient_check_in_value v ON v.check_in_id = c.check_in_id
    JOIN meta.parameter p ON p.parameter_id = v.parameter_id
    WHERE c.episode_id = :e AND c.day_after_discharge = 0 AND p.parameter_code = :code
"""


async def test_summary_pairs_discharge_baseline_with_latest_check_in(client, db, nurse_headers):
    episode_id = await episode_for_mrn(db, "FX-01")
    res = await client.get(f"/api/v1/episodes/{episode_id}/summary", headers=nurse_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["patient_name"] == "Lakshmi Narayanan [Smooth Recovery]"
    assert data["mrn"] == "FX-01"
    assert data["phone_e164"].startswith("+")
    assert data["hospital_name"] == "St. Mary's Orthopedic Center"
    assert data["ruleset_version"] == "1.0.0"
    assert data["post_op_day"] == 21
    assert data["latest_check_in"]["day_after_discharge"] == 21
    assert data["latest_check_in"]["source"] == "patient"

    readings = {r["code"]: r for r in data["readings"]}
    assert "redness" not in readings
    assert readings["temp_c"]["baseline"] == 36.8
    assert isinstance(readings["temp_c"]["current"], float)
    # The discharge baseline is the reading taken on the day of discharge. Pulse is
    # scored as a distance from it, so the two have to be the same observation.
    day_zero_hr = (await db.execute(text(DAY_ZERO_SQL), {"e": episode_id, "code": "hr"})).scalar_one()
    assert readings["hr"]["baseline"] == float(day_zero_hr)
    assert readings["knee_bend"]["baseline"] == "Sit in a dining chair"
    assert readings["knee_bend"]["current"] == "Get into a car"
    assert readings["walk_aid"]["current"] == "Walking stick"
    assert readings["calf_pain"]["current"] is False
    assert readings["calf_pain"]["concerning_when_true"] is True


async def test_summary_carries_who_to_call_and_where_the_patient_lives(client, db, nurse_headers):
    episode_id = await episode_for_mrn(db, "FX-01")
    data = (await client.get(f"/api/v1/episodes/{episode_id}/summary", headers=nurse_headers)).json()

    assert data["gender"] == "female"
    assert [(c["name"], c["relationship"]) for c in data["emergency_contacts"]] == [("Arun Narayanan", "son")]
    assert data["emergency_contacts"][0]["phone_e164"] != data["phone_e164"]
    assert (data["address"]["line"], data["address"]["postal_code"]) == ("12 Race Course Road", "641018")
    assert (data["checkin_window_start"], data["checkin_window_end"]) == ("08:00:00", "10:00:00")

    body = data["body"]
    assert body["bmi"] == round(body["weight_kg"] / (body["height_cm"] / 100) ** 2, 1)
    assert body["bp_systolic"] > body["bp_diastolic"]
    # Fixtures are loaded by script, not enrolled, so no consent decisions were recorded.
    assert data["consents"] == []


async def test_summary_of_another_hospitals_patient_is_not_found(client, db, h2_headers):
    episode_id = await episode_for_mrn(db, "FX-01")
    res = await client.get(f"/api/v1/episodes/{episode_id}/summary", headers=h2_headers)
    assert res.status_code == 404


async def test_summary_of_unknown_episode_is_not_found(client, nurse_headers):
    res = await client.get(f"/api/v1/episodes/{uuid4()}/summary", headers=nurse_headers)
    assert res.status_code == 404


async def test_summary_requires_authentication(client, db):
    episode_id = await episode_for_mrn(db, "FX-01")
    assert (await client.get(f"/api/v1/episodes/{episode_id}/summary")).status_code == 401
