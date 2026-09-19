from datetime import date, timedelta

import pytest
from sqlalchemy import text

from tests.conftest import login_headers
from tests.support import create_hospital


@pytest.fixture
async def ward(client, db):
    """A dedicated hospital, so enrollments never change the fixture hospital's counts."""
    import uuid
    h = await create_hospital(db, f"ENR-{uuid.uuid4().hex[:6]}")
    return h, await login_headers(client, h.email, h.password)


async def _options(client, headers):
    res = await client.get("/api/v1/enrollment/options", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _form(today: date, **overrides):
    body = {
        "patient_name": "Lakshmi Narayanan",
        "mrn": "MRN-4471",
        "phone_e164": "+919876543210",
        "language_code": "ta",
        "date_of_birth": "1958-03-14",
        "procedure_code": "TKR",
        "surgery_date": str(today - timedelta(days=4)),
        "discharge_date": str(today - timedelta(days=2)),
        "consent_version": "v1",
        "consent_confirmed": True,
        "baseline": {"temp_c": 36.9, "hr": 78, "walk_aid": "walker"},
    }
    body.update(overrides)
    return body


async def test_options_list_the_offered_procedure_and_baseline_measures(client, ward):
    _, headers = ward
    options = await _options(client, headers)
    assert [(p["procedure_code"], p["ruleset_version"], p["observation_days"]) for p in options["procedures"]] == \
        [("TKR", "1.0.0", 84)]
    assert [p["code"] for p in options["baseline_parameters"]] == ["temp_c", "hr", "spo2", "pain", "knee_bend", "walk_aid"]
    walk = next(p for p in options["baseline_parameters"] if p["code"] == "walk_aid")
    assert [o["code"] for o in walk["options"]] == ["walker", "crutch", "cane", "none"]
    assert options["languages"] == ["en", "ta", "hi"]


async def test_enrollment_creates_patient_episode_and_baseline(client, db, ward):
    hospital, headers = ward
    today = date.fromisoformat((await _options(client, headers))["today"])

    res = await client.post("/api/v1/enrollment", json=_form(today), headers=headers)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["returning_patient"] is False
    assert data["post_op_day"] == 2
    assert data["baseline_recorded"] == 3
    assert data["monitoring_ends_on"] == str(today - timedelta(days=2) + timedelta(days=84))

    row = (await db.execute(text("""
        SELECT e.hospital_id, e.enrolled_by, e.status, r.status AS ruleset_status, p.language_code,
               (SELECT count(*) FROM txn.episode_baseline b WHERE b.episode_id = e.episode_id) AS baselines
        FROM txn.patient_episode e
        JOIN txn.patient p ON p.patient_id = e.patient_id
        JOIN meta.ruleset r ON r.ruleset_id = e.ruleset_id
        WHERE e.episode_id = :e
    """), {"e": data["episode_id"]})).mappings().one()
    assert row["hospital_id"] == hospital.hospital_id
    assert row["enrolled_by"] == hospital.admin_user_id
    assert (row["status"], row["ruleset_status"], row["language_code"], row["baselines"]) == \
        ("active", "approved", "ta", 3)

    listed = (await client.get("/api/v1/patients?search=MRN-4471", headers=headers)).json()["items"]
    assert [p["patient_name"] for p in listed] == ["Lakshmi Narayanan"]


async def test_enrolled_patient_is_invisible_to_other_hospitals(client, ward, nurse_headers):
    _, headers = ward
    today = date.fromisoformat((await _options(client, headers))["today"])
    await client.post("/api/v1/enrollment", json=_form(today, mrn="ISO-1", patient_name="Isolated Person"), headers=headers)
    assert (await client.get("/api/v1/patients?search=Isolated", headers=nurse_headers)).json()["total"] == 0


async def test_same_mrn_is_refused_while_monitored_or_if_the_name_differs(client, ward):
    _, headers = ward
    today = date.fromisoformat((await _options(client, headers))["today"])
    assert (await client.post("/api/v1/enrollment", json=_form(today, mrn="DUP-1"), headers=headers)).status_code == 201

    again = await client.post("/api/v1/enrollment", json=_form(today, mrn="DUP-1"), headers=headers)
    assert again.status_code == 409
    assert "already being monitored" in again.json()["detail"]

    other = await client.post("/api/v1/enrollment", json=_form(today, mrn="DUP-1", patient_name="Someone Else"), headers=headers)
    assert other.status_code == 409
    assert "different patient" in other.json()["detail"]


async def test_returning_patient_gets_a_new_episode_on_the_same_record(client, db, ward):
    _, headers = ward
    today = date.fromisoformat((await _options(client, headers))["today"])
    first = (await client.post("/api/v1/enrollment", json=_form(today, mrn="RET-1"), headers=headers)).json()
    await db.execute(text("UPDATE txn.patient_episode SET status = 'completed' WHERE episode_id = :e"),
                     {"e": first["episode_id"]})
    await db.commit()

    second = await client.post("/api/v1/enrollment", json=_form(today, mrn="RET-1", patient_name="lakshmi narayanan"),
                               headers=headers)
    assert second.status_code == 201
    assert second.json()["returning_patient"] is True
    assert second.json()["patient_id"] == first["patient_id"]
    assert second.json()["episode_id"] != first["episode_id"]


@pytest.mark.parametrize("overrides", [
    {"phone_e164": "9876543210"},
    {"consent_confirmed": False},
    {"language_code": "fr"},
    {"patient_name": "   "},
    {"baseline": {"temp_c": 50}},
    {"baseline": {"redness": True}},
    {"baseline": {"walk_aid": "wheelchair"}},
])
async def test_invalid_enrollments_are_rejected(client, ward, overrides):
    _, headers = ward
    today = date.fromisoformat((await _options(client, headers))["today"])
    res = await client.post("/api/v1/enrollment", json=_form(today, mrn="BAD-1", **overrides), headers=headers)
    assert res.status_code == 422, overrides


async def test_dates_must_make_sense(client, ward):
    _, headers = ward
    today = date.fromisoformat((await _options(client, headers))["today"])
    before_surgery = _form(today, surgery_date=str(today - timedelta(days=1)), discharge_date=str(today - timedelta(days=3)))
    future = _form(today, surgery_date=str(today), discharge_date=str(today + timedelta(days=1)))
    for body in (before_surgery, future):
        assert (await client.post("/api/v1/enrollment", json=body, headers=headers)).status_code == 422


async def test_procedure_must_be_offered_by_the_hospital(client, db):
    h = await create_hospital(db, "ENR-NOTKR", offers_tkr=False)
    headers = await login_headers(client, h.email, h.password)
    assert (await _options(client, headers))["procedures"] == []
    today = date.fromisoformat((await _options(client, headers))["today"])
    res = await client.post("/api/v1/enrollment", json=_form(today), headers=headers)
    assert res.status_code == 400
