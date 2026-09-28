"""
Messages to patients: their wording, the outbound log, and delivery.

A message is written to txn.patient_message as 'queued' by the transaction that
decides to send it, and sent afterwards in a short transaction of its own.
Sending inside the deciding transaction would leave a delivered message with no
record whenever that transaction rolled back, and the next pass would send it
again. Each send locks its row (FOR UPDATE SKIP LOCKED) so two workers never send
the same message; a crash between Meta accepting it and the commit can still
send it twice, which beats a patient never hearing.

With WHATSAPP_PROVIDER=meta every message goes out as an approved Meta template,
because WhatsApp only lets a business send free text within 24 hours of the
patient writing to it and these messages start the conversation. The Meta
template is named after the ERAS template key (checkin_reminder,
checkin_confirmation, urgent_guidance) in the language of the wording used, and
its {{1}}, {{2}}... are the placeholders of the hospital's wording in the order
they appear. The wording approved in Meta must therefore match the templates page.

The check-in link is a credential for the patient's day, so it is minted at send
time and never stored: the logged body shows [check-in link] in its place. The
token goes after '#', which browsers never send to a server, so no web server or
proxy logs it either.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_factory
from app.schemas.template import PLACEHOLDER_PATTERN
from app.services.magic_token import generate_magic_token
from app.services.whatsapp import resolve_credentials, send_whatsapp_template

logger = logging.getLogger("eras.patient_messages")

# A send that fails for a passing reason is tried on this many dispatcher passes.
MAX_ATTEMPTS = 3
REDACTED_LINK = "[check-in link]"


@dataclass(frozen=True)
class Wording:
    body: str
    language_code: str


class WordingUnfillable(ValueError):
    """The wording uses a placeholder this message has no value for."""


def reply_type_for(tier: str) -> str:
    """
    The WhatsApp reply to a scored check-in. Critical and emergency verdicts get
    urgent guidance, whose wording tells the patient to call now; emergency is what
    breathlessness or chest pain produces. A check-in the nurses will review gets
    the same plain receipt as a normal one.
    """
    return "urgent_guidance" if tier in ("critical", "emergency") else "checkin_confirmation"


def message_values(
    message_type: str,
    *,
    patient_name: str,
    hospital_name: str,
    day: int,
    checkin_link: Optional[str] = None,
    hospital_phone: Optional[str] = None,
) -> Dict[str, str]:
    """
    What each placeholder stands for. Only a reminder has a link to give, and
    {hospital_phone} only has a value once the hospital has set its number.
    """
    names = (patient_name or "").split()
    values = {
        "patient_first_name": names[0] if names else patient_name,
        "hospital_name": hospital_name,
        "post_op_day": str(day),
    }
    if message_type == "checkin_reminder":
        values["checkin_link"] = checkin_link or REDACTED_LINK
    if hospital_phone:
        values["hospital_phone"] = hospital_phone
    return values


def render(body: str, values: Dict[str, str]) -> str:
    missing = sorted({name for name in PLACEHOLDER_PATTERN.findall(body) if name not in values})
    if missing:
        raise WordingUnfillable(f"uses {', '.join('{' + n + '}' for n in missing)}, which this message cannot fill")
    return PLACEHOLDER_PATTERN.sub(lambda m: values[m.group(1)], body)


def template_parameters(body: str, values: Dict[str, str]) -> List[str]:
    """Meta's {{1}}, {{2}}... are the wording's placeholders in the order they appear."""
    render(body, values)
    return [values[name] for name in PLACEHOLDER_PATTERN.findall(body)]


async def load_wording(
    session: AsyncSession, hospital_id: int, template_key: str, language_code: Optional[str]
) -> Optional[Wording]:
    """The hospital's active wording in the patient's language, else in English; None when it has neither."""
    row = (await session.execute(text("""
        SELECT body, language_code FROM meta.message_template
        WHERE hospital_id = :h AND template_key = :key AND is_active
          AND language_code IN (:lang, 'en')
        ORDER BY language_code = :lang DESC
        LIMIT 1
    """), {"h": hospital_id, "key": template_key, "lang": language_code or "en"})).mappings().first()
    return Wording(row["body"], row["language_code"]) if row else None


async def queue_message(
    session: AsyncSession,
    *,
    episode_id: UUID,
    patient_id: UUID,
    hospital_id: int,
    message_type: str,
    day: int,
    phone_e164: str,
    wording: Optional[Wording],
    values: Dict[str, str],
) -> Optional[UUID]:
    """
    Record an outbound message as queued, for deliver_message once the caller
    commits. Returns its id, or None when there is nothing to send: the day's
    reminder is already recorded, or the hospital has no usable wording. A
    missing wording is recorded as a failed message, so the gap shows in the log
    once rather than being retried every pass.
    """
    body, error = "", None
    if wording is None:
        error = f"No active {message_type} wording in the patient's language or English"
    else:
        try:
            body = render(wording.body, values)
        except WordingUnfillable as exc:
            error = f"The {message_type} wording {exc}"

    message_id = (await session.execute(text("""
        INSERT INTO txn.patient_message (
            episode_id, patient_id, hospital_id, message_type, day_after_discharge,
            phone_e164, channel, direction, body, status, error_message
        ) VALUES (
            :episode_id, :patient_id, :hospital_id, :message_type, :day,
            :phone, 'whatsapp', 'outbound', :body, :status, :error
        )
        ON CONFLICT DO NOTHING
        RETURNING message_id
    """), {
        "episode_id": episode_id, "patient_id": patient_id, "hospital_id": hospital_id,
        "message_type": message_type, "day": day, "phone": phone_e164, "body": body,
        "status": "failed" if error else "queued", "error": error,
    })).scalar_one_or_none()

    if error:
        if message_id is not None:
            logger.warning("%s for episode %s not sent: %s", message_type, episode_id, error)
        return None
    return message_id


DELIVERABLE = text("""
    SELECT m.message_id, m.message_type, m.episode_id, m.hospital_id, m.day_after_discharge,
           m.phone_e164, m.attempts, p.patient_name, p.language_code, h.hospital_name,
           h.emergency_phone_e164, hw.phone_number_id, hw.access_token
    FROM txn.patient_message m
    JOIN txn.patient p   ON p.patient_id = m.patient_id
    JOIN meta.hospital h ON h.hospital_id = m.hospital_id
    LEFT JOIN meta.hospital_whatsapp hw
           ON hw.hospital_id = m.hospital_id AND hw.is_default AND hw.is_active
    WHERE m.message_id = :message_id AND m.status = 'queued'
    FOR UPDATE OF m SKIP LOCKED
""")


async def deliver_message(session: AsyncSession, message_id: UUID) -> Optional[str]:
    """
    Send one queued message and commit what happened. Returns its status after:
    sent, queued (sending disabled, or a passing failure left for a retry) or
    failed. None when it is no longer queued or another worker holds it.
    """
    m = (await session.execute(DELIVERABLE, {"message_id": message_id})).mappings().first()
    if m is None:
        await session.rollback()
        return None

    message_type = m["message_type"]
    wording = await load_wording(session, m["hospital_id"], message_type, m["language_code"])
    if wording is None:
        return await _record(session, message_id, "failed", m["attempts"], f"No active {message_type} wording")

    link = None
    if message_type == "checkin_reminder":
        token = generate_magic_token(m["episode_id"], m["day_after_discharge"])
        link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/checkin#token={token}"
    values = message_values(
        message_type, patient_name=m["patient_name"], hospital_name=m["hospital_name"],
        day=m["day_after_discharge"], checkin_link=link, hospital_phone=m["emergency_phone_e164"],
    )
    try:
        parameters = template_parameters(wording.body, values)
    except WordingUnfillable as exc:
        return await _record(session, message_id, "failed", m["attempts"], f"The {message_type} wording {exc}")

    result = await send_whatsapp_template(
        m["phone_e164"], message_type, wording.language_code, parameters,
        resolve_credentials(m["phone_number_id"], m["access_token"]),
        reference=f"patient_message {message_id} ({message_type})",
    )
    if result.status == "queued":
        await session.rollback()
        return "queued"

    attempts = m["attempts"] + 1
    if result.status == "sent":
        return await _record(session, message_id, "sent", attempts, None, result.message_id)
    if result.retryable and attempts < MAX_ATTEMPTS:
        return await _record(session, message_id, "queued", attempts, result.error)
    return await _record(session, message_id, "failed", attempts, result.error)


async def _record(
    session: AsyncSession,
    message_id: UUID,
    status: str,
    attempts: int,
    error: Optional[str],
    meta_message_id: Optional[str] = None,
) -> str:
    await session.execute(text("""
        UPDATE txn.patient_message
           SET status = :status, attempts = :attempts, error_message = :error,
               meta_message_id = COALESCE(:meta_id, meta_message_id),
               sent_at = CASE WHEN :status = 'sent' THEN now() ELSE sent_at END
         WHERE message_id = :message_id
    """), {"status": status, "attempts": attempts, "error": error, "meta_id": meta_message_id, "message_id": message_id})
    await session.commit()
    return status


async def deliver_queued_messages(session_factory=None, batch_size: int = 50) -> Dict[str, int]:
    """
    One dispatcher pass: give up on messages whose day has passed, then send the
    rest oldest first, each in its own transaction.
    """
    factory = session_factory or async_session_factory

    async with factory() as session:
        expired = (await session.execute(text("""
            UPDATE txn.patient_message m
               SET status = 'failed', error_message = 'Not sent before the day it was for had ended'
              FROM txn.patient_episode e
              JOIN meta.hospital h ON h.hospital_id = e.hospital_id
             WHERE e.episode_id = m.episode_id
               AND m.status = 'queued' AND m.direction = 'outbound'
               AND m.day_after_discharge < ((now() AT TIME ZONE h.timezone)::date - e.discharge_date)::int
        """))).rowcount
        queued = (await session.execute(text("""
            SELECT message_id FROM txn.patient_message
            WHERE status = 'queued' AND direction = 'outbound'
            ORDER BY created_at
            LIMIT :batch_size
        """), {"batch_size": batch_size})).scalars().all()
        await session.commit()

    if settings.WHATSAPP_PROVIDER == "disabled":
        if queued:
            logger.warning(
                "%d patient WhatsApp message(s) waiting, but WHATSAPP_PROVIDER is 'disabled': "
                "no patient has been messaged.", len(queued),
            )
        return {"sent": 0, "failed": 0, "waiting": len(queued), "expired": expired}

    outcomes = []
    for message_id in queued:
        async with factory() as session:
            outcomes.append(await deliver_message(session, message_id))

    sent, failed = outcomes.count("sent"), outcomes.count("failed")
    if sent or failed or expired:
        logger.info("Patient WhatsApp messages: %d sent, %d failed, %d expired.", sent, failed, expired)
    return {"sent": sent, "failed": failed, "waiting": outcomes.count("queued"), "expired": expired}
