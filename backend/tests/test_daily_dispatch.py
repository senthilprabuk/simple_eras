"""
Daily reminders: sent once and only inside the patient's window, as the approved
template, with a link minted at send time and never stored or logged.
"""

import logging
from datetime import time

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.services import whatsapp
from app.services.daily_dispatch import run_daily_checkin_dispatch
from app.services.magic_token import validate_magic_token
from app.services.patient_messages import MAX_ATTEMPTS, deliver_queued_messages
from app.services.whatsapp import SendResult
from tests.conftest import isolated_session_factory
from tests.support import create_hospital

REMINDER = "Good morning {patient_first_name}, day {post_op_day} at {hospital_name}: {checkin_link}"


@pytest.fixture(autouse=True)
def log_provider(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "log")


async def _due_patient(db, code, *, window=(time(0, 0), time(23, 59, 59)), wording=True, phone_number_id=None):
    hospital = await create_hospital(db, code)
    await db.execute(
        text("UPDATE txn.patient_episode SET checkin_window_start = :s, checkin_window_end = :e WHERE episode_id = :ep"),
        {"s": window[0], "e": window[1], "ep": hospital.episode_id},
    )
    if wording:
        await db.execute(text("""
            INSERT INTO meta.message_template (hospital_id, template_key, language_code, body)
            VALUES (:h, 'checkin_reminder', 'en', :body)
        """), {"h": hospital.hospital_id, "body": REMINDER})
    if phone_number_id:
        await db.execute(text("""
            INSERT INTO meta.hospital_whatsapp (hospital_id, display_name, display_phone_number,
                phone_number_id, waba_id, access_token, verify_token)
            VALUES (:h, 'Test Helpline', '+91 90000 22222', :pid, '500000000000001', 'EAAG-dispatch', 'verify-dispatch')
        """), {"h": hospital.hospital_id, "pid": phone_number_id})
    await db.commit()
    return hospital


async def _reminders(db, episode_id):
    return (await db.execute(text("""
        SELECT day_after_discharge, status, body, attempts, sent_at, meta_message_id, error_message
        FROM txn.patient_message
        WHERE episode_id = :e AND message_type = 'checkin_reminder'
    """), {"e": episode_id})).mappings().all()


def _fake_meta(monkeypatch, result):
    posted = []

    async def fake_post(credentials, payload, reference):
        posted.append((credentials, payload))
        return result

    monkeypatch.setattr(whatsapp, "_post", fake_post)
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "meta")
    return posted


async def test_no_reminder_outside_the_patients_window(db):
    not_yet = await _due_patient(db, "RM-EARLY", window=(time(23, 59, 58), time(23, 59, 59)))
    over = await _due_patient(db, "RM-LATE", window=(time(0, 0), time(0, 0, 1)))

    await run_daily_checkin_dispatch(isolated_session_factory)

    assert await _reminders(db, not_yet.episode_id) == []
    assert await _reminders(db, over.episode_id) == []


async def test_a_reminder_is_sent_once_and_its_link_stays_out_of_the_record(db, caplog):
    hospital = await _due_patient(db, "RM-SEND")

    with caplog.at_level(logging.INFO):
        result = await run_daily_checkin_dispatch(isolated_session_factory)
    assert result["queued"] >= 1

    [reminder] = await _reminders(db, hospital.episode_id)
    assert reminder["status"] == "sent"
    assert reminder["attempts"] == 1
    assert reminder["sent_at"] is not None
    assert reminder["body"].endswith("Hospital RM-SEND: [check-in link]")
    assert "token=" not in caplog.text
    assert "9800000001" not in caplog.text
    assert "Patient RM-SEND" not in caplog.text

    await run_daily_checkin_dispatch(isolated_session_factory)
    assert len(await _reminders(db, hospital.episode_id)) == 1


async def test_with_meta_the_reminder_is_the_approved_template_with_a_working_link(db, monkeypatch):
    hospital = await _due_patient(db, "RM-META", phone_number_id="400000000000001")
    posted = _fake_meta(monkeypatch, SendResult("sent", message_id="wamid.rm-meta"))

    await run_daily_checkin_dispatch(isolated_session_factory)

    [(credentials, payload)] = [p for p in posted if p[0].phone_number_id == "400000000000001"]
    assert credentials.access_token == "EAAG-dispatch"
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "checkin_reminder"
    assert payload["template"]["language"] == {"code": "en"}
    first_name, day, hospital_name, link = [
        p["text"] for p in payload["template"]["components"][0]["parameters"]
    ]
    assert (first_name, hospital_name) == ("Patient", "Hospital RM-META")
    assert link.startswith(f"{settings.FRONTEND_BASE_URL}/checkin?token=")
    assert validate_magic_token(link.split("token=")[1]) == {"episode_id": hospital.episode_id, "day": int(day)}

    [reminder] = await _reminders(db, hospital.episode_id)
    assert reminder["meta_message_id"] == "wamid.rm-meta"


async def test_with_meta_and_no_account_the_reminder_fails_rather_than_pretending(db, monkeypatch):
    hospital = await _due_patient(db, "RM-NOACC")
    monkeypatch.setattr(settings, "META_PHONE_NUMBER_ID", None)
    monkeypatch.setattr(settings, "META_ACCESS_TOKEN", None)
    _fake_meta(monkeypatch, SendResult("sent", message_id="wamid.must-not-be-used"))

    await run_daily_checkin_dispatch(isolated_session_factory)

    [reminder] = await _reminders(db, hospital.episode_id)
    assert reminder["status"] == "failed"
    assert "No WhatsApp account" in reminder["error_message"]


async def test_a_passing_failure_is_retried_then_given_up(db, monkeypatch):
    hospital = await _due_patient(db, "RM-RETRY", phone_number_id="400000000000002")
    _fake_meta(monkeypatch, SendResult("failed", error="Could not reach Meta (ConnectTimeout)", retryable=True))

    await run_daily_checkin_dispatch(isolated_session_factory)
    for attempt in range(1, MAX_ATTEMPTS):
        [reminder] = await _reminders(db, hospital.episode_id)
        assert (reminder["status"], reminder["attempts"]) == ("queued", attempt)
        await deliver_queued_messages(isolated_session_factory)

    [reminder] = await _reminders(db, hospital.episode_id)
    assert (reminder["status"], reminder["attempts"]) == ("failed", MAX_ATTEMPTS)
    assert "ConnectTimeout" in reminder["error_message"]


async def test_a_rejected_send_is_not_retried(db, monkeypatch):
    hospital = await _due_patient(db, "RM-REJECT", phone_number_id="400000000000003")
    _fake_meta(monkeypatch, SendResult("failed", error="Template name does not exist", retryable=False))

    await run_daily_checkin_dispatch(isolated_session_factory)

    [reminder] = await _reminders(db, hospital.episode_id)
    assert (reminder["status"], reminder["attempts"]) == ("failed", 1)


async def test_with_sending_disabled_reminders_wait_and_the_log_says_so(db, monkeypatch, caplog):
    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "disabled")
    hospital = await _due_patient(db, "RM-OFF")

    with caplog.at_level(logging.WARNING, logger="eras.patient_messages"):
        await run_daily_checkin_dispatch(isolated_session_factory)
    assert "no patient has been messaged" in caplog.text
    [reminder] = await _reminders(db, hospital.episode_id)
    assert (reminder["status"], reminder["attempts"]) == ("queued", 0)

    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "log")
    await deliver_queued_messages(isolated_session_factory)
    [reminder] = await _reminders(db, hospital.episode_id)
    assert reminder["status"] == "sent"


async def test_a_reminder_left_from_an_earlier_day_is_not_sent(db):
    hospital = await _due_patient(db, "RM-STALE", window=(time(23, 59, 58), time(23, 59, 59)))
    await db.execute(text("""
        INSERT INTO txn.patient_message (episode_id, patient_id, hospital_id, message_type,
            day_after_discharge, phone_e164, body)
        SELECT e.episode_id, e.patient_id, e.hospital_id, 'checkin_reminder', 9, '+919800000001', 'left over'
        FROM txn.patient_episode e WHERE e.episode_id = :e
    """), {"e": hospital.episode_id})
    await db.commit()

    result = await deliver_queued_messages(isolated_session_factory)

    assert result["expired"] >= 1
    [reminder] = await _reminders(db, hospital.episode_id)
    assert reminder["status"] == "failed"
    assert reminder["error_message"] == "Not sent before the day it was for had ended"


async def test_without_wording_the_gap_is_recorded_once(db):
    hospital = await _due_patient(db, "RM-NOWORD", wording=False)

    await run_daily_checkin_dispatch(isolated_session_factory)
    await run_daily_checkin_dispatch(isolated_session_factory)

    [reminder] = await _reminders(db, hospital.episode_id)
    assert reminder["status"] == "failed"
    assert "No active checkin_reminder wording" in reminder["error_message"]
