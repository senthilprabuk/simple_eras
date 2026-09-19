from tests.conftest import login_headers
from tests.support import create_hospital


def _entry(catalogue, key, lang):
    return next(t for t in catalogue["templates"] if t["template_key"] == key and t["language_code"] == lang)


async def test_catalogue_lists_every_template_in_every_language(client, nurse_headers):
    catalogue = (await client.get("/api/v1/templates", headers=nurse_headers)).json()
    assert len(catalogue["templates"]) == 12
    assert set(catalogue["placeholders"]) == {"patient_first_name", "hospital_name", "post_op_day", "checkin_link"}

    reminder = _entry(catalogue, "checkin_reminder", "en")
    assert "{checkin_link}" in reminder["body"]
    assert reminder["is_active"] is True
    # Untranslated languages are reported as gaps, not hidden.
    assert _entry(catalogue, "checkin_reminder", "ta")["body"] is None
    assert _entry(catalogue, "urgent_guidance", "hi")["body"] is None


async def test_only_a_superadmin_can_edit_wording(client, nurse_headers):
    res = await client.put("/api/v1/templates/checkin_reminder/ta", json={"body": "Hello"}, headers=nurse_headers)
    assert res.status_code == 403


async def test_superadmin_writes_a_translation(client, db, nurse_headers):
    h = await create_hospital(db, "TPL-EDIT", role="superadmin")
    headers = await login_headers(client, h.email, h.password)
    body = "வணக்கம் {patient_first_name}, இன்றைய பதிவை நிரப்பவும்: {checkin_link}"

    res = await client.put("/api/v1/templates/checkin_reminder/ta", json={"body": body}, headers=headers)
    assert res.status_code == 200
    saved = _entry((await client.get("/api/v1/templates", headers=headers)).json(), "checkin_reminder", "ta")
    assert saved["body"] == body
    assert saved["updated_by_name"] == "Admin TPL-EDIT"

    res = await client.put("/api/v1/templates/checkin_reminder/ta", json={"body": body, "is_active": False}, headers=headers)
    assert res.json()["is_active"] is False

    # Another hospital's wording is untouched.
    fixture = (await client.get("/api/v1/templates", headers=nurse_headers)).json()
    assert _entry(fixture, "checkin_reminder", "ta")["body"] is None


async def test_bad_wording_is_rejected_before_it_can_reach_a_patient(client, db):
    h = await create_hospital(db, "TPL-BAD", role="superadmin")
    headers = await login_headers(client, h.email, h.password)
    for body in ("Hi {patient_frist_name}", "Hi {patient_first_name", "x" * 1025, "   "):
        res = await client.put("/api/v1/templates/checkin_reminder/en", json={"body": body}, headers=headers)
        assert res.status_code == 422, body
    for path in ("/api/v1/templates/newsletter/en", "/api/v1/templates/checkin_reminder/fr"):
        assert (await client.put(path, json={"body": "Hello"}, headers=headers)).status_code == 422
