"""
The Meta webhook: a handshake only with a verify token we issued, and delivery
receipts only when Meta's signature checks out.
"""

import hashlib
import hmac
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.config import settings

APP_SECRET = "test-app-secret"


@pytest.fixture
def app_secret(monkeypatch):
    monkeypatch.setattr(settings, "META_APP_SECRET", APP_SECRET)


def _signed(payload, secret=APP_SECRET):
    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, {"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={signature}"}


def _receipt(wamid, status):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "12345", "phone_number_id": "67890"},
                    "statuses": [{"id": wamid, "status": status, "timestamp": "1726830000",
                                  "recipient_id": "919876543210"}],
                },
            }],
        }],
    }


async def _handshake(client, token):
    return await client.get("/api/v1/whatsapp/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "1158201244",
    })


async def test_handshake_accepts_a_connected_hospitals_verify_token(client):
    res = await _handshake(client, "eras_noyyal_verify_2026")
    assert res.status_code == 200
    assert res.text == "1158201244"

    assert (await _handshake(client, "wrong_token")).status_code == 403
    assert (await client.get("/api/v1/whatsapp/webhook", params={"hub.mode": "subscribe"})).status_code == 403


async def test_handshake_accepts_the_platform_token_only_when_one_is_set(client, monkeypatch):
    assert (await _handshake(client, "platform-verify")).status_code == 403
    monkeypatch.setattr(settings, "META_WEBHOOK_VERIFY_TOKEN", "platform-verify")
    assert (await _handshake(client, "platform-verify")).status_code == 200


async def test_receipts_are_refused_without_a_signing_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "META_APP_SECRET", None)
    res = await client.post("/api/v1/whatsapp/webhook", json=_receipt("wamid.any", "delivered"))
    assert res.status_code == 503


async def test_unsigned_or_forged_receipts_are_refused(client, app_secret):
    res = await client.post("/api/v1/whatsapp/webhook", json=_receipt("wamid.any", "read"))
    assert res.status_code == 403

    body, headers = _signed(_receipt("wamid.any", "read"), secret="not-the-secret")
    res = await client.post("/api/v1/whatsapp/webhook", content=body, headers=headers)
    assert res.status_code == 403


async def test_signed_receipts_advance_the_message(client, db, app_secret):
    row = (await db.execute(text("""
        SELECT e.episode_id, e.patient_id, e.hospital_id
        FROM txn.patient_episode e
        WHERE e.status = 'active'
        LIMIT 1
    """))).mappings().first()

    wamid = f"wamid.test_{uuid4().hex}"
    await db.execute(text("""
        INSERT INTO txn.patient_message (
            episode_id, patient_id, hospital_id, message_type,
            day_after_discharge, phone_e164, channel, direction,
            body, meta_message_id, status, sent_at
        ) VALUES (
            :e, :p, :h, 'checkin_reminder',
            1, '+919876543210', 'whatsapp', 'outbound',
            'Test message', :wamid, 'sent', now()
        )
    """), {"e": row["episode_id"], "p": row["patient_id"], "h": row["hospital_id"], "wamid": wamid})
    await db.commit()

    body, headers = _signed(_receipt(wamid, "delivered"))
    res = await client.post("/api/v1/whatsapp/webhook", content=body, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"ok": True, "status_updates": 1}

    status_row = (await db.execute(
        text("SELECT status, delivered_at FROM txn.patient_message WHERE meta_message_id = :w"), {"w": wamid},
    )).mappings().one()
    assert status_row["status"] == "delivered"
    assert status_row["delivered_at"] is not None

    body, headers = _signed(_receipt(wamid, "read"))
    assert (await client.post("/api/v1/whatsapp/webhook", content=body, headers=headers)).status_code == 200

    status_row = (await db.execute(
        text("SELECT status, read_at FROM txn.patient_message WHERE meta_message_id = :w"), {"w": wamid},
    )).mappings().one()
    assert status_row["status"] == "read"
    assert status_row["read_at"] is not None
