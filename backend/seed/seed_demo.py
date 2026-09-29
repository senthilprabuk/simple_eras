#!/usr/bin/env python3
"""
ERAS demo seed: a hospital that looks like a working ward, not a test bench.

Run after db/seed/02_fixtures.sql, which rebuilds the FX-* patients at post-op
day 21; `.claude/skills/run-simple-eras/app.sh reset-demo` runs both. Alert times
are relative to now, so seed just before a demo: an hour later today's open
alerts are past their 15-minute window and the dashboard reads as though nobody
responded.

Populates:
  1. The hospital, Noyyal Orthopaedic Centre in Coimbatore: a 15-minute
     acknowledgement window, a demo ward number, and its WhatsApp helpline name.
  2. Clinicians: a nurse, a surgeon and a superadmin, plus the platform app admin.
  3. The past week's alerts, each acknowledged and resolved with an outcome, so
     acknowledgement compliance reads like a ward that answers its alerts.
  4. Today's queue: 1 emergency, 2 critical, 2 review (acknowledged), 1 missed.
  5. Normal evaluations for the quiet cohort.

Reason names are the ruleset's own signal names, so the alerts screen groups
them by complication, and reason keys come from the engine's reason_key_for,
so a later check-in reporting the same problem joins the seeded alert instead
of opening a second one.
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

from app.core.security import get_password_hash
from app.db.session import async_session_factory
from app.services.rules_engine import reason_key_for

HOSPITAL_NAME = "Noyyal Orthopaedic Centre"
HELPLINE_NAME = "Noyyal Ortho Helpline"
# Demo only: no Indian subscriber number starts with 0, so the check-in's
# "Call the ward" button dials a number that reaches nobody.
DEMO_WARD_NUMBER = "+914220000000"
PASSWORD = "password123"

NURSE = ("anitha.joseph@noyyalortho.in", "Anitha Joseph", "admin")
SURGEON = ("dr.arun@noyyalortho.in", "Dr. Arun Prakash", "admin")
SUPERADMIN = ("admin@noyyalortho.in", "Vasanth Raj", "superadmin")
APP_ADMIN_EMAIL = "appadmin@eras.local"

# The past week, oldest first: (MRN, days ago, post-op day, tier, reasons,
# minutes to acknowledge, outcome, note). One of the fourteen was acknowledged
# late, as happens on a real ward.
HISTORY = [
    ("FX-02", 6, 15, "review", [("temp_c", "Temperature 37.9 °C", 1, 3)], 6, "reassured",
     "Taking paracetamol; to recheck in the evening"),
    ("FX-11", 6, 15, "critical", [("hr", "Pulse 118, 32 above discharge", 3, 2), ("pain", "Pain 8 of 10", 2, 2)], 4,
     "plan_adjusted", "Analgesia increased; pulse settled on repeat"),
    ("FX-05", 5, 16, "review", [("pain_rising", "Pain up 3 points on this week's average", 2, 2)], 9, "reassured", None),
    ("FX-14", 5, 16, "review", [("slow_burn", "Temperature rising slowly for five days", 2, 2)], 7, "same_day_review",
     "Seen in clinic; wound clean"),
    ("FX-07", 4, 17, "review", [("knee_bend", "Knee bend still limited to chair height", 2, 1)], 11, "plan_adjusted",
     "Physiotherapy visits increased"),
    ("FX-09", 4, 17, "review", [("drainage", "Fluid still leaking from the wound", 2, 2)], 5, "same_day_review",
     "Dressing changed; no signs of infection"),
    ("FX-04", 3, 18, "critical", [("calf_pain", "Calf more swollen than the other leg", 3, 3)], 3,
     "same_day_review", "Doppler scan clear of clot"),
    ("FX-15", 3, 18, "review", [("pain", "Pain 7 of 10", 2, 2)], 22, "reassured", "Reached on the second call"),
    ("FX-12", 2, 19, "review", [("mobility_regression", "900 steps, below the week's best of 1,200", 1, 1)], 8,
     "reassured", None),
    ("FX-02", 2, 19, "critical", [("chills", "Shivering and chills overnight", 3, 3), ("temp_c", "Temperature 38.3 °C", 2, 3)],
     2, "same_day_review", "Blood tests sent; started on antibiotics"),
    ("FX-11", 1, 20, "review", [("pain", "Pain 6 of 10", 2, 2)], 6, "reassured", None),
    ("FX-13", 1, 20, "review", [("weight_bear", "Harder to put weight on the operated leg", 2, 3)], 10, "plan_adjusted",
     "Walking frame for another week"),
    ("FX-05", 1, 20, "review", [("temp_c", "Temperature 37.8 °C", 1, 3)], 7, "reassured", None),
    ("FX-14", 1, 20, "critical", [("slow_burn", "Temperature rising slowly for six days", 2, 2),
                                  ("pain_rising", "Pain up 3 points on this week's average", 2, 2)], 4,
     "same_day_review", "Aspiration booked"),
]


def _reasons(signals):
    """(name, detail, score, weight) as the engine stores them: worst first, points = score x weight."""
    ranked = sorted(signals, key=lambda s: (s[2] * s[3], s[2]), reverse=True)
    return [{"name": n, "detail": d, "score": sc, "points": sc * w} for n, d, sc, w in ranked]


async def _alert(session, patient, *, day, tier, signals, raised_at, total_score, is_override=False, check_in=True,
                 acknowledged_at=None, acknowledged_by=None, resolved_at=None, resolved_by=None,
                 outcome=None, note=None):
    reasons = _reasons(signals)
    key = reason_key_for(r["name"] for r in reasons)
    evaluation_id = (await session.execute(text("""
        INSERT INTO txn.check_in_evaluation (
            episode_id, ruleset_id, day_after_discharge, tier, total_score, is_override,
            reasons, reason_key, evaluated_at, coverage
        ) VALUES (:e, :r, :d, :tier, :total, :override, CAST(:reasons AS jsonb), :key, :at, :coverage)
        RETURNING evaluation_id
    """), {
        "e": patient["episode_id"], "r": patient["ruleset_id"], "d": day, "tier": tier, "total": total_score,
        "override": is_override, "reasons": json.dumps(reasons), "key": key, "at": raised_at,
        # A missed day has nothing answered; seeded check-ins answered everything.
        "coverage": 1.0 if check_in else 0.0,
    })).scalar_one()
    status = "resolved" if resolved_at else "acknowledged" if acknowledged_at else "open"
    await session.execute(text("""
        INSERT INTO txn.alert (
            alert_id, episode_id, evaluation_id, tier, reason_key, status, raised_at, notified_at,
            acknowledged_at, acknowledged_by, resolved_at, resolved_by, outcome, outcome_note
        ) VALUES (
            :a, :e, :ev, :tier, :key, :status, :raised_at, :raised_at,
            :ack_at, :ack_by, :resolved_at, :resolved_by, :outcome, :note
        )
    """), {
        "a": uuid4(), "e": patient["episode_id"], "ev": evaluation_id, "tier": tier, "key": key, "status": status,
        "raised_at": raised_at, "ack_at": acknowledged_at, "ack_by": acknowledged_by,
        "resolved_at": resolved_at, "resolved_by": resolved_by, "outcome": outcome, "note": note,
    })


async def seed_demo(session_factory=None):
    print("================================================================")
    print("        ERAS DEMO CLINICAL SEED SCRIPT                          ")
    print("================================================================\n")

    now = datetime.now(timezone.utc)

    async with (session_factory or async_session_factory)() as session:
        print("[*] 1. Hospital:")
        await session.execute(text("""
            UPDATE meta.hospital
            SET hospital_name = :name, ack_window_secs = 900, emergency_phone_e164 = :ward
            WHERE hospital_id = 1
        """), {"name": HOSPITAL_NAME, "ward": DEMO_WARD_NUMBER})
        await session.execute(text("""
            UPDATE meta.hospital_whatsapp
            SET display_name = :helpline, verify_token = 'eras_noyyal_verify_2026'
            WHERE hospital_id = 1
        """), {"helpline": HELPLINE_NAME})
        print(f"  [+] {HOSPITAL_NAME}: 15-minute window, demo ward number, WhatsApp helpline '{HELPLINE_NAME}'.")

        print("\n[*] 2. Clinicians:")
        hashed = get_password_hash(PASSWORD)
        await session.execute(text("DELETE FROM meta.admin_user WHERE hospital_id = 1"))
        staff = {}
        for email, name, role in (NURSE, SURGEON, SUPERADMIN):
            staff[email] = (await session.execute(text("""
                INSERT INTO meta.admin_user (hospital_id, email, hashed_password, full_name, role, is_active)
                VALUES (1, :email, :pwd, :name, :role, true)
                RETURNING admin_user_id
            """), {"email": email, "pwd": hashed, "name": name, "role": role})).scalar_one()
            print(f"  [+] {role.upper():<10} {name:<18} | {email}")
        nurse, surgeon = staff[NURSE[0]], staff[SURGEON[0]]

        # The platform's app admin manages hospitals and rulesets and belongs to no hospital.
        await session.execute(text("DELETE FROM meta.admin_user WHERE email = :email AND hospital_id IS NULL"),
                              {"email": APP_ADMIN_EMAIL})
        await session.execute(text("""
            INSERT INTO meta.admin_user (hospital_id, email, hashed_password, full_name, role, is_active)
            VALUES (NULL, :email, :pwd, 'Platform App Admin', 'app_admin', true)
        """), {"email": APP_ADMIN_EMAIL, "pwd": hashed})
        print(f"  [+] APP_ADMIN  Platform App Admin | {APP_ADMIN_EMAIL}")

        patients = {r["mrn"]: r for r in (await session.execute(text("""
            SELECT p.mrn, p.patient_name, e.episode_id, e.ruleset_id
            FROM txn.patient p
            JOIN txn.patient_episode e ON e.patient_id = p.patient_id
            WHERE p.hospital_id = 1
        """))).mappings().all()}

        await session.execute(text("DELETE FROM txn.alert_notification"))
        await session.execute(text("DELETE FROM txn.alert"))
        await session.execute(text("DELETE FROM txn.check_in_evaluation"))

        print("\n[*] 3. The past week's alerts, acknowledged and resolved:")
        on_time = 0
        for i, (mrn, days_ago, day, tier, signals, ack_minutes, outcome, note) in enumerate(HISTORY):
            if mrn not in patients:
                continue
            raised_at = now - timedelta(days=days_ago, hours=3 + i % 5)
            acknowledged_at = raised_at + timedelta(minutes=ack_minutes)
            await _alert(
                session, patients[mrn], day=day, tier=tier, signals=signals, raised_at=raised_at,
                total_score=sum(sc * w for _, _, sc, w in signals),
                acknowledged_at=acknowledged_at, acknowledged_by=nurse if i % 3 else surgeon,
                resolved_at=acknowledged_at + timedelta(minutes=20 + i % 4 * 10),
                resolved_by=surgeon if outcome == "same_day_review" else nurse, outcome=outcome, note=note,
            )
            on_time += ack_minutes <= 15
        print(f"  [+] {len(HISTORY)} alerts over six days; {on_time} acknowledged within 15 minutes.")

        print("\n[*] 4. Today's queue:")
        today = [
            ("FX-03", "emergency", 21, 3, [("calf_pain", "Calf swelling and acute sharp pain", 3, 3),
                                          ("breathless", "Newly short of breath", 3, 3)], True, None),
            ("FX-02", "critical", 21, 11, [("fever_returned", "Fever returned: 38.6 °C", 3, 3),
                                          ("drainage", "Fluid leaking from the wound", 2, 2)], True, None),
            ("FX-07", "critical", 21, 2, [("pain", "Pain 6 of 10", 2, 2), ("hr", "Pulse 104, 22 above discharge", 2, 2),
                                          ("temp_c", "Temperature 37.9 °C", 1, 3)], False, None),
            ("FX-08", "review", 21, 42, [("temp_c", "Temperature 38.1 °C", 2, 3)], False, (8, surgeon)),
            ("FX-12", "review", 21, 75, [("mobility_regression", "400 steps, below half of this patient's best of 1,200",
                                          2, 1)], False, (9, nurse)),
        ]
        for mrn, tier, day, minutes_ago, signals, override, ack in today:
            raised_at = now - timedelta(minutes=minutes_ago)
            await _alert(
                session, patients[mrn], day=day, tier=tier, signals=signals, raised_at=raised_at,
                total_score=sum(sc * w for _, _, sc, w in signals), is_override=override,
                acknowledged_at=raised_at + timedelta(minutes=ack[0]) if ack else None,
                acknowledged_by=ack[1] if ack else None,
            )
            state = f"acknowledged after {ack[0]} min" if ack else "open"
            print(f"  [+] {tier.upper():<10} {mrn} {patients[mrn]['patient_name']}: raised {minutes_ago} min ago, {state}")

        # Suresh stopped checking in after day 5. The sweep raises the same problem
        # under the same reason key, so it joins this alert rather than opening another.
        # The nurse acknowledged it and is trying to reach him.
        missed_at = now - timedelta(hours=2)
        await _alert(
            session, patients["FX-06"], day=6, tier="missed", check_in=False,
            signals=[("missed_check_in", "No check-in received since day 5", 0, 0)],
            raised_at=missed_at, total_score=0,
            acknowledged_at=missed_at + timedelta(minutes=6), acknowledged_by=nurse,
        )
        print(f"  [+] MISSED     FX-06 {patients['FX-06']['patient_name']}: no check-in since day 5, acknowledged after 6 min")

        print("\n[*] 5. Quiet cohort:")
        quiet = ["FX-01", "FX-04", "FX-05", "FX-09", "FX-11", "FX-13"]
        for mrn in quiet:
            p = patients.get(mrn)
            if p:
                await session.execute(text("""
                    INSERT INTO txn.check_in_evaluation (
                        episode_id, ruleset_id, day_after_discharge, tier, total_score, is_override,
                        reasons, reason_key, evaluated_at, coverage
                    ) VALUES (:e, :r, 21, 'normal', 0, false, '[]'::jsonb, 'none', :now, 1.0)
                """), {"e": p["episode_id"], "r": p["ruleset_id"], "now": now})
        print(f"  [+] {len(quiet)} patients recovering as expected (no alerts).")

        await session.commit()

    print("\n================================================================")
    print("                    SEEDING COMPLETE                            ")
    print("================================================================")
    print(f"Hospital:       {HOSPITAL_NAME} (ID: 1, Code: CBE-01)")
    print("Today's queue:  1 emergency, 2 critical, 2 review, 1 missed; 6 patients recovering normally")
    print(f"\nDemo logins (password {PASSWORD}):")
    print(f"  1. Nurse:       {NURSE[0]:<30} {NURSE[1]}")
    print(f"  2. Surgeon:     {SURGEON[0]:<30} {SURGEON[1]}")
    print(f"  3. Superadmin:  {SUPERADMIN[0]:<30} {SUPERADMIN[1]}")
    print(f"  4. App Admin:   {APP_ADMIN_EMAIL:<30} opens /app_admin")
    print("================================================================\n")


if __name__ == "__main__":
    asyncio.run(seed_demo())
