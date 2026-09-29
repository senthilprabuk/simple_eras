import pytest

from tests.conftest import login_headers
from tests.support import admin_id_for, create_hospital


@pytest.fixture
async def superadmin(client, db):
    import uuid
    h = await create_hospital(db, f"CLN-{uuid.uuid4().hex[:6]}", role="superadmin")
    return h, await login_headers(client, h.email, h.password)


NEW = {"email": "New.Nurse@Example.org", "full_name": "New Nurse", "role": "admin", "password": "temporary-pass-123"}


async def test_roster_lists_the_hospitals_clinicians_without_secrets(client, nurse_headers):
    roster = (await client.get("/api/v1/clinicians", headers=nurse_headers)).json()
    emails = {c["email"] for c in roster}
    assert {"anitha.joseph@noyyalortho.in", "dr.arun@noyyalortho.in", "admin@noyyalortho.in"} <= emails
    assert all("hashed_password" not in c and "password" not in c for c in roster)


async def test_only_a_superadmin_manages_accounts(client, db, nurse_headers):
    assert (await client.post("/api/v1/clinicians", json=NEW, headers=nurse_headers)).status_code == 403
    surgeon = await admin_id_for(db, "dr.arun@noyyalortho.in")
    res = await client.patch(f"/api/v1/clinicians/{surgeon}", json={"is_active": False}, headers=nurse_headers)
    assert res.status_code == 403


async def test_superadmin_adds_a_clinician_who_can_then_sign_in(client, superadmin):
    _, headers = superadmin
    res = await client.post("/api/v1/clinicians", json=NEW, headers=headers)
    assert res.status_code == 201
    assert res.json()["email"] == "new.nurse@example.org"
    await login_headers(client, "new.nurse@example.org", NEW["password"])

    duplicate = await client.post("/api/v1/clinicians", json={**NEW, "email": "NEW.NURSE@example.org"}, headers=headers)
    assert duplicate.status_code == 409


async def test_weak_or_malformed_accounts_are_rejected(client, superadmin):
    _, headers = superadmin
    for body in ({**NEW, "password": "short"}, {**NEW, "email": "not-an-email"}, {**NEW, "role": "owner"}):
        assert (await client.post("/api/v1/clinicians", json=body, headers=headers)).status_code == 422


async def test_deactivated_clinician_can_no_longer_sign_in(client, superadmin):
    _, headers = superadmin
    created = (await client.post("/api/v1/clinicians", json={**NEW, "email": "leaving@example.org"}, headers=headers)).json()

    res = await client.patch(f"/api/v1/clinicians/{created['admin_user_id']}", json={"is_active": False}, headers=headers)
    assert res.status_code == 200 and res.json()["is_active"] is False

    login = await client.post("/api/v1/auth/login", json={"email": "leaving@example.org", "password": NEW["password"]})
    assert login.status_code == 401


async def test_nobody_can_demote_or_deactivate_themselves(client, superadmin):
    hospital, headers = superadmin
    for change in ({"is_active": False}, {"role": "admin"}):
        res = await client.patch(f"/api/v1/clinicians/{hospital.admin_user_id}", json=change, headers=headers)
        assert res.status_code == 400


async def test_another_hospitals_clinician_is_not_found(client, db, superadmin):
    _, headers = superadmin
    nurse = await admin_id_for(db, "anitha.joseph@noyyalortho.in")
    res = await client.patch(f"/api/v1/clinicians/{nurse}", json={"is_active": False}, headers=headers)
    assert res.status_code == 404
    await login_headers(client, "anitha.joseph@noyyalortho.in", "password123")


async def test_changing_your_own_password(client, superadmin):
    hospital, headers = superadmin
    wrong = await client.post("/api/v1/account/password",
                              json={"current_password": "nope", "new_password": "brand-new-secret-9"}, headers=headers)
    assert wrong.status_code == 400

    same = await client.post("/api/v1/account/password",
                             json={"current_password": hospital.password, "new_password": hospital.password}, headers=headers)
    assert same.status_code == 422

    ok = await client.post("/api/v1/account/password",
                           json={"current_password": hospital.password, "new_password": "brand-new-secret-9"}, headers=headers)
    assert ok.status_code == 204

    old = await client.post("/api/v1/auth/login", json={"email": hospital.email, "password": hospital.password})
    assert old.status_code == 401
    await login_headers(client, hospital.email, "brand-new-secret-9")
