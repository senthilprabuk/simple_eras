from tests.conftest import login_headers
from tests.support import create_hospital


async def test_profile_shows_settings_procedures_and_activity(client, nurse_headers):
    profile = (await client.get("/api/v1/hospital", headers=nurse_headers)).json()
    assert profile["hospital_code"] == "CBE-01"
    assert profile["hospital_name"] == "St. Mary's Orthopedic Center"
    assert profile["timezone"] == "Asia/Kolkata"
    assert profile["ack_window_secs"] == 900
    assert [p["procedure_code"] for p in profile["procedures"]] == ["TKR"]
    assert profile["stats"]["active_patients"] == 14
    assert profile["stats"]["active_clinicians"] >= 3


async def test_only_a_superadmin_can_change_settings(client, nurse_headers):
    res = await client.patch("/api/v1/hospital", json={"ack_window_secs": 1200}, headers=nurse_headers)
    assert res.status_code == 403


async def test_superadmin_changes_apply_to_escalation_and_kpis(client, db):
    h = await create_hospital(db, "HOSP-EDIT", role="superadmin")
    headers = await login_headers(client, h.email, h.password)

    res = await client.patch("/api/v1/hospital", json={"ack_window_secs": 1800, "city": "Madurai"}, headers=headers)
    assert res.status_code == 200
    assert (res.json()["ack_window_secs"], res.json()["city"]) == (1800, "Madurai")

    kpis = (await client.get("/api/v1/dashboard/kpis", headers=headers)).json()
    assert kpis["ack_window_secs"] == 1800


async def test_invalid_settings_are_rejected(client, db):
    h = await create_hospital(db, "HOSP-BAD", role="superadmin")
    headers = await login_headers(client, h.email, h.password)
    for body in ({"timezone": "Mars/Olympus"}, {"ack_window_secs": 30}, {"ack_window_secs": 9000}, {"hospital_name": "  "}):
        res = await client.patch("/api/v1/hospital", json=body, headers=headers)
        assert res.status_code == 422, body


async def test_a_superadmin_cannot_touch_another_hospital(client, db, nurse_headers):
    h = await create_hospital(db, "HOSP-ISO", role="superadmin")
    headers = await login_headers(client, h.email, h.password)
    await client.patch("/api/v1/hospital", json={"hospital_name": "Renamed"}, headers=headers)

    fixture_hospital = (await client.get("/api/v1/hospital", headers=nurse_headers)).json()
    assert fixture_hospital["hospital_name"] == "St. Mary's Orthopedic Center"
    assert fixture_hospital["ack_window_secs"] == 900


async def test_the_emergency_number_is_normalised_validated_and_cleared(client, db):
    h = await create_hospital(db, "HOSP-SOS", role="superadmin")
    headers = await login_headers(client, h.email, h.password)
    assert (await client.get("/api/v1/hospital", headers=headers)).json()["emergency_phone_e164"] is None

    res = await client.patch("/api/v1/hospital", json={"emergency_phone_e164": "+91 422 555 0100"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["emergency_phone_e164"] == "+914225550100"

    for bad in ("call the ward", "0422 555 0100"):
        res = await client.patch("/api/v1/hospital", json={"emergency_phone_e164": bad}, headers=headers)
        assert res.status_code == 422, bad

    res = await client.patch("/api/v1/hospital", json={"emergency_phone_e164": ""}, headers=headers)
    assert res.json()["emergency_phone_e164"] is None


async def test_a_number_that_wording_uses_cannot_be_cleared(client, db):
    h = await create_hospital(db, "HOSP-SOS-USED", role="superadmin")
    headers = await login_headers(client, h.email, h.password)
    await client.patch("/api/v1/hospital", json={"emergency_phone_e164": "+914225550100"}, headers=headers)
    res = await client.put("/api/v1/templates/urgent_guidance/en",
                           json={"body": "Please call {hospital_phone} now."}, headers=headers)
    assert res.status_code == 200

    res = await client.patch("/api/v1/hospital", json={"emergency_phone_e164": None}, headers=headers)
    assert res.status_code == 422
    assert "urgent_guidance" in res.json()["detail"]
