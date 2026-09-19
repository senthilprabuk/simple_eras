#!/usr/bin/env python3
"""
ERAS Clinical Remote Monitoring - Demo Seed Script
Populates:
  1. Hospital branding ("St. Mary's Orthopedic Center", Coimbatore)
  2. 3 Hospital Admin Accounts (Nurse, Surgeon, Superadmin)
  3. Clinical evaluations & alerts across all 12 existing fixture patients:
     - 1 Emergency Alert (FX-03 Sudden Clot)
     - 2 Critical Alerts (FX-02 Slow Burn, FX-07 Combination Creep)
     - 2 Review Alerts (FX-08 Early Low Fever, FX-12 Mobility Drop)
     - 1 Missed Check-in Alert (FX-06 Drop Out)
     - 6 Quiet Cohort Normal Patients (FX-01, FX-04, FX-05, FX-09, FX-11, FX-13)
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text

# Ensure backend directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import async_session_factory
from app.core.security import get_password_hash

async def seed_demo(session_factory=None):
    print("================================================================")
    print("        ERAS DEMO CLINICAL SEED SCRIPT (PAGE 1)                ")
    print("================================================================\n")

    now = datetime.now(timezone.utc)

    async with (session_factory or async_session_factory)() as session:
        # 1. Update Hospital 1 name
        print("[*] 1. Updating hospital details for ID 1:")
        await session.execute(text("""
            UPDATE meta.hospital
            SET hospital_name = :h_name,
                ack_window_secs = 900
            WHERE hospital_id = 1;
        """), {"h_name": "St. Mary's Orthopedic Center"})
        print("  [+] Hospital 1 updated: St. Mary's Orthopedic Center (15m SLA Window).")

        # 2. Seed Admin Users
        print("\n[*] 2. Seeding administrator accounts in meta.admin_user:")
        raw_password = "password123"
        hashed_password = get_password_hash(raw_password)

        admin_sarah_id = uuid4()
        admin_mehta_id = uuid4()
        admin_super_id = uuid4()

        admins_to_seed = [
            (admin_sarah_id, 1, "nurse.sarah@stmarys.org", hashed_password, "Nurse Sarah Jenkins", "admin"),
            (admin_mehta_id, 1, "dr.mehta@stmarys.org", hashed_password, "Dr. K. Mehta", "admin"),
            (admin_super_id, 1, "admin@stmarys.org", hashed_password, "System Superadmin", "superadmin"),
        ]

        # Clean existing test admins if any
        await session.execute(text("DELETE FROM meta.admin_user WHERE hospital_id = 1;"))

        for aid, hid, email, pwd, name, role in admins_to_seed:
            await session.execute(text("""
                INSERT INTO meta.admin_user (
                    admin_user_id, hospital_id, email, hashed_password, full_name, role, is_active
                ) VALUES (
                    :aid, :hid, :email, :pwd, :name, :role, true
                );
            """), {"aid": aid, "hid": hid, "email": email, "pwd": pwd, "name": name, "role": role})
            print(f"  [+] Created {role.upper()}: {name:<22} | {email}")

        # 3. Retrieve existing fixture patients & episodes
        print("\n[*] 3. Fetching existing fixture patients and episodes:")
        pt_res = await session.execute(text("""
            SELECT p.patient_id, p.mrn, p.patient_name, e.episode_id, e.ruleset_id
            FROM txn.patient p
            JOIN txn.patient_episode e ON e.patient_id = p.patient_id
            WHERE p.hospital_id = 1
            ORDER BY p.mrn;
        """))
        patient_rows = pt_res.mappings().all()
        patient_map = {r["mrn"]: r for r in patient_rows}
        print(f"  [+] Found {len(patient_map)} fixture patients mapped to active episodes.")

        # Clean prior alerts, notifications, and evaluations to ensure fresh repeatable state
        print("\n[*] 4. Resetting evaluations and alerts for fresh demonstration:")
        await session.execute(text("DELETE FROM txn.alert_notification;"))
        await session.execute(text("DELETE FROM txn.alert;"))
        await session.execute(text("DELETE FROM txn.check_in_evaluation;"))
        print("  [+] Prior evaluations and alerts cleared.")

        # 5. Populate Evaluations and Prioritized Alerts
        print("\n[*] 5. Seeding clinical alerts across all severity tiers:")

        # --- ROW 1: EMERGENCY (FX-03 Sudden Clot / H. Thorne equivalent) ---
        p = patient_map.get("FX-03")
        if p:
            eval_id = uuid4()
            alert_id = uuid4()
            raised_at = now - timedelta(minutes=3)
            reasons = [
                {"name": "calf_pain", "score": 3, "weight": 3, "detail": "Calf swelling & acute sharp pain"},
                {"name": "pe_risk", "score": 3, "weight": 0, "detail": "Suspected DVT trigger"}
            ]
            await session.execute(text("""
                INSERT INTO txn.check_in_evaluation (
                    evaluation_id, episode_id, ruleset_id, day_after_discharge,
                    tier, total_score, is_override, reasons, reason_key, evaluated_at
                ) VALUES (
                    :evid, :eid, :rid, 4, 'emergency', 18, true, CAST(:reasons AS jsonb), 'reason_dvt_clot', :raised_at
                );
            """), {"evid": eval_id, "eid": p["episode_id"], "rid": p["ruleset_id"], "reasons": json.dumps(reasons), "raised_at": raised_at})

            await session.execute(text("""
                INSERT INTO txn.alert (
                    alert_id, episode_id, evaluation_id, tier, reason_key, status, raised_at, notified_at
                ) VALUES (
                    :aid, :eid, :evid, 'emergency', 'reason_dvt_clot', 'open', :raised_at, :raised_at
                );
            """), {"aid": alert_id, "eid": p["episode_id"], "evid": eval_id, "raised_at": raised_at})
            print(f"  [+] [EMERGENCY]  {p['mrn']} ({p['patient_name']}): Calf swelling & Suspected DVT (3m ago, open)")

        # --- ROW 2: CRITICAL (FX-02 Slow Burn / M. Vance equivalent - Near SLA Breach) ---
        p = patient_map.get("FX-02")
        if p:
            eval_id = uuid4()
            alert_id = uuid4()
            raised_at = now - timedelta(minutes=11)
            reasons = [
                {"name": "drainage", "score": 2, "weight": 2, "detail": "Wound incision exudate reported"},
                {"name": "fever_returned", "score": 3, "weight": 3, "detail": "Fever returned: 38.6°C"}
            ]
            await session.execute(text("""
                INSERT INTO txn.check_in_evaluation (
                    evaluation_id, episode_id, ruleset_id, day_after_discharge,
                    tier, total_score, is_override, reasons, reason_key, evaluated_at
                ) VALUES (
                    :evid, :eid, :rid, 2, 'critical', 15, true, CAST(:reasons AS jsonb), 'reason_fever_drainage', :raised_at
                );
            """), {"evid": eval_id, "eid": p["episode_id"], "rid": p["ruleset_id"], "reasons": json.dumps(reasons), "raised_at": raised_at})

            await session.execute(text("""
                INSERT INTO txn.alert (
                    alert_id, episode_id, evaluation_id, tier, reason_key, status, raised_at, notified_at
                ) VALUES (
                    :aid, :eid, :evid, 'critical', 'reason_fever_drainage', 'open', :raised_at, :raised_at
                );
            """), {"aid": alert_id, "eid": p["episode_id"], "evid": eval_id, "raised_at": raised_at})
            print(f"  [+] [CRITICAL]   {p['mrn']} ({p['patient_name']}): Wound drainage & Fever returned (11m ago, 4m SLA remains)")

        # --- ROW 3: CRITICAL (FX-07 Combination Creep / R. Nair equivalent - Newly Raised) ---
        p = patient_map.get("FX-07")
        if p:
            eval_id = uuid4()
            alert_id = uuid4()
            raised_at = now - timedelta(minutes=2)
            reasons = [
                {"name": "knee_extension", "score": 2, "weight": 2, "detail": "Persistent extension block >15°"},
                {"name": "night_pain", "score": 2, "weight": 2, "detail": "Severe night pain flare"}
            ]
            await session.execute(text("""
                INSERT INTO txn.check_in_evaluation (
                    evaluation_id, episode_id, ruleset_id, day_after_discharge,
                    tier, total_score, is_override, reasons, reason_key, evaluated_at
                ) VALUES (
                    :evid, :eid, :rid, 9, 'critical', 14, false, CAST(:reasons AS jsonb), 'reason_extension_pain', :raised_at
                );
            """), {"evid": eval_id, "eid": p["episode_id"], "rid": p["ruleset_id"], "reasons": json.dumps(reasons), "raised_at": raised_at})

            await session.execute(text("""
                INSERT INTO txn.alert (
                    alert_id, episode_id, evaluation_id, tier, reason_key, status, raised_at, notified_at
                ) VALUES (
                    :aid, :eid, :evid, 'critical', 'reason_extension_pain', 'open', :raised_at, :raised_at
                );
            """), {"aid": alert_id, "eid": p["episode_id"], "evid": eval_id, "raised_at": raised_at})
            print(f"  [+] [CRITICAL]   {p['mrn']} ({p['patient_name']}): Extension block & Night pain flare (2m ago, open)")

        # --- ROW 4: REVIEW (FX-08 Early Low Fever / D. Gallagher equivalent - Acknowledged) ---
        p = patient_map.get("FX-08")
        if p:
            eval_id = uuid4()
            alert_id = uuid4()
            raised_at = now - timedelta(minutes=42)
            ack_at = now - timedelta(minutes=25)
            reasons = [
                {"name": "erythema", "score": 2, "weight": 2, "detail": "Mild peripatellar erythema spreading 1cm"}
            ]
            await session.execute(text("""
                INSERT INTO txn.check_in_evaluation (
                    evaluation_id, episode_id, ruleset_id, day_after_discharge,
                    tier, total_score, is_override, reasons, reason_key, evaluated_at
                ) VALUES (
                    :evid, :eid, :rid, 7, 'review', 6, false, CAST(:reasons AS jsonb), 'reason_erythema', :raised_at
                );
            """), {"evid": eval_id, "eid": p["episode_id"], "rid": p["ruleset_id"], "reasons": json.dumps(reasons), "raised_at": raised_at})

            await session.execute(text("""
                INSERT INTO txn.alert (
                    alert_id, episode_id, evaluation_id, tier, reason_key, status, raised_at, notified_at, acknowledged_at, acknowledged_by
                ) VALUES (
                    :aid, :eid, :evid, 'review', 'reason_erythema', 'acknowledged', :raised_at, :raised_at, :ack_at, :ack_by
                );
            """), {"aid": alert_id, "eid": p["episode_id"], "evid": eval_id, "raised_at": raised_at, "ack_at": ack_at, "ack_by": admin_mehta_id})
            print(f"  [+] [REVIEW]     {p['mrn']} ({p['patient_name']}): Erythema spreading 1cm (Ack by Dr. Mehta)")

        # --- ROW 5: REVIEW (FX-12 Mobility Drop / A. Chen equivalent - Acknowledged) ---
        p = patient_map.get("FX-12")
        if p:
            eval_id = uuid4()
            alert_id = uuid4()
            raised_at = now - timedelta(minutes=75)
            ack_at = now - timedelta(minutes=50)
            reasons = [
                {"name": "fall_report", "score": 2, "weight": 2, "detail": "Reported fall without direct knee impact"}
            ]
            await session.execute(text("""
                INSERT INTO txn.check_in_evaluation (
                    evaluation_id, episode_id, ruleset_id, day_after_discharge,
                    tier, total_score, is_override, reasons, reason_key, evaluated_at
                ) VALUES (
                    :evid, :eid, :rid, 21, 'review', 6, false, CAST(:reasons AS jsonb), 'reason_fall', :raised_at
                );
            """), {"evid": eval_id, "eid": p["episode_id"], "rid": p["ruleset_id"], "reasons": json.dumps(reasons), "raised_at": raised_at})

            await session.execute(text("""
                INSERT INTO txn.alert (
                    alert_id, episode_id, evaluation_id, tier, reason_key, status, raised_at, notified_at, acknowledged_at, acknowledged_by
                ) VALUES (
                    :aid, :eid, :evid, 'review', 'reason_fall', 'acknowledged', :raised_at, :raised_at, :ack_at, :ack_by
                );
            """), {"aid": alert_id, "eid": p["episode_id"], "evid": eval_id, "raised_at": raised_at, "ack_at": ack_at, "ack_by": admin_sarah_id})
            print(f"  [+] [REVIEW]     {p['mrn']} ({p['patient_name']}): Reported fall without knee impact (Ack by Nurse Sarah)")

        # --- ROW 6: MISSED (FX-06 Drop Out / B. Kowalski equivalent - Evaluated Today) ---
        p = patient_map.get("FX-06")
        if p:
            eval_id = uuid4()
            alert_id = uuid4()
            raised_at = now - timedelta(hours=2)
            reasons = [
                {"name": "missed_submission", "score": 2, "weight": 2, "detail": "No check-in for 2 expected cycles (WhatsApp inactive 18h)"}
            ]
            # check_in_id is NULL for synthetic missed check-in evaluation
            await session.execute(text("""
                INSERT INTO txn.check_in_evaluation (
                    evaluation_id, check_in_id, episode_id, ruleset_id, day_after_discharge,
                    tier, total_score, is_override, reasons, reason_key, evaluated_at
                ) VALUES (
                    :evid, NULL, :eid, :rid, 5, 'missed', 0, false, CAST(:reasons AS jsonb), 'reason_missed_dropout', :raised_at
                );
            """), {"evid": eval_id, "eid": p["episode_id"], "rid": p["ruleset_id"], "reasons": json.dumps(reasons), "raised_at": now})

            await session.execute(text("""
                INSERT INTO txn.alert (
                    alert_id, episode_id, evaluation_id, tier, reason_key, status, raised_at, notified_at
                ) VALUES (
                    :aid, :eid, :evid, 'missed', 'reason_missed_dropout', 'open', :raised_at, :raised_at
                );
            """), {"aid": alert_id, "eid": p["episode_id"], "evid": eval_id, "raised_at": raised_at})
            print(f"  [+] [MISSED]     {p['mrn']} ({p['patient_name']}): 2 Overdue cycles / Inactive 18h (Evaluated today)")

        # --- QUIET COHORT (NORMAL TIER: FX-01, FX-04, FX-05, FX-09, FX-11, FX-13) ---
        quiet_cohort = ["FX-01", "FX-04", "FX-05", "FX-09", "FX-11", "FX-13"]
        for mrn in quiet_cohort:
            p = patient_map.get(mrn)
            if p:
                eval_id = uuid4()
                reasons = [{"name": "normal_trajectory", "detail": "Vitals and milestones within expected corridor"}]
                await session.execute(text("""
                    INSERT INTO txn.check_in_evaluation (
                        evaluation_id, episode_id, ruleset_id, day_after_discharge,
                        tier, total_score, is_override, reasons, reason_key, evaluated_at
                    ) VALUES (
                        :evid, :eid, :rid, 8, 'normal', 2, false, CAST(:reasons AS jsonb), 'normal_key', :now
                    );
                """), {"evid": eval_id, "eid": p["episode_id"], "rid": p["ruleset_id"], "reasons": json.dumps(reasons), "now": now})
        print(f"  [+] [NORMAL]     {len(quiet_cohort)} Quiet Cohort patients initialized (No alerts raised).")

        await session.commit()

    print("\n================================================================")
    print("                    SEEDING COMPLETE                            ")
    print("================================================================")
    print("Hospital:       St. Mary's Orthopedic Center (ID: 1, Code: CBE-01)")
    print("Active Cohort:  12 Enrolled Patients (6 Alerts: 1 Emergency, 2 Critical, 2 Review, 1 Missed, 6 Normal)")
    print("\nDemo Login Credentials:")
    print("  1. Nurse Admin:   nurse.sarah@stmarys.org  |  password123")
    print("  2. Surgeon Admin: dr.mehta@stmarys.org     |  password123")
    print("  3. Superadmin:    admin@stmarys.org        |  password123")
    print("================================================================\n")

if __name__ == "__main__":
    asyncio.run(seed_demo())
