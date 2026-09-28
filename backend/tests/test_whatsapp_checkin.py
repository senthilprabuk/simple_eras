"""
Check-ins made through the WhatsApp link. The link is bound to one episode and
one day, and only a check-in made through it messages the patient back.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.services.magic_token import generate_magic_token
from app.services.patient_messages import reply_type_for
from tests.support import create_hospital


@pytest.fixture(autouse=True)
def log_provider(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "log")


async def _linked_patient(db, code):
    """A patient on today's check-in, at a hospital with reply wording."""
    hospital = await create_hospital(db, code)
    day = (await db.execute(text("""
        SELECT ((now() AT TIME ZONE h.timezone)::date - e.discharge_date)::int
        FROM txn.patient_episode e JOIN meta.hospital h ON h.hospital_id = e.hospital_id
        WHERE e.episode_id = :e
    """), {"e": hospital.episode_id})).scalar_one()
    await db.execute(text("""
        INSERT INTO meta.message_template (hospital_id, template_key, language_code, body) VALUES
            (:h, 'checkin_confirmation', 'en', 'Thank you {patient_first_name}, day {post_op_day} reached {hospital_name}.'),
            (:h, 'urgent_guidance', 'en', '{patient_first_name}, please call {hospital_name} now.')
    """), {"h": hospital.hospital_id})
    await db.commit()
    return hospital, day


def _answers(form):
    answers = []
    for section in form["sections"]:
        for p in section["parameters"]:
            if p["type"] == "numeric":
                answers.append({"parameter_id": p["parameter_id"], "value_num": p["value_min"] or 0.0})
            elif p["type"] == "boolean":
                answers.append({"parameter_id": p["parameter_id"], "value_bool": False})
            elif p["type"] == "ordinal" and p["options"]:
                answers.append({"parameter_id": p["parameter_id"], "value_code": p["options"][0]["code"]})
    return answers


def _submission(episode_id, day, token, values, **changes):
    return {
        "episode_id": str(episode_id),
        "day_after_discharge": day,
        "idempotency_key": f"link-{uuid4().hex}",
        "simulated": False,
        "token": token,
        "values": values,
        **changes,
    }


async def _messages(db, episode_id):
    return (await db.execute(text("""
        SELECT message_type, status, body, attempts FROM txn.patient_message
        WHERE episode_id = :e ORDER BY created_at
    """), {"e": episode_id})).mappings().all()


async def test_the_link_opens_its_own_day_and_knows_when_it_is_done(client, db):
    hospital, day = await _linked_patient(db, "LINK-FORM")
    token = generate_magic_token(hospital.episode_id, day)

    form = (await client.get(f"/api/v1/checkin/form?token={token}")).json()
    assert form["episode"]["episode_id"] == str(hospital.episode_id)
    assert form["effective_day"] == day
    assert form["simulated"] is False
    assert form["already_submitted_today"] is False

    res = await client.post("/api/v1/checkin", json=_submission(hospital.episode_id, day, token, _answers(form)))
    assert res.status_code == 201, res.text

    again = (await client.get(f"/api/v1/checkin/form?token={token}")).json()
    assert again["already_submitted_today"] is True


async def test_a_check_in_through_the_link_is_answered_on_whatsapp(client, db):
    hospital, day = await _linked_patient(db, "LINK-REPLY")
    token = generate_magic_token(hospital.episode_id, day)
    form = (await client.get(f"/api/v1/checkin/form?token={token}")).json()

    res = await client.post("/api/v1/checkin", json=_submission(hospital.episode_id, day, token, _answers(form)))
    receipt = res.json()
    assert receipt["patient_message_status"] == "sent"

    [message] = await _messages(db, hospital.episode_id)
    assert message["message_type"] == reply_type_for(receipt["tier"])
    assert message["status"] == "sent"
    assert message["attempts"] == 1
    assert message["body"].startswith("Thank you Patient, day") or message["body"].startswith("Patient, please call")


async def test_a_simulator_check_in_never_messages_the_patient(client, db):
    hospital, day = await _linked_patient(db, "LINK-SIM")
    form = (await client.get(f"/api/v1/checkin/form?episode_id={hospital.episode_id}")).json()

    res = await client.post(
        "/api/v1/checkin", json=_submission(hospital.episode_id, day, None, _answers(form))
    )
    assert res.status_code == 201
    assert res.json()["patient_message_status"] is None
    assert await _messages(db, hospital.episode_id) == []


async def test_the_link_is_bound_to_its_episode_and_day(client, db):
    hospital, day = await _linked_patient(db, "LINK-BIND")
    token = generate_magic_token(hospital.episode_id, day)
    other, _ = await _linked_patient(db, "LINK-BIND-2")

    res = await client.post("/api/v1/checkin", json=_submission(other.episode_id, day, token, []))
    assert res.status_code == 403
    assert await _messages(db, other.episode_id) == []
    res = await client.post("/api/v1/checkin", json=_submission(hospital.episode_id, day - 1, token, []))
    assert res.status_code == 403
    res = await client.post("/api/v1/checkin", json=_submission(hospital.episode_id, day, token, [], simulated=True))
    assert res.status_code == 400
    res = await client.post("/api/v1/checkin", json=_submission(hospital.episode_id, day, token[:-4] + "xyz1", []))
    assert res.status_code == 401
    assert await _messages(db, hospital.episode_id) == []


async def test_a_link_from_an_earlier_day_is_refused(client, db):
    hospital, day = await _linked_patient(db, "LINK-STALE")
    yesterdays = generate_magic_token(hospital.episode_id, day - 1)

    assert (await client.get(f"/api/v1/checkin/form?token={yesterdays}")).status_code == 410
    res = await client.post("/api/v1/checkin", json=_submission(hospital.episode_id, day - 1, yesterdays, []))
    assert res.status_code == 410


async def test_with_sending_disabled_the_reply_waits_and_is_not_reported_sent(client, db, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "disabled")
    hospital, day = await _linked_patient(db, "LINK-OFF")
    token = generate_magic_token(hospital.episode_id, day)

    res = await client.post("/api/v1/checkin", json=_submission(hospital.episode_id, day, token, []))
    assert res.json()["patient_message_status"] == "queued"
    [message] = await _messages(db, hospital.episode_id)
    assert message["status"] == "queued"
    assert message["attempts"] == 0


async def test_without_reply_wording_nothing_is_sent_and_the_gap_is_logged(client, db):
    hospital = await create_hospital(db, "LINK-NOWORD")
    form = (await client.get(f"/api/v1/checkin/form?episode_id={hospital.episode_id}")).json()
    day = form["episode"]["actual_post_op_day"]
    token = generate_magic_token(hospital.episode_id, day)

    res = await client.post("/api/v1/checkin", json=_submission(hospital.episode_id, day, token, []))
    assert res.status_code == 201
    assert res.json()["patient_message_status"] is None
    [message] = await _messages(db, hospital.episode_id)
    assert message["status"] == "failed"


def test_only_a_critical_verdict_gets_urgent_guidance():
    assert reply_type_for("critical") == "urgent_guidance"
    assert reply_type_for("review") == "checkin_confirmation"
    assert reply_type_for("normal") == "checkin_confirmation"


async def test_with_the_simulator_off_only_the_patients_link_opens_a_check_in(client, db, monkeypatch):
    monkeypatch.setattr(settings, "CHECKIN_SIMULATOR_ENABLED", False)
    hospital, day = await _linked_patient(db, "LINK-SIM-OFF")

    assert (await client.get("/api/v1/checkin/episodes")).status_code == 404
    assert (await client.get(f"/api/v1/checkin/form?episode_id={hospital.episode_id}")).status_code == 404
    res = await client.post("/api/v1/checkin", json=_submission(hospital.episode_id, day, None, []))
    assert res.status_code == 401
    submitted = (await db.execute(
        text("SELECT count(*) FROM txn.patient_check_in WHERE episode_id = :e"), {"e": hospital.episode_id}
    )).scalar_one()
    assert submitted == 0

    token = generate_magic_token(hospital.episode_id, day)
    res = await client.get("/api/v1/checkin/form", headers={"X-Checkin-Token": token})
    assert res.status_code == 200
    res = await client.post("/api/v1/checkin", json=_submission(hospital.episode_id, day, token, []))
    assert res.status_code == 201


async def test_the_form_carries_the_hospitals_emergency_number(client, db):
    hospital, day = await _linked_patient(db, "LINK-SOS")
    headers = {"X-Checkin-Token": generate_magic_token(hospital.episode_id, day)}

    form = (await client.get("/api/v1/checkin/form", headers=headers)).json()
    assert form["episode"]["hospital_emergency_phone"] is None

    await db.execute(text("UPDATE meta.hospital SET emergency_phone_e164 = '+914225550100' WHERE hospital_id = :h"),
                     {"h": hospital.hospital_id})
    await db.commit()
    form = (await client.get("/api/v1/checkin/form", headers=headers)).json()
    assert form["episode"]["hospital_emergency_phone"] == "+914225550100"
