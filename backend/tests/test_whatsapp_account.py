"""
The hospital's WhatsApp account: who may change it, what everyone else sees,
and that nothing on its way to a patient is made up.
"""

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.services import whatsapp
from app.services.whatsapp import SendResult
from tests.conftest import login_headers
from tests.support import create_hospital


@pytest.fixture(autouse=True)
def log_provider(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "log")


async def _superadmin(client, db, code):
    hospital = await create_hospital(db, code, role="superadmin")
    return hospital, await login_headers(client, hospital.email, hospital.password)


def _account(phone_number_id, **changes):
    return {
        "display_phone_number": "+91 90000 11111",
        "display_name": "Test Helpline",
        "phone_number_id": phone_number_id,
        "waba_id": "200000000000001",
        "access_token": "EAAG-test-token",
        "verify_token": "verify-test-secret",
        **changes,
    }


async def test_every_clinician_sees_the_account_but_not_its_secrets(client, nurse_headers):
    res = await client.get("/api/v1/whatsapp/account", headers=nurse_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["display_phone_number"] == "+91 98765 43210"
    assert data["qr_code_url"].startswith("data:image/png;base64,")
    assert data["click_to_chat_url"].startswith("https://wa.me/919876543210?text=")
    assert data["webhook_url"] == f"{settings.PUBLIC_API_BASE_URL}/api/v1/whatsapp/webhook"
    assert data["verify_token"] is None
    assert data["access_token_masked"] == "••••••••"


async def test_only_a_superadmin_can_change_the_account_or_send_from_it(client, nurse_headers):
    res = await client.post("/api/v1/whatsapp/account", json=_account("300000000000001"), headers=nurse_headers)
    assert res.status_code == 403
    assert (await client.delete("/api/v1/whatsapp/account", headers=nurse_headers)).status_code == 403
    res = await client.post("/api/v1/whatsapp/test", json={"to_phone": "+919123456789"}, headers=nurse_headers)
    assert res.status_code == 403

    still = (await client.get("/api/v1/whatsapp/account", headers=nurse_headers)).json()
    assert still["phone_number_id"] == "104239857123456"


async def test_an_account_saved_without_meta_is_unverified(client, db):
    hospital, headers = await _superadmin(client, db, "WA-CONNECT")
    assert (await client.get("/api/v1/whatsapp/account", headers=headers)).json() is None

    res = await client.post("/api/v1/whatsapp/account", json=_account("300000000000002"), headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["hospital_id"] == hospital.hospital_id
    assert data["display_phone_number"] == "+91 90000 11111"
    assert data["display_name"] == "Test Helpline"
    # The log provider checks nothing with Meta, so nothing is called healthy.
    assert data["health_status"] == "unverified"
    assert data["verify_token"] == "verify-test-secret"
    assert data["click_to_chat_url"].startswith("https://wa.me/919000011111?text=")


async def test_no_number_is_made_up_when_neither_the_form_nor_meta_gives_one(client, db):
    _, headers = await _superadmin(client, db, "WA-NONUM")
    res = await client.post(
        "/api/v1/whatsapp/account",
        json=_account("300000000000003", display_phone_number=None, display_name=None),
        headers=headers,
    )
    assert res.status_code == 400
    assert (await client.get("/api/v1/whatsapp/account", headers=headers)).json() is None


async def test_a_display_number_must_be_a_phone_number(client, db):
    _, headers = await _superadmin(client, db, "WA-BADNUM")
    res = await client.post(
        "/api/v1/whatsapp/account", json=_account("300000000000009", display_phone_number="call us"), headers=headers
    )
    assert res.status_code == 422


async def test_an_update_without_a_token_keeps_the_stored_one(client, db):
    hospital, headers = await _superadmin(client, db, "WA-KEEP")
    await client.post("/api/v1/whatsapp/account", json=_account("300000000000004"), headers=headers)

    res = await client.post(
        "/api/v1/whatsapp/account",
        json=_account("300000000000004", access_token=None, display_name="Renamed Helpline"),
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["display_name"] == "Renamed Helpline"
    stored = (await db.execute(
        text("SELECT access_token FROM meta.hospital_whatsapp WHERE hospital_id = :h"), {"h": hospital.hospital_id}
    )).scalar_one()
    assert stored == "EAAG-test-token"


async def test_a_number_connected_to_another_hospital_is_refused(client, db):
    _, headers = await _superadmin(client, db, "WA-DUP")
    # The fixture hospital's Phone Number ID
    res = await client.post("/api/v1/whatsapp/account", json=_account("104239857123456"), headers=headers)
    assert res.status_code == 409


async def test_a_test_message_goes_from_the_hospitals_own_number(client, db, monkeypatch, caplog):
    _, headers = await _superadmin(client, db, "WA-TEST")
    res = await client.post("/api/v1/whatsapp/test", json={"to_phone": "+91 91234 56789"}, headers=headers)
    assert res.status_code == 400  # nothing connected yet

    await client.post("/api/v1/whatsapp/account", json=_account("300000000000005"), headers=headers)

    res = await client.post("/api/v1/whatsapp/test", json={"to_phone": "+91 91234 56789"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "sent"
    assert "91234" not in caplog.text

    posted = []

    async def fake_post(credentials, payload, reference):
        posted.append((credentials, payload))
        return SendResult("sent", message_id="wamid.test")

    monkeypatch.setattr(whatsapp, "_post", fake_post)
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "meta")
    res = await client.post("/api/v1/whatsapp/test", json={"to_phone": "+91 91234 56789"}, headers=headers)
    assert res.json() == {"status": "sent", "message_id": "wamid.test", "error": None}
    [(credentials, payload)] = posted
    assert credentials.phone_number_id == "300000000000005"
    assert credentials.access_token == "EAAG-test-token"
    assert payload["to"] == "919123456789"


async def test_a_test_message_with_sending_disabled_says_nothing_was_sent(client, db, monkeypatch):
    _, headers = await _superadmin(client, db, "WA-OFF")
    await client.post("/api/v1/whatsapp/account", json=_account("300000000000006"), headers=headers)
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "disabled")

    res = await client.post("/api/v1/whatsapp/test", json={"to_phone": "+919123456789"}, headers=headers)
    assert res.json()["status"] == "queued"
    assert "nothing was sent" in res.json()["error"]


async def test_disconnect_and_reconnect(client, db):
    _, headers = await _superadmin(client, db, "WA-DISC")
    await client.post("/api/v1/whatsapp/account", json=_account("300000000000007"), headers=headers)

    assert (await client.delete("/api/v1/whatsapp/account", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/whatsapp/account", headers=headers)).json() is None

    # Reconnecting needs the token again: nothing is kept after a disconnect.
    res = await client.post("/api/v1/whatsapp/account", json=_account("300000000000007", access_token=None), headers=headers)
    assert res.status_code == 400
    res = await client.post("/api/v1/whatsapp/account", json=_account("300000000000007"), headers=headers)
    assert res.status_code == 200
