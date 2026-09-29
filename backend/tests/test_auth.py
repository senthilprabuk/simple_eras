from datetime import timedelta
from uuid import uuid4

import httpx
import jwt
from sqlalchemy import text

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from tests.conftest import NURSE, login_headers
from tests.support import PASSWORD, create_hospital

GENERIC_401 = "Invalid email or password"


async def test_login_success(client: httpx.AsyncClient):
    res = await client.post("/api/v1/auth/login", json={"email": NURSE[0], "password": NURSE[1]})
    assert res.status_code == 200
    data = res.json()
    assert data["token_type"] == "bearer"
    assert data["full_name"] == "Anitha Joseph"
    assert data["role"] == "admin"
    assert data["hospital_id"] == 1
    assert data["hospital_name"] == "Noyyal Orthopaedic Centre"
    assert data["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


async def test_login_case_insensitive_email(client: httpx.AsyncClient):
    res = await client.post("/api/v1/auth/login", json={"email": "  ANITHA.JOSEPH@NOYYALORTHO.IN  ", "password": NURSE[1]})
    assert res.status_code == 200
    assert res.json()["full_name"] == "Anitha Joseph"


async def test_wrong_password_unknown_email_and_inactive_account_are_indistinguishable(client, db):
    await db.execute(text("""
        INSERT INTO meta.admin_user (hospital_id, email, hashed_password, full_name, is_active)
        VALUES (1, 'retired.nurse@noyyalortho.in', :pwd, 'Retired Nurse', false)
    """), {"pwd": get_password_hash(PASSWORD)})
    await db.commit()

    attempts = [
        {"email": NURSE[0], "password": "wrong-password"},
        {"email": "nobody@noyyalortho.in", "password": "anything"},
        {"email": "retired.nurse@noyyalortho.in", "password": PASSWORD},  # right password, inactive
    ]
    for body in attempts:
        res = await client.post("/api/v1/auth/login", json=body)
        assert res.status_code == 401, body
        assert res.json()["detail"] == GENERIC_401, body


async def test_repeated_failures_lock_the_account_for_that_client(client: httpx.AsyncClient):
    for _ in range(settings.LOGIN_MAX_FAILURES_PER_ACCOUNT):
        res = await client.post("/api/v1/auth/login", json={"email": NURSE[0], "password": "guess"})
        assert res.status_code == 401

    # Locked even with the right password, until the window passes.
    res = await client.post("/api/v1/auth/login", json={"email": NURSE[0], "password": NURSE[1]})
    assert res.status_code == 429

    # A different account from the same client is unaffected.
    res = await client.post("/api/v1/auth/login", json={"email": "dr.arun@noyyalortho.in", "password": "password123"})
    assert res.status_code == 200


async def test_same_account_at_two_hospitals_needs_a_choice_only_after_the_password_matches(client, db):
    a = await create_hospital(db, "DUP-A")
    b = await create_hospital(db, "DUP-B")
    shared = "shared.clinician@example.org"
    await db.execute(text("UPDATE meta.admin_user SET email = :e WHERE admin_user_id IN (:a, :b)"),
                     {"e": shared, "a": a.admin_user_id, "b": b.admin_user_id})
    await db.commit()

    # A wrong password gets the ordinary 401, so a guesser learns nothing.
    res = await client.post("/api/v1/auth/login", json={"email": shared, "password": "wrong"})
    assert res.status_code == 401
    assert res.json()["detail"] == GENERIC_401

    res = await client.post("/api/v1/auth/login", json={"email": shared, "password": PASSWORD})
    assert res.status_code == 400
    offered = {h["hospital_id"] for h in res.json()["detail"]["hospitals"]}
    assert offered == {a.hospital_id, b.hospital_id}

    res = await client.post("/api/v1/auth/login", json={"email": shared, "password": PASSWORD, "hospital_id": b.hospital_id})
    assert res.status_code == 200
    assert res.json()["hospital_id"] == b.hospital_id


async def test_unauthenticated_access(client: httpx.AsyncClient):
    assert (await client.get("/api/v1/dashboard/queue")).status_code == 401


async def test_invalid_bearer_token(client: httpx.AsyncClient):
    res = await client.get("/api/v1/dashboard/queue", headers={"Authorization": "Bearer not-a-valid-jwt-token"})
    assert res.status_code == 401


async def test_forged_signature_token(client: httpx.AsyncClient):
    forged = jwt.encode({"sub": str(uuid4()), "hospital_id": 1, "role": "admin"}, "x" * 40, algorithm="HS256")
    res = await client.get("/api/v1/dashboard/queue", headers={"Authorization": f"Bearer {forged}"})
    assert res.status_code == 401


async def test_expired_token(client: httpx.AsyncClient, nurse_headers):
    me = await client.post("/api/v1/auth/login", json={"email": NURSE[0], "password": NURSE[1]})
    claims = {"sub": me.json()["admin_user_id"], "hospital_id": 1, "role": "admin"}
    expired = create_access_token(claims, expires_delta=timedelta(seconds=-1))
    res = await client.get("/api/v1/dashboard/queue", headers={"Authorization": f"Bearer {expired}"})
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()


async def test_token_for_deactivated_admin_is_rejected(client: httpx.AsyncClient, db):
    h = await create_hospital(db, "DEACT")
    headers = await login_headers(client, h.email, h.password)
    await db.execute(text("UPDATE meta.admin_user SET is_active = false WHERE admin_user_id = :a"),
                     {"a": h.admin_user_id})
    await db.commit()
    assert (await client.get("/api/v1/dashboard/queue", headers=headers)).status_code == 401
