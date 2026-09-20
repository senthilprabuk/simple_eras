from uuid import uuid4
import pytest
from sqlalchemy import text

from app.core.config import settings


@pytest.mark.asyncio
async def test_webhook_handshake(client):
    # Success handshake
    res = await client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.META_WEBHOOK_VERIFY_TOKEN,
            "hub.challenge": "1158201244",
        },
    )
    assert res.status_code == 200
    assert res.text == "1158201244"

    # Mismatch token handshake
    res_bad = await client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "1158201244",
        },
    )
    assert res_bad.status_code == 403


@pytest.mark.asyncio
async def test_webhook_status_receipts(client, db):
    # Insert a dummy sent message
    row = (await db.execute(text("""
        SELECT e.episode_id, e.patient_id, e.hospital_id
        FROM txn.patient_episode e
        WHERE e.status = 'active'
        LIMIT 1
    """))).mappings().first()
    assert row is not None

    wamid = f"wamid.test_{uuid4().hex}"
    await db.execute(
        text("""
            INSERT INTO txn.patient_message (
                episode_id, patient_id, hospital_id, message_type,
                day_after_discharge, phone_e164, channel, direction,
                body, meta_message_id, status, sent_at
            ) VALUES (
                :e, :p, :h, 'checkin_reminder',
                1, '+919876543210', 'whatsapp', 'outbound',
                'Test message', :wamid, 'sent', now()
            )
        """),
        {"e": row["episode_id"], "p": row["patient_id"], "h": row["hospital_id"], "wamid": wamid},
    )
    await db.commit()

    # Post 'delivered' status receipt
    delivered_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "12345", "phone_number_id": "67890"},
                    "statuses": [{
                        "id": wamid,
                        "status": "delivered",
                        "timestamp": "1726830000",
                        "recipient_id": "919876543210",
                    }],
                },
                "field": "messages",
            }],
        }],
    }

    res = await client.post("/api/v1/whatsapp/webhook", json=delivered_payload)
    assert res.status_code == 200
    assert res.json()["status_updates"] >= 1

    status_row = (await db.execute(
        text("SELECT status, delivered_at FROM txn.patient_message WHERE meta_message_id = :w"),
        {"w": wamid},
    )).mappings().first()
    assert status_row["status"] == "delivered"
    assert status_row["delivered_at"] is not None

    # Post 'read' status receipt
    read_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "12345", "phone_number_id": "67890"},
                    "statuses": [{
                        "id": wamid,
                        "status": "read",
                        "timestamp": "1726830100",
                        "recipient_id": "919876543210",
                    }],
                },
                "field": "messages",
            }],
        }],
    }

    res2 = await client.post("/api/v1/whatsapp/webhook", json=read_payload)
    assert res2.status_code == 200

    status_row2 = (await db.execute(
        text("SELECT status, read_at FROM txn.patient_message WHERE meta_message_id = :w"),
        {"w": wamid},
    )).mappings().first()
    assert status_row2["status"] == "read"
    assert status_row2["read_at"] is not None
