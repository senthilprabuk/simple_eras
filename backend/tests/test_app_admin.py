import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import login_headers

APP_ADMIN = ("appadmin@eras.local", "password123")


@pytest.fixture
async def admin_headers(client):
    return await login_headers(client, *APP_ADMIN)


def _code(prefix: str = "T") -> str:
    return f"{prefix}{uuid.uuid4().hex[:6].upper()}"


def _hospital(code: str, **overrides):
    body = {
        "hospital_code": code, "hospital_name": f"Hospital {code}", "city": "Salem", "timezone": "Asia/Kolkata",
        "ack_window_secs": 600, "privacy_law": "DPDP-2023", "is_active": True, "procedure_codes": ["TKR"],
    }
    body.update(overrides)
    return body


async def _create_hospital(client, headers, **overrides):
    res = await client.post("/api/v1/app-admin/hospitals", json=_hospital(_code(), **overrides), headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def _add_account(client, headers, hospital_id, email, role="superadmin"):
    res = await client.post(f"/api/v1/app-admin/hospitals/{hospital_id}/accounts", headers=headers, json={
        "email": email, "full_name": "First Admin", "role": role, "password": "temporary-pass-123",
    })
    assert res.status_code == 201, res.text
    return res.json()


async def _procedure_with_approved_ruleset(db):
    """A throwaway procedure, so approving its versions never changes the TKR ruleset other tests use."""
    code = _code("P")
    procedure_id = (await db.execute(text("""
        INSERT INTO meta.surgical_procedure (procedure_code, procedure_name, observation_days)
        VALUES (:code, :name, 42) RETURNING procedure_id
    """), {"code": code, "name": f"Test procedure {code}"})).scalar_one()
    ruleset_id = (await db.execute(text("""
        INSERT INTO meta.ruleset (procedure_id, version, review_at, critical_at, status, approved_by, approved_at)
        VALUES (:p, '1.0.0', 4, 8, 'approved', 'Dr Test', now()) RETURNING ruleset_id
    """), {"p": procedure_id})).scalar_one()
    await db.execute(text("""
        INSERT INTO meta.procedure_parameter
            (ruleset_id, parameter_id, display_order, display_section, collect_from_day, collect_to_day,
             score_from_day, score_to_day, parameter_weight, scoring_config, question_text)
        SELECT :r, p.parameter_id, v.ord, v.section, 0, 42, 0, 42, v.weight, CAST(v.cfg AS jsonb), v.question
        FROM (VALUES ('temp_c', 1, 'readings', 3,
                      '{"direction": "higher_is_worse", "bands": [[0, 37.5, 0], [37.5, 38.5, 1], [38.5, 99, 3]]}',
                      'Temperature?'),
                     ('breathless', 2, 'checks', 3, '{"binary_score": 3, "emergency": true}', 'Breathless?'))
             AS v(code, ord, section, weight, cfg, question)
        JOIN meta.parameter p ON p.parameter_code = v.code
    """), {"r": ruleset_id})
    await db.commit()
    return code, ruleset_id


PAIN = {
    "display_section": "readings", "display_order": 3, "collect_from_day": 0, "collect_to_day": 42,
    "score_from_day": 0, "score_to_day": 42, "weight": 2, "question_text": "How bad is your pain?",
    "scoring_config": {"direction": "higher_is_worse", "bands": [[0, 5, 0], [5, 8, 1], [8, 99, 3]]},
}


# ---------------------------------------------------------------- access

async def test_app_admin_signs_in_without_a_hospital(client):
    res = await client.post("/api/v1/auth/login", json={"email": APP_ADMIN[0], "password": APP_ADMIN[1]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["role"], body["hospital_id"], body["hospital_name"]) == ("app_admin", None, None)


async def test_app_admin_cannot_open_patient_screens(client, admin_headers):
    for path in ("/api/v1/patients", "/api/v1/dashboard/queue", "/api/v1/enrollment/options"):
        assert (await client.get(path, headers=admin_headers)).status_code == 403, path


async def test_clinicians_cannot_open_the_admin_area(client, nurse_headers):
    for path in ("/api/v1/app-admin/hospitals", "/api/v1/app-admin/rulesets"):
        assert (await client.get(path, headers=nurse_headers)).status_code == 403, path


async def test_platform_role_has_no_access_to_patient_data(db):
    await db.execute(text("SET LOCAL ROLE eras_platform"))
    counts = (await db.execute(text("SELECT sum(active_episodes) FROM meta.platform_usage()"))).scalar_one()
    assert counts >= 12
    with pytest.raises(DBAPIError, match="permission denied"):
        await db.execute(text("SELECT count(*) FROM txn.patient"))
    await db.rollback()


# ------------------------------------------------------------- hospitals

async def test_hospital_list_counts_patients_without_reading_them(client, admin_headers):
    hospitals = (await client.get("/api/v1/app-admin/hospitals", headers=admin_headers)).json()
    stmarys = next(h for h in hospitals if h["hospital_code"] == "CBE-01")
    assert (stmarys["active_patients"], stmarys["procedure_codes"], stmarys["privacy_law"]) == (14, ["TKR"], "DPDP-2023")
    assert stmarys["account_count"] >= 1


async def test_a_new_hospital_and_its_first_superadmin(client, admin_headers):
    created = await _create_hospital(client, admin_headers, hospital_code="new-" + uuid.uuid4().hex[:4])
    assert created["hospital_code"].startswith("NEW-")
    assert (created["procedure_codes"], created["accounts"], created["active_patients"]) == (["TKR"], [], 0)

    email = f"lead.{created['hospital_code'].lower()}@example.org"
    detail = await _add_account(client, admin_headers, created["hospital_id"], email)
    assert [(a["email"], a["role"]) for a in detail["accounts"]] == [(email, "superadmin")]

    signed_in = await client.post("/api/v1/auth/login", json={"email": email, "password": "temporary-pass-123"})
    assert signed_in.status_code == 200
    assert signed_in.json()["hospital_name"] == created["hospital_name"]


async def test_hospital_codes_are_unique(client, admin_headers):
    code = _code()
    assert (await client.post("/api/v1/app-admin/hospitals", json=_hospital(code), headers=admin_headers)).status_code == 201
    again = await client.post("/api/v1/app-admin/hospitals", json=_hospital(code.lower()), headers=admin_headers)
    assert again.status_code == 409


@pytest.mark.parametrize("overrides", [
    {"timezone": "Mars/Olympus"},
    {"procedure_codes": ["NOPE"]},
    {"ack_window_secs": 30},
    {"hospital_code": "x"},
    {"privacy_law": "GDPR"},
    {"hospital_name": "  "},
])
async def test_invalid_hospitals_are_rejected(client, admin_headers, overrides):
    res = await client.post("/api/v1/app-admin/hospitals", json=_hospital(_code(), **overrides), headers=admin_headers)
    assert res.status_code == 422, overrides


async def test_editing_a_hospital_and_the_procedures_it_offers(client, admin_headers):
    created = await _create_hospital(client, admin_headers)
    path = f"/api/v1/app-admin/hospitals/{created['hospital_id']}"
    body = _hospital(created["hospital_code"], hospital_name="Renamed", procedure_codes=[], ack_window_secs=1200)
    del body["hospital_code"]

    edited = (await client.put(path, json=body, headers=admin_headers)).json()
    assert (edited["hospital_name"], edited["procedure_codes"], edited["ack_window_secs"]) == ("Renamed", [], 1200)

    body["procedure_codes"] = ["TKR"]
    assert (await client.put(path, json=body, headers=admin_headers)).json()["procedure_codes"] == ["TKR"]
    assert (await client.put("/api/v1/app-admin/hospitals/999999", json=body, headers=admin_headers)).status_code == 404


async def test_deactivating_a_hospital_signs_its_clinicians_out(client, admin_headers):
    created = await _create_hospital(client, admin_headers)
    email = f"nurse.{created['hospital_code'].lower()}@example.org"
    await _add_account(client, admin_headers, created["hospital_id"], email, role="admin")
    clinician = await login_headers(client, email, "temporary-pass-123")
    assert (await client.get("/api/v1/patients", headers=clinician)).status_code == 200

    body = _hospital(created["hospital_code"], is_active=False)
    del body["hospital_code"]
    await client.put(f"/api/v1/app-admin/hospitals/{created['hospital_id']}", json=body, headers=admin_headers)

    assert (await client.get("/api/v1/patients", headers=clinician)).status_code == 401
    refused = await client.post("/api/v1/auth/login", json={"email": email, "password": "temporary-pass-123"})
    assert refused.status_code == 401


async def test_a_duplicate_account_is_refused(client, admin_headers):
    created = await _create_hospital(client, admin_headers)
    email = f"dup.{created['hospital_code'].lower()}@example.org"
    await _add_account(client, admin_headers, created["hospital_id"], email)
    again = await client.post(f"/api/v1/app-admin/hospitals/{created['hospital_id']}/accounts", headers=admin_headers,
                              json={"email": email, "full_name": "Again", "role": "admin", "password": "temporary-pass-123"})
    assert again.status_code == 409


# -------------------------------------------------------------- rulesets

async def test_ruleset_list_shows_each_version_and_who_uses_it(client, admin_headers):
    procedures = (await client.get("/api/v1/app-admin/rulesets", headers=admin_headers)).json()
    tkr = next(p for p in procedures if p["procedure_code"] == "TKR")
    approved = next(v for v in tkr["versions"] if v["status"] == "approved")
    assert (approved["version"], approved["parameter_count"]) == ("1.0.0", 12)
    assert approved["active_episodes"] >= 12
    assert tkr["hospitals_offering"] >= 1


async def test_a_draft_from_start_to_approval(client, db, admin_headers):
    code, approved_id = await _procedure_with_approved_ruleset(db)
    base = "/api/v1/app-admin/rulesets"

    draft = await client.post(f"{base}/{approved_id}/drafts", json={"version": "1.1.0"}, headers=admin_headers)
    assert draft.status_code == 201, draft.text
    draft = draft.json()
    draft_id = draft["ruleset_id"]
    assert (draft["status"], [b["parameter_code"] for b in draft["bindings"]]) == ("draft", ["temp_c", "breathless"])
    assert "pain" in [p["parameter_code"] for p in draft["available_parameters"]]

    cutoffs = await client.patch(f"{base}/{draft_id}", json={"review_at": 5, "critical_at": 10}, headers=admin_headers)
    assert (cutoffs.json()["review_at"], cutoffs.json()["critical_at"]) == (5, 10)

    added = await client.put(f"{base}/{draft_id}/parameters/pain", json=PAIN, headers=admin_headers)
    assert added.status_code == 200, added.text
    pain = next(b for b in added.json()["bindings"] if b["parameter_code"] == "pain")
    assert pain["scoring_summary"] == "5–8 → 1, ≥8 → 3"
    assert pain["direction"] == "higher_is_worse"

    removed = await client.delete(f"{base}/{draft_id}/parameters/breathless", headers=admin_headers)
    assert [b["parameter_code"] for b in removed.json()["bindings"]] == ["temp_c", "pain"]

    approved = await client.post(f"{base}/{draft_id}/approve", json={"approved_by": "Dr. K. Mehta"}, headers=admin_headers)
    assert approved.status_code == 200, approved.text
    assert (approved.json()["status"], approved.json()["approved_by"]) == ("approved", "Dr. K. Mehta")

    versions = next(p for p in (await client.get(base, headers=admin_headers)).json() if p["procedure_code"] == code)["versions"]
    assert [(v["version"], v["status"]) for v in versions] == [("1.1.0", "approved"), ("1.0.0", "retired")]

    # Published now: nothing about it can change.
    assert (await client.patch(f"{base}/{draft_id}", json={"review_at": 6}, headers=admin_headers)).status_code == 409
    assert (await client.put(f"{base}/{draft_id}/parameters/pain", json=PAIN, headers=admin_headers)).status_code == 409


async def test_new_enrollments_use_the_newly_approved_version(client, db, admin_headers):
    code, approved_id = await _procedure_with_approved_ruleset(db)
    base = "/api/v1/app-admin/rulesets"
    draft_id = (await client.post(f"{base}/{approved_id}/drafts", json={"version": "2.0.0"}, headers=admin_headers)).json()["ruleset_id"]
    await client.post(f"{base}/{draft_id}/approve", json={"approved_by": "Dr Test"}, headers=admin_headers)

    hospital = await _create_hospital(client, admin_headers, procedure_codes=[code])
    email = f"enrol.{hospital['hospital_code'].lower()}@example.org"
    await _add_account(client, admin_headers, hospital["hospital_id"], email)
    clinician = await login_headers(client, email, "temporary-pass-123")
    options = (await client.get("/api/v1/enrollment/options", headers=clinician)).json()
    assert [(p["procedure_code"], p["ruleset_version"]) for p in options["procedures"]] == [(code, "2.0.0")]


WORSE_HIGH = {"direction": "higher_is_worse"}


@pytest.mark.parametrize("config, message", [
    ({**WORSE_HIGH, "bands": [[38, 37, 1]]}, "'from' must be below 'to'"),
    ({**WORSE_HIGH, "bands": [[0, 38, 0], [37, 99, 3]]}, "overlaps"),
    ({**WORSE_HIGH, "bands": [[0, 38, 0], [38, 99, 5]]}, "from 0 to 3"),
    ({**WORSE_HIGH, "band": [[0, 38, 0]]}, "unknown setting band"),
    ({**WORSE_HIGH, "bands_by_day": {"0-10": [[0, 5, 0]], "8-20": [[0, 4, 0]]}}, "overlap"),
    ({**WORSE_HIGH, "bands_by_day": {"0-60": [[0, 5, 0]]}}, "from 0 to 42"),
    ({"binary_score": 3}, "unknown setting binary_score"),
    ({"bands": [[0, 38, 0], [38, 99, 3]]}, "needs direction"),
    ({"direction": "up", "bands": [[0, 38, 0], [38, 99, 3]]}, "direction must be"),
    ({"direction": "higher_is_better", "bands": [[0, 38, 0], [38, 99, 3]]}, "direction is higher_is_worse"),
])
async def test_rules_the_engine_cannot_read_are_refused(client, db, admin_headers, config, message):
    _, approved_id = await _procedure_with_approved_ruleset(db)
    base = "/api/v1/app-admin/rulesets"
    draft_id = (await client.post(f"{base}/{approved_id}/drafts", json={"version": "9.9.9"}, headers=admin_headers)).json()["ruleset_id"]
    res = await client.put(f"{base}/{draft_id}/parameters/temp_c", json={**PAIN, "display_order": 1, "scoring_config": config},
                           headers=admin_headers)
    assert res.status_code == 422
    assert message in res.json()["detail"]


async def test_windows_must_fit_the_monitoring_period(client, db, admin_headers):
    _, approved_id = await _procedure_with_approved_ruleset(db)
    base = "/api/v1/app-admin/rulesets"
    draft_id = (await client.post(f"{base}/{approved_id}/drafts", json={"version": "1.2.0"}, headers=admin_headers)).json()["ruleset_id"]
    too_long = {**PAIN, "collect_to_day": 60, "score_to_day": 60}
    assert (await client.put(f"{base}/{draft_id}/parameters/pain", json=too_long, headers=admin_headers)).status_code == 422
    unasked = {**PAIN, "collect_from_day": 5, "score_from_day": 2}
    assert (await client.put(f"{base}/{draft_id}/parameters/pain", json=unasked, headers=admin_headers)).status_code == 422
    clash = {**PAIN, "display_order": 1}
    assert (await client.put(f"{base}/{draft_id}/parameters/pain", json=clash, headers=admin_headers)).status_code == 409


async def test_versions_are_unique_and_drafts_can_be_discarded(client, db, admin_headers):
    _, approved_id = await _procedure_with_approved_ruleset(db)
    base = "/api/v1/app-admin/rulesets"
    assert (await client.post(f"{base}/{approved_id}/drafts", json={"version": "1.0.0"}, headers=admin_headers)).status_code == 409

    draft_id = (await client.post(f"{base}/{approved_id}/drafts", json={"version": "1.3.0"}, headers=admin_headers)).json()["ruleset_id"]
    for measure in ("temp_c", "breathless"):
        await client.delete(f"{base}/{draft_id}/parameters/{measure}", headers=admin_headers)
    empty = await client.post(f"{base}/{draft_id}/approve", json={"approved_by": "Dr Test"}, headers=admin_headers)
    assert empty.status_code == 422

    assert (await client.delete(f"{base}/{draft_id}", headers=admin_headers)).status_code == 204
    assert (await client.get(f"{base}/{draft_id}", headers=admin_headers)).status_code == 404
    assert (await client.delete(f"{base}/{approved_id}", headers=admin_headers)).status_code == 409


async def test_a_published_ruleset_cannot_be_changed_even_in_sql(db):
    _, approved_id = await _procedure_with_approved_ruleset(db)
    with pytest.raises(DBAPIError, match="only a draft can be changed"):
        await db.execute(text("UPDATE meta.ruleset SET review_at = 3 WHERE ruleset_id = :id"), {"id": approved_id})
    await db.rollback()

    await db.execute(text("SET LOCAL ROLE eras_platform"))
    changed = (await db.execute(text("""
        UPDATE meta.procedure_parameter SET parameter_weight = 1 WHERE ruleset_id = :id
    """), {"id": approved_id})).rowcount
    assert changed == 0
    await db.rollback()
