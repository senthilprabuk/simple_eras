"""
Tests for Hospital WhatsApp Business Account management and QR code pairing.
"""

import httpx
import pytest
from tests.conftest import NURSE, login_headers


@pytest.mark.asyncio
async def test_get_whatsapp_account_returns_qr_code(client: httpx.AsyncClient):
    headers = await login_headers(client, *NURSE)
    res = await client.get("/api/v1/whatsapp/account", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data is not None
    assert data["display_name"] == "St. Mary's Orthopedic Helpline"
    assert data["display_phone_number"] == "+91 98765 43210"
    assert data["phone_number_id"] == "104239857123456"
    assert data["health_status"] == "healthy"
    assert data["qr_code_url"].startswith("data:image/png;base64,")
    assert "https://wa.me/919876543210" in data["click_to_chat_url"]
    assert "/api/v1/whatsapp/webhook" in data["webhook_url"]


@pytest.mark.asyncio
async def test_save_whatsapp_account(client: httpx.AsyncClient):
    headers = await login_headers(client, *NURSE)
    payload = {
        "phone_number_id": "999888777111222",
        "waba_id": "888777666555444",
        "access_token": "mock_updated_token_test",
        "verify_token": "test_verify_secret_123",
        "meta_app_id": "112233445566778",
    }
    res = await client.post("/api/v1/whatsapp/account", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["phone_number_id"] == "999888777111222"
    assert data["waba_id"] == "888777666555444"
    assert data["verify_token"] == "test_verify_secret_123"
    assert data["qr_code_url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_update_whatsapp_phone_number_and_name(client: httpx.AsyncClient):
    headers = await login_headers(client, *NURSE)
    payload = {
        "display_phone_number": "+91 94444 88888",
        "display_name": "St. Mary's Orthopedic Emergency Desk",
        "phone_number_id": "104239857123456",
        "waba_id": "108374829103948",
        "verify_token": "eras_stmarys_verify_2026",
    }
    res = await client.post("/api/v1/whatsapp/account", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["display_phone_number"] == "+91 94444 88888"
    assert data["display_name"] == "St. Mary's Orthopedic Emergency Desk"
    assert "https://wa.me/919444488888" in data["click_to_chat_url"]
    assert data["qr_code_url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_send_test_whatsapp_message(client: httpx.AsyncClient):
    headers = await login_headers(client, *NURSE)
    payload = {
        "to_phone": "+91 91234 56789",
        "message": "Clinical test check-in message",
    }
    res = await client.post("/api/v1/whatsapp/test", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "sent"
    assert data["message_id"] is not None


@pytest.mark.asyncio
async def test_disconnect_and_reconnect_whatsapp_account(client: httpx.AsyncClient):
    headers = await login_headers(client, *NURSE)

    # Disconnect
    del_res = await client.delete("/api/v1/whatsapp/account", headers=headers)
    assert del_res.status_code == 204

    # Verify None returned
    get_res = await client.get("/api/v1/whatsapp/account", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json() is None

    # Reconnect
    payload = {
        "phone_number_id": "104239857123456",
        "waba_id": "108374829103948",
        "access_token": "mock_reconnect_token",
        "verify_token": "eras_stmarys_verify_2026",
    }
    reconnect_res = await client.post("/api/v1/whatsapp/account", json=payload, headers=headers)
    assert reconnect_res.status_code == 200
    assert reconnect_res.json()["phone_number_id"] == "104239857123456"
