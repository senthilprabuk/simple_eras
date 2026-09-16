#!/usr/bin/env python3
"""
Step 7 Verification Test
Validates:
  1. Automated escalation sweep (run_escalation_sweep) detects SLA-breached alerts
  2. Sets alert.escalated_at to current timestamp
  3. Dispatches notifications for active admins across push and sms channels
  4. Strictly idempotent: subsequent sweep ticks do not re-escalate or duplicate notifications
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text

# Ensure backend directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db.session import async_session_factory
from app.services.escalation import run_escalation_sweep

async def test_escalation():
    print("=== STEP 7: IN-PROCESS ESCALATION SWEEP VERIFICATION ===\n")

    test_admin_id = uuid4()
    test_patient_id = uuid4()
    test_episode_id = uuid4()
    test_eval_id = uuid4()
    test_alert_id = uuid4()

    now = datetime.now(timezone.utc)
    # Simulate an alert raised 25 minutes ago (SLA window is 15 minutes / 900 seconds)
    twenty_five_mins_ago = now - timedelta(minutes=25)

    async with async_session_factory() as session:
        # 1. Fetch available hospital and procedure/ruleset IDs
        res = await session.execute(text("SELECT hospital_id FROM meta.hospital LIMIT 1;"))
        h_id = res.scalar()
        assert h_id is not None, "Hospital must exist in meta.hospital"

        res = await session.execute(text("SELECT procedure_id FROM meta.surgical_procedure LIMIT 1;"))
        proc_id = res.scalar()

        res = await session.execute(text("SELECT ruleset_id FROM meta.ruleset WHERE procedure_id = :pid LIMIT 1;"), {"pid": proc_id})
        ruleset_id = res.scalar()

        print(f"[*] Setup: using Hospital ID {h_id}, Procedure ID {proc_id}, Ruleset ID {ruleset_id}")

        # 2. Insert test admin
        test_email = f"esc.nurse.{uuid4().hex[:6]}@stmarys.org"
        await session.execute(text("""
            INSERT INTO meta.admin_user (admin_user_id, hospital_id, email, hashed_password, full_name, role, is_active)
            VALUES (:uid, :hid, :email, 'hash', 'On-Call Nurse Sarah', 'admin', true);
        """), {"uid": test_admin_id, "hid": h_id, "email": test_email})

        # 3. Insert test patient & episode
        await session.execute(text("""
            INSERT INTO txn.patient (patient_id, hospital_id, mrn, patient_name, phone_e164, language_code)
            VALUES (:pid, :hid, 'MRN-ESC-1', 'Escalation Test Patient', '+919876543210', 'en');
        """), {"pid": test_patient_id, "hid": h_id})

        await session.execute(text("""
            INSERT INTO txn.patient_episode (
                episode_id, patient_id, hospital_id, procedure_id, ruleset_id,
                surgery_date, discharge_date, monitoring_ends_on, consent_version, consent_at, status
            ) VALUES (
                :eid, :pid, :hid, :proc_id, :rid,
                current_date - 5, current_date - 3, current_date + 80, 'v1.0', now(), 'active'
            );
        """), {"eid": test_episode_id, "pid": test_patient_id, "hid": h_id, "proc_id": proc_id, "rid": ruleset_id})

        # 4. Insert evaluation
        await session.execute(text("""
            INSERT INTO txn.check_in_evaluation (
                evaluation_id, episode_id, ruleset_id, day_after_discharge,
                tier, total_score, is_override, reasons, reason_key, evaluated_at
            ) VALUES (
                :evid, :eid, :rid, 3, 'critical', 14, false,
                '[{"name": "fever_returned", "score": 3, "detail": "Fever returned: 38.8C"}]'::jsonb,
                'hash_fever_key', :raised_at
            );
        """), {"evid": test_eval_id, "eid": test_episode_id, "rid": ruleset_id, "raised_at": twenty_five_mins_ago})

        # 5. Insert open, unacknowledged critical alert (exceeding ack window)
        await session.execute(text("""
            INSERT INTO txn.alert (
                alert_id, episode_id, evaluation_id, tier, reason_key, status, raised_at, notified_at, escalated_at
            ) VALUES (
                :aid, :eid, :evid, 'critical', 'hash_fever_key', 'open', :raised_at, :notified_at, NULL
            );
        """), {"aid": test_alert_id, "eid": test_episode_id, "evid": test_eval_id, "raised_at": twenty_five_mins_ago, "notified_at": twenty_five_mins_ago})

        await session.commit()
        print(f"  [+] Seeded unacknowledged alert {test_alert_id} raised 25m ago (breaching 15m window).")

    try:
        # 6. Run sweep #1 (Should detect and escalate)
        print("\n[*] Running Escalation Sweep 1:")
        res1 = await run_escalation_sweep(async_session_factory)
        print(f"  [+] Sweep 1 Result: {res1}")
        assert res1["overdue_alerts_found"] >= 1, "Sweep must find at least the test alert!"
        assert res1["notifications_created"] >= 2, "Must create at least push and sms notifications!"

        # Verify in DB
        async with async_session_factory() as session:
            alert_res = await session.execute(text("SELECT status, escalated_at FROM txn.alert WHERE alert_id = :aid;"), {"aid": test_alert_id})
            status, esc_at = alert_res.fetchone()
            assert esc_at is not None, "Alert must have escalated_at timestamp set!"
            print(f"  [+] DB Alert escalated_at confirmed: {esc_at}")

            notif_res = await session.execute(text("SELECT channel, recipient, status FROM txn.alert_notification WHERE alert_id = :aid;"), {"aid": test_alert_id})
            notifs = notif_res.fetchall()
            print(f"  [+] Dispatched notifications ({len(notifs)}): {[(n[0], n[1]) for n in notifs]}")
            channels = {n[0] for n in notifs}
            assert "push" in channels and "sms" in channels, "Both push and sms notifications must be created!"

        # 7. Run sweep #2 (Should be strictly idempotent - 0 newly overdue alerts)
        print("\n[*] Running Escalation Sweep 2 (Testing Idempotency):")
        res2 = await run_escalation_sweep(async_session_factory)
        print(f"  [+] Sweep 2 Result: {res2}")
        assert res2["overdue_alerts_found"] == 0, "Sweep 2 must find 0 alerts (already escalated)!"
        print("  [+] Idempotency confirmed: already-escalated alert was skipped.")

    finally:
        # 8. Cleanup test data
        print("\n[*] Cleaning up test records...")
        async with async_session_factory() as session:
            await session.execute(text("DELETE FROM txn.alert_notification WHERE alert_id = :aid;"), {"aid": test_alert_id})
            await session.execute(text("DELETE FROM txn.alert WHERE alert_id = :aid;"), {"aid": test_alert_id})
            await session.execute(text("DELETE FROM txn.check_in_evaluation WHERE evaluation_id = :evid;"), {"evid": test_eval_id})
            await session.execute(text("DELETE FROM txn.patient_episode WHERE episode_id = :eid;"), {"eid": test_episode_id})
            await session.execute(text("DELETE FROM txn.patient WHERE patient_id = :pid;"), {"pid": test_patient_id})
            await session.execute(text("DELETE FROM meta.admin_user WHERE admin_user_id = :uid;"), {"uid": test_admin_id})
            await session.commit()
        print("  [+] Test records cleaned up successfully.")

    print("\n[SUCCESS] Step 7 In-Process Escalation Sweep verified with 0 errors!")

if __name__ == "__main__":
    asyncio.run(test_escalation())
