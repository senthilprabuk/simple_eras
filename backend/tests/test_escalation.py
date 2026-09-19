import asyncio
from datetime import timedelta

from sqlalchemy import text

from app.services.escalation import run_escalation_sweep
from tests.conftest import isolated_session_factory
from tests.support import create_alert, create_hospital, episode_for_mrn


async def _escalated_at(db, alert_id):
    return (await db.execute(text("SELECT escalated_at FROM txn.alert WHERE alert_id = :a"), {"a": alert_id})).scalar_one()


async def _notifications(db, alert_id):
    return (await db.execute(
        text("SELECT recipient, channel FROM txn.alert_notification WHERE alert_id = :a ORDER BY recipient"),
        {"a": alert_id},
    )).all()


async def _active_admin_emails(db, hospital_id):
    return [r[0] for r in (await db.execute(
        text("SELECT email FROM meta.admin_user WHERE hospital_id = :h AND is_active ORDER BY email"),
        {"h": hospital_id},
    )).all()]


async def test_breached_alert_is_escalated_once_with_one_email_per_active_admin(db):
    alert_id = await create_alert(db, await episode_for_mrn(db, "FX-01"), tier="critical",
                                  raised_ago=timedelta(minutes=20))

    await run_escalation_sweep(isolated_session_factory)
    first_escalation = await _escalated_at(db, alert_id)
    assert first_escalation is not None

    sent = await _notifications(db, alert_id)
    assert [r.recipient for r in sent] == await _active_admin_emails(db, 1)
    assert {r.channel for r in sent} == {"email"}

    await run_escalation_sweep(isolated_session_factory)
    assert await _notifications(db, alert_id) == sent
    assert await _escalated_at(db, alert_id) == first_escalation


async def test_concurrent_sweeps_do_not_duplicate_notifications(db):
    alert_id = await create_alert(db, await episode_for_mrn(db, "FX-01"), tier="emergency",
                                  raised_ago=timedelta(minutes=30))

    await asyncio.gather(*(run_escalation_sweep(isolated_session_factory) for _ in range(3)))

    assert len(await _notifications(db, alert_id)) == len(await _active_admin_emails(db, 1))


async def test_only_open_critical_and_emergency_alerts_past_their_window_escalate(db):
    ep = await episode_for_mrn(db, "FX-01")
    acknowledged = await create_alert(db, ep, tier="critical", status="acknowledged",
                                      raised_ago=timedelta(minutes=30), acknowledged_after=timedelta(minutes=1))
    review_tier = await create_alert(db, ep, tier="review", raised_ago=timedelta(minutes=30))
    still_in_window = await create_alert(db, ep, tier="critical", raised_ago=timedelta(minutes=5))

    await run_escalation_sweep(isolated_session_factory)

    for alert_id in (acknowledged, review_tier, still_in_window):
        assert await _escalated_at(db, alert_id) is None


async def test_escalation_respects_each_hospitals_own_window(db):
    h = await create_hospital(db, "ESC-HOUR", ack_window_secs=3600)
    alert_id = await create_alert(db, h.episode_id, tier="critical", raised_ago=timedelta(minutes=20))

    await run_escalation_sweep(isolated_session_factory)

    assert await _escalated_at(db, alert_id) is None
