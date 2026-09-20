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
        "gender": "female",
        "address": {"line": "12 Race Course Road", "city": "Coimbatore", "district": "Coimbatore",
                    "state": "Tamil Nadu", "postal_code": "641018"},
        "alt_phone_e164": "+919876500001",
        "email": "lakshmi@example.com",
        "emergency_contacts": [{"name": "Arun Narayanan", "relationship": "son", "phone_e164": "+919812345678"}],
        "procedure_code": "TKR",
        "operative_side": "right",
        "surgery_date": str(today - timedelta(days=4)),
        "discharge_date": str(today - timedelta(days=2)),
        "checkin_window": "evening",
        "consent_version": "v1",
        "consent_confirmed": True,
        "data_processing_consent": True,
        "contact_sharing_consent": True,
        "baseline": {"temp_c": 36.9, "hr": 78, "walk_aid": "walker"},
    }
    body.update(overrides)
    return body


async def _enroll(client, headers, **overrides):
    today = date.fromisoformat((await _options(client, headers))["today"])
    return await client.post("/api/v1/enrollment", json=_form(today, **overrides), headers=headers)


async def _summary(client, headers, episode_id):
    res = await client.get(f"/api/v1/episodes/{episode_id}/summary", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def test_options_list_the_offered_procedure_and_baseline_measures(client, ward):
    _, headers = ward
    options = await _options(client, headers)
    assert [(p["procedure_code"], p["ruleset_version"], p["observation_days"]) for p in options["procedures"]] == \
        [("TKR", "1.0.0", 84)]
    assert [p["code"] for p in options["baseline_parameters"]] == \
        ["height_cm", "weight_kg", "bp_sys", "bp_dia", "temp_c", "hr", "spo2", "pain", "knee_bend", "walk_aid"]
    walk = next(p for p in options["baseline_parameters"] if p["code"] == "walk_aid")
    assert [o["code"] for o in walk["options"]] == ["walker", "crutch", "cane", "none"]
    assert options["languages"] == ["en", "ta", "hi"]
    assert [(w["code"], w["start"], w["end"]) for w in options["checkin_windows"]] == [
        ("morning", "08:00:00", "10:00:00"), ("midday", "12:00:00", "14:00:00"), ("evening", "17:00:00", "19:00:00"),
    ]
    assert options["privacy_law"] == "DPDP-2023"


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


async def test_safety_details_reach_the_patient_summary(client, ward):
    _, headers = ward
    res = await _enroll(client, headers, emergency_contacts=[
        {"name": "Arun Narayanan", "relationship": "son", "phone_e164": "+919812345678"},
        {"name": "Meera Arun", "relationship": "other_family", "phone_e164": "+919812345679"},
    ], baseline={"height_cm": 158, "weight_kg": 71.4, "bp_sys": 138, "bp_dia": 84})
    assert res.status_code == 201, res.text

    summary = await _summary(client, headers, res.json()["episode_id"])
    assert (summary["gender"], summary["age_years"] > 60) == ("female", True)
    assert summary["address"] == {"line": "12 Race Course Road", "city": "Coimbatore", "district": "Coimbatore",
                                  "state": "Tamil Nadu", "postal_code": "641018"}
    assert (summary["alt_phone_e164"], summary["email"]) == ("+919876500001", "lakshmi@example.com")
    assert [(c["name"], c["relationship"]) for c in summary["emergency_contacts"]] == \
        [("Arun Narayanan", "son"), ("Meera Arun", "other_family")]
    assert (summary["checkin_window_start"], summary["checkin_window_end"]) == ("17:00:00", "19:00:00")
    assert summary["body"] == {"height_cm": 158.0, "weight_kg": 71.4, "bmi": 28.6, "bp_systolic": 138, "bp_diastolic": 84}
    assert {(c["code"], c["granted"], c["privacy_law"]) for c in summary["consents"]} == {
        ("remote_monitoring", True, "DPDP-2023"), ("data_processing", True, "DPDP-2023"),
        ("contact_sharing", True, "DPDP-2023"),
    }
    # Body measurements are recorded, never scored: they stay out of the check-in comparison.
    assert not {"height_cm", "weight_kg", "bp_sys", "bp_dia"} & {r["code"] for r in summary["readings"]}


async def test_a_refusal_to_share_with_contacts_is_recorded_not_dropped(client, ward):
    _, headers = ward
    res = await _enroll(client, headers, contact_sharing_consent=False)
    assert res.status_code == 201, res.text
    consents = (await _summary(client, headers, res.json()["episode_id"]))["consents"]
    assert next(c for c in consents if c["code"] == "contact_sharing")["granted"] is False


async def test_phone_numbers_are_accepted_the_way_they_are_printed(client, ward):
    _, headers = ward
    res = await _enroll(client, headers, phone_e164="+91 98765 43210", alt_phone_e164="+91-98765-00001",
                        emergency_contacts=[{"name": "Arun", "relationship": "son", "phone_e164": "+91 (98123) 45678"}])
    assert res.status_code == 201, res.text
    summary = await _summary(client, headers, res.json()["episode_id"])
    assert (summary["phone_e164"], summary["alt_phone_e164"], summary["emergency_contacts"][0]["phone_e164"]) == \
        ("+919876543210", "+919876500001", "+919812345678")


async def test_optional_contact_channels_may_be_left_blank(client, ward):
    _, headers = ward
    res = await _enroll(client, headers, alt_phone_e164="", email="  ",
                        address={"line": "12 Race Course Road", "district": "Coimbatore", "postal_code": "641018",
                                 "city": "", "state": None})
    assert res.status_code == 201, res.text
    summary = await _summary(client, headers, res.json()["episode_id"])
    assert (summary["alt_phone_e164"], summary["email"], summary["address"]["city"]) == (None, None, None)


async def test_enrolled_patient_is_invisible_to_other_hospitals(client, ward, nurse_headers):
    _, headers = ward
    res = await _enroll(client, headers, mrn="ISO-1", patient_name="Isolated Person")
    assert (await client.get("/api/v1/patients?search=Isolated", headers=nurse_headers)).json()["total"] == 0
    other = await client.get(f"/api/v1/episodes/{res.json()['episode_id']}/summary", headers=nurse_headers)
    assert other.status_code == 404


async def test_same_mrn_is_refused_while_monitored_or_if_the_name_differs(client, ward):
    _, headers = ward
    assert (await _enroll(client, headers, mrn="DUP-1")).status_code == 201

    again = await _enroll(client, headers, mrn="DUP-1")
    assert again.status_code == 409
    assert "already being monitored" in again.json()["detail"]

    other = await _enroll(client, headers, mrn="DUP-1", patient_name="Someone Else")
    assert other.status_code == 409
    assert "different patient" in other.json()["detail"]


async def test_returning_patient_gets_a_new_episode_with_refreshed_details(client, db, ward):
    _, headers = ward
    first = (await _enroll(client, headers, mrn="RET-1")).json()
    await db.execute(text("UPDATE txn.patient_episode SET status = 'completed' WHERE episode_id = :e"),
                     {"e": first["episode_id"]})
    await db.commit()

    second = await _enroll(
        client, headers, mrn="RET-1", patient_name="lakshmi narayanan", email="",
        address={"line": "4 New Street", "district": "Tiruppur", "postal_code": "641601"},
        emergency_contacts=[{"name": "Kala Devi", "relationship": "caregiver", "phone_e164": "+919800000009"}],
    )
    assert second.status_code == 201, second.text
    assert second.json()["returning_patient"] is True
    assert second.json()["patient_id"] == first["patient_id"]
    assert second.json()["episode_id"] != first["episode_id"]

    summary = await _summary(client, headers, second.json()["episode_id"])
    assert [c["name"] for c in summary["emergency_contacts"]] == ["Kala Devi"]
    assert (summary["address"]["line"], summary["address"]["district"]) == ("4 New Street", "Tiruppur")
    # Blank optional details keep what was recorded before.
    assert (summary["email"], summary["address"]["city"]) == ("lakshmi@example.com", "Coimbatore")


@pytest.mark.parametrize("overrides", [
    {"phone_e164": "9876543210"},
    {"consent_confirmed": False},
    {"data_processing_consent": False},
    {"contact_sharing_consent": None},
    {"language_code": "fr"},
    {"patient_name": "   "},
    {"gender": None},
    {"gender": "f"},
    {"address": {"line": "12 Race Course Road", "district": "Coimbatore", "postal_code": "6410!8"}},
    {"address": {"line": " ", "district": "Coimbatore", "postal_code": "641018"}},
    {"address": {"line": "12 Race Course Road", "postal_code": "641018"}},
    {"email": "lakshmi.example.com"},
    {"alt_phone_e164": "+919876543210"},
    {"emergency_contacts": []},
    {"emergency_contacts": [{"name": "Arun", "relationship": "son", "phone_e164": "+919876543210"}]},
    {"emergency_contacts": [{"name": "Arun", "relationship": "son", "phone_e164": "+919812345678"},
                            {"name": "Meera", "relationship": "spouse", "phone_e164": "+91 98123 45678"}]},
    {"emergency_contacts": [{"name": "Arun", "relationship": "cousin", "phone_e164": "+919812345678"}]},
    {"emergency_contacts": [{"name": f"C{i}", "relationship": "son", "phone_e164": f"+91981234567{i}"} for i in range(4)]},
    {"checkin_window": "night"},
    {"baseline": {"temp_c": 50}},
    {"baseline": {"height_cm": 45}},
    {"baseline": {"bp_sys": 80, "bp_dia": 90}},
    {"baseline": {"redness": True}},
    {"baseline": {"walk_aid": "wheelchair"}},
])
async def test_invalid_enrollments_are_rejected(client, ward, overrides):
    _, headers = ward
    res = await _enroll(client, headers, mrn="BAD-1", **overrides)
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


async def test_every_patient_table_clinicians_can_read_is_tenant_isolated(db):
    """A txn table the clinician role can read without row-level security would leak across hospitals."""
    tables = (await db.execute(text("""
        SELECT c.relname,
               c.relrowsecurity AND EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid) AS isolated
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'txn' AND c.relkind = 'r' AND has_table_privilege('eras_app', c.oid, 'SELECT')
    """))).all()
    assert {"patient_contact", "episode_consent"} <= {name for name, _ in tables}
    assert [name for name, isolated in tables if not isolated] == []
