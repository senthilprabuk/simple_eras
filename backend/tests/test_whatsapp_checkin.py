from uuid import uuid4
import pytest
from sqlalchemy import text

from app.services.magic_token import generate_magic_token


@pytest.mark.asyncio
async def test_checkin_form_with_magic_token(client, db):
    # Find an active episode
    row = (await db.execute(text("""
        SELECT e.episode_id, e.hospital_id, p.patient_name,
               ((now() AT TIME ZONE h.timezone)::date - e.discharge_date)::int AS post_op_day
        FROM txn.patient_episode e
        JOIN meta.hospital h ON h.hospital_id = e.hospital_id
        JOIN txn.patient p   ON p.patient_id = e.patient_id
        WHERE e.status = 'active'
        LIMIT 1
    """))).mappings().first()
    assert row is not None

    episode_id = row["episode_id"]
    day = row["post_op_day"]

    # Generate token
    token = generate_magic_token(episode_id, day)

    # Fetch form using token
    res = await client.get(f"/api/v1/checkin/form?token={token}")
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["episode"]["episode_id"] == str(episode_id)
    assert data["episode"]["patient_name"] == row["patient_name"]
    assert data["effective_day"] == day
    assert data["simulated"] is False
    assert len(data["sections"]) > 0


@pytest.mark.asyncio
async def test_checkin_submission_triggers_whatsapp_confirmation(client, db):
    # Find an active episode with parameters
    row = (await db.execute(text("""
        SELECT e.episode_id, p.phone_e164,
               ((now() AT TIME ZONE h.timezone)::date - e.discharge_date)::int AS post_op_day
        FROM txn.patient_episode e
        JOIN meta.hospital h ON h.hospital_id = e.hospital_id
        JOIN txn.patient p   ON p.patient_id = e.patient_id
        WHERE e.status = 'active'
        LIMIT 1
    """))).mappings().first()
    assert row is not None

    episode_id = row["episode_id"]
    day = row["post_op_day"]

    # Clear prior messages
    await db.execute(text("DELETE FROM txn.patient_message WHERE episode_id = :e"), {"e": episode_id})
    await db.commit()

    token = generate_magic_token(episode_id, day)

    # Get the form to pick valid parameters
    form_res = await client.get(f"/api/v1/checkin/form?token={token}")
    assert form_res.status_code == 200
    form = form_res.json()

    # Collect answers for first section
    answers = []
    for s in form["sections"]:
        for p in s["parameters"]:
            if p["type"] == "numeric":
                answers.append({"parameter_id": p["parameter_id"], "value_num": 0.0})
            elif p["type"] == "boolean":
                answers.append({"parameter_id": p["parameter_id"], "value_bool": False})
            elif p["type"] == "ordinal" and p["options"]:
                answers.append({"parameter_id": p["parameter_id"], "value_code": p["options"][0]["code"]})

    # Submit check-in
    key = f"test-checkin-{uuid4().hex}"
    submit_payload = {
        "episode_id": str(episode_id),
        "day_after_discharge": day,
        "idempotency_key": key,
        "simulated": False,
        "token": token,
        "values": answers,
    }

    sub_res = await client.post("/api/v1/checkin", json=submit_payload)
    assert sub_res.status_code == 201, sub_res.text
    receipt = sub_res.json()
    assert receipt["values_recorded"] == len(answers)

    # Verify a WhatsApp message was logged in txn.patient_message
    msg = (await db.execute(
        text("""
            SELECT message_type, status, direction, channel, body
            FROM txn.patient_message
            WHERE episode_id = :e AND message_type IN ('checkin_confirmation', 'urgent_guidance')
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"e": episode_id},
    )).mappings().first()

    assert msg is not None
    assert msg["status"] == "sent"
    assert msg["direction"] == "outbound"
    assert msg["channel"] == "whatsapp"
