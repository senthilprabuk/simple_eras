"""Builders for test data. All write through a session as the connecting role."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash

PASSWORD = "correct-horse-battery"


@dataclass
class Hospital:
    hospital_id: int
    admin_user_id: UUID
    email: str
    password: str
    episode_id: UUID


async def create_hospital(
    session: AsyncSession,
    code: str,
    *,
    timezone_name: str = "Asia/Kolkata",
    ack_window_secs: int = 900,
) -> Hospital:
    """A hospital with one active admin and one patient on an active episode."""
    hospital_id = (await session.execute(text("""
        INSERT INTO meta.hospital (hospital_code, hospital_name, timezone, ack_window_secs)
        VALUES (:code, :name, :tz, :window)
        RETURNING hospital_id
    """), {"code": code, "name": f"Hospital {code}", "tz": timezone_name, "window": ack_window_secs})).scalar_one()

    email = f"admin.{code.lower()}@example.org"
    admin_user_id = (await session.execute(text("""
        INSERT INTO meta.admin_user (hospital_id, email, hashed_password, full_name, role)
        VALUES (:h, :email, :pwd, :name, 'admin')
        RETURNING admin_user_id
    """), {"h": hospital_id, "email": email, "pwd": get_password_hash(PASSWORD), "name": f"Admin {code}"})).scalar_one()

    patient_id = (await session.execute(text("""
        INSERT INTO txn.patient (hospital_id, mrn, patient_name, phone_e164)
        VALUES (:h, :mrn, :name, '+919800000001')
        RETURNING patient_id
    """), {"h": hospital_id, "mrn": f"{code}-P1", "name": f"Patient {code}"})).scalar_one()

    episode_id = (await session.execute(text("""
        INSERT INTO txn.patient_episode
            (patient_id, hospital_id, procedure_id, ruleset_id, surgery_date, discharge_date,
             monitoring_ends_on, consent_version, consent_at, status)
        SELECT :p, :h, sp.procedure_id, r.ruleset_id,
               current_date - 12, current_date - 10, current_date + 74, 'v1', now(), 'active'
        FROM meta.surgical_procedure sp
        JOIN meta.ruleset r ON r.procedure_id = sp.procedure_id AND r.status = 'approved'
        WHERE sp.procedure_code = 'TKR'
        RETURNING episode_id
    """), {"p": patient_id, "h": hospital_id})).scalar_one()

    await session.commit()
    return Hospital(hospital_id, admin_user_id, email, PASSWORD, episode_id)


async def create_alert(
    session: AsyncSession,
    episode_id: UUID,
    *,
    tier: str = "critical",
    status: str = "open",
    raised_ago: timedelta = timedelta(minutes=1),
    acknowledged_after: Optional[timedelta] = None,
    acknowledged_by: Optional[UUID] = None,
) -> UUID:
    """An alert with its evaluation. acknowledged_after is measured from raised_at."""
    raised_at = datetime.now(timezone.utc) - raised_ago
    acknowledged_at = raised_at + acknowledged_after if acknowledged_after is not None else None
    evaluation_id, alert_id = uuid4(), uuid4()
    reason_key = f"test_{alert_id.hex}"

    await session.execute(text("""
        INSERT INTO txn.check_in_evaluation
            (evaluation_id, episode_id, ruleset_id, day_after_discharge, tier, reasons, reason_key, evaluated_at)
        SELECT :ev, :ep, e.ruleset_id, 4, :tier, CAST(:reasons AS jsonb), :key, :raised_at
        FROM txn.patient_episode e WHERE e.episode_id = :ep
    """), {
        "ev": evaluation_id, "ep": episode_id, "tier": tier, "key": reason_key, "raised_at": raised_at,
        "reasons": json.dumps([{"name": "test_signal", "detail": "Test signal", "score": 3, "weight": 3}]),
    })
    await session.execute(text("""
        INSERT INTO txn.alert
            (alert_id, episode_id, evaluation_id, tier, reason_key, status, raised_at,
             acknowledged_at, acknowledged_by)
        VALUES (:a, :ep, :ev, :tier, :key, :status, :raised_at, :ack_at, :ack_by)
    """), {
        "a": alert_id, "ep": episode_id, "ev": evaluation_id, "tier": tier, "key": reason_key,
        "status": status, "raised_at": raised_at, "ack_at": acknowledged_at, "ack_by": acknowledged_by,
    })
    await session.commit()
    return alert_id


async def episode_for_mrn(session: AsyncSession, mrn: str) -> UUID:
    return (await session.execute(text("""
        SELECT e.episode_id FROM txn.patient_episode e
        JOIN txn.patient p ON p.patient_id = e.patient_id
        WHERE p.mrn = :mrn
    """), {"mrn": mrn})).scalar_one()


async def admin_id_for(session: AsyncSession, email: str) -> UUID:
    return (await session.execute(
        text("SELECT admin_user_id FROM meta.admin_user WHERE email = :email AND hospital_id = 1"),
        {"email": email},
    )).scalar_one()
