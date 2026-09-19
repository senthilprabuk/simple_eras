import logging

from sqlalchemy import text

from app.core.config import settings
from app.services.notifications import dispatch_queued_notifications
from tests.conftest import isolated_session_factory
from tests.support import create_alert, episode_for_mrn


async def _queue_notification(db):
    alert_id = await create_alert(db, await episode_for_mrn(db, "FX-01"), tier="review")
    notification_id = (await db.execute(text("""
        INSERT INTO txn.alert_notification (alert_id, recipient, channel)
        VALUES (:a, 'nurse.sarah@stmarys.org', 'email')
        RETURNING notification_id
    """), {"a": alert_id})).scalar_one()
    await db.commit()
    return alert_id, notification_id


async def _notification(db, notification_id):
    return (await db.execute(
        text("SELECT status, sent_at, attempts, provider_ref FROM txn.alert_notification WHERE notification_id = :n"),
        {"n": notification_id},
    )).mappings().one()


async def test_disabled_provider_leaves_notifications_queued_and_says_so(db, monkeypatch, caplog):
    monkeypatch.setattr(settings, "NOTIFICATION_PROVIDER", "disabled")
    _, notification_id = await _queue_notification(db)

    with caplog.at_level(logging.WARNING, logger="eras.notifications"):
        result = await dispatch_queued_notifications(isolated_session_factory)

    assert result["sent"] == 0
    assert result["queued"] >= 1
    assert "no clinician has been notified" in caplog.text
    assert (await _notification(db, notification_id))["status"] == "queued"


async def test_log_provider_delivers_and_keeps_patient_details_out_of_the_log(db, monkeypatch, caplog):
    monkeypatch.setattr(settings, "NOTIFICATION_PROVIDER", "log")
    alert_id, notification_id = await _queue_notification(db)

    with caplog.at_level(logging.INFO, logger="eras.notifications"):
        await dispatch_queued_notifications(isolated_session_factory, batch_size=1000)

    row = await _notification(db, notification_id)
    assert row["status"] == "sent"
    assert row["provider_ref"] == "log"
    assert row["sent_at"] is not None
    assert row["attempts"] == 1
    assert str(alert_id) in caplog.text
    assert "Lakshmi Narayanan [Smooth Recovery]" not in caplog.text
