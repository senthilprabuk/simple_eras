import pytest
import httpx
import jwt
from uuid import uuid4

@pytest.mark.asyncio
async def test_login_success(client: httpx.AsyncClient):
    response = await client.post("/api/v1/auth/login", json={
        "email": "nurse.sarah@stmarys.org",
        "password": "password123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["full_name"] == "Nurse Sarah Jenkins"
    assert data["role"] == "admin"
    assert data["hospital_id"] == 1
    assert "admin_user_id" in data

@pytest.mark.asyncio
async def test_login_case_insensitive_email(client: httpx.AsyncClient):
    response = await client.post("/api/v1/auth/login", json={
        "email": "  NURSE.SARAH@STMARYS.ORG  ",
        "password": "password123"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Nurse Sarah Jenkins"

@pytest.mark.asyncio
async def test_login_wrong_password(client: httpx.AsyncClient):
    response = await client.post("/api/v1/auth/login", json={
        "email": "nurse.sarah@stmarys.org",
        "password": "incorrect_password"
    })
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data

@pytest.mark.asyncio
async def test_login_unknown_email(client: httpx.AsyncClient):
    response = await client.post("/api/v1/auth/login", json={
        "email": "nonexistent.user@stmarys.org",
        "password": "password123"
    })
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_unauthenticated_access(client: httpx.AsyncClient):
    response = await client.get("/api/v1/dashboard/queue")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_invalid_bearer_token(client: httpx.AsyncClient):
    response = await client.get(
        "/api/v1/dashboard/queue",
        headers={"Authorization": "Bearer not-a-valid-jwt-token"}
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_forged_signature_token(client: httpx.AsyncClient):
    forged_token = jwt.encode(
        {"sub": str(uuid4()), "hospital_id": 1, "role": "admin"},
        "wrong-secret-key-that-does-not-match",
        algorithm="HS256"
    )
    response = await client.get(
        "/api/v1/dashboard/queue",
        headers={"Authorization": f"Bearer {forged_token}"}
    )
    assert response.status_code == 401
