import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import text
from app.db.session import async_session_factory
from app.services.escalation import run_escalation_sweep

@pytest.mark.asyncio
async def test_escalation_sweep_execution():
    """Verify that run_escalation_sweep executes cleanly against the live database."""
    # Run once
    await run_escalation_sweep(async_session_factory)
    # Run a second time to ensure idempotency and no unhandled concurrency errors
    await run_escalation_sweep(async_session_factory)

@pytest.mark.asyncio
async def test_escalation_sweep_escalates_breached_alert():
    """
    Simulate an alert that exceeded the hospital ack SLA window (e.g. 20 minutes ago),
    run the sweep, and verify:
    1. alert.escalated_at is set to a non-null timestamp
    2. notifications are inserted into txn.alert_notification
    3. running sweep again does NOT re-escalate or duplicate notifications
    """
    now = datetime.now(timezone.utc)
    twenty_mins_ago = now - timedelta(minutes=20)

    async with async_session_factory() as session:
        # Get an existing patient and episode from Hospital 1
        res = await session.execute(text("""
            SELECT p.patient_id, e.episode_id, e.ruleset_id
            FROM txn.patient p
            JOIN txn.patient_episode e ON e.patient_id = p.patient_id
            WHERE p.hospital_id = 1
            LIMIT 1;
        """))
        row = res.mappings().first()
        assert row is not None

        patient_id = row["patient_id"]
        episode_id = row["episode_id"]
        ruleset_id = row["ruleset_id"]

        # Insert check_in_evaluation
        test_eval_id = uuid4()
        test_alert_id = uuid4()

        await session.execute(text("""
            INSERT INTO txn.check_in_evaluation (
                evaluation_id, episode_id, ruleset_id, day_after_discharge,
                tier, total_score, is_override, reasons, reason_key, evaluated_at
            ) VALUES (
                :eid, :epid, :rsid, 4, 'critical',
                15, true, CAST(:reasons AS jsonb), 'reason_test_sla', :t_ago
            );
        """), {
            "eid": test_eval_id,
            "epid": episode_id,
            "rsid": ruleset_id,
            "reasons": '[{"name": "test_sla", "score": 3, "weight": 3, "detail": "Test SLA breach trigger"}]',
            "t_ago": twenty_mins_ago
        })

        # Insert unacknowledged critical alert raised 20 mins ago
        await session.execute(text("""
            INSERT INTO txn.alert (
                alert_id, episode_id, evaluation_id, tier,
                reason_key, status, raised_at, notified_at
            ) VALUES (
                :aid, :epid, :eid, 'critical',
                'reason_test_sla', 'open', :t_ago, :t_ago
            );
        """), {
            "aid": test_alert_id,
            "epid": episode_id,
            "eid": test_eval_id,
            "t_ago": twenty_mins_ago
        })
        await session.commit()

    # Trigger escalation sweep
    await run_escalation_sweep(async_session_factory)

    # Verify alert was escalated
    async with async_session_factory() as session:
        res = await session.execute(text("""
            SELECT escalated_at, status FROM txn.alert WHERE alert_id = :aid;
        """), {"aid": test_alert_id})
        alert_row = res.mappings().first()
        assert alert_row is not None
        assert alert_row["escalated_at"] is not None

        # Check notifications were created
        res = await session.execute(text("""
            SELECT count(*) FROM txn.alert_notification WHERE alert_id = :aid;
        """), {"aid": test_alert_id})
        notif_count_1 = res.scalar()
        assert notif_count_1 > 0

    # Run sweep again (idempotency check)
    await run_escalation_sweep(async_session_factory)

    # Check no duplicate notifications were created
    async with async_session_factory() as session:
        res = await session.execute(text("""
            SELECT count(*) FROM txn.alert_notification WHERE alert_id = :aid;
        """), {"aid": test_alert_id})
        notif_count_2 = res.scalar()
        assert notif_count_1 == notif_count_2

        # Cleanup test rows
        await session.execute(text("DELETE FROM txn.alert_notification WHERE alert_id = :aid;"), {"aid": test_alert_id})
        await session.execute(text("DELETE FROM txn.alert WHERE alert_id = :aid;"), {"aid": test_alert_id})
        await session.execute(text("DELETE FROM txn.check_in_evaluation WHERE evaluation_id = :eid;"), {"eid": test_eval_id})
        await session.commit()
