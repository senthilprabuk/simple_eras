"""
Daily check-in reminders.

While a patient's check-in window is open in their hospital's timezone, each
active episode that owes today's check-in gets one WhatsApp reminder with a
signed link to the form. The window's end matters as much as its start: a
reminder sent late at night would carry a link that is stale by morning.

This pass only claims the reminders, as queued rows in txn.patient_message
whose unique index allows one per episode per day. patient_messages then sends
each in its own transaction, so a failure part-way through never rolls back the
record of a message that already went out.
"""

import logging
from typing import Any, Dict

from sqlalchemy import text

from app.db.session import async_session_factory
from app.services.patient_messages import deliver_queued_messages, load_wording, message_values, queue_message

logger = logging.getLogger("eras.dispatch")

DUE_REMINDERS_SQL = text("""
    WITH patient_status AS (
        SELECT
            e.episode_id,
            e.patient_id,
            e.hospital_id,
            e.ruleset_id,
            e.monitoring_ends_on,
            p.patient_name,
            p.phone_e164,
            p.language_code,
            h.hospital_name,
            e.checkin_window_start,
            e.checkin_window_end,
            (now() AT TIME ZONE h.timezone)::date AS hospital_today,
            (now() AT TIME ZONE h.timezone)::time AS hospital_current_time,
            ((now() AT TIME ZONE h.timezone)::date - e.discharge_date)::int AS post_op_day
        FROM txn.patient_episode e
        JOIN txn.patient p   ON p.patient_id = e.patient_id
        JOIN meta.hospital h ON h.hospital_id = e.hospital_id
        WHERE e.status = 'active'
          AND h.is_active = true
    )
    SELECT
        s.episode_id,
        s.patient_id,
        s.hospital_id,
        s.patient_name,
        s.phone_e164,
        s.language_code,
        s.hospital_name,
        s.post_op_day
    FROM patient_status s
    WHERE s.post_op_day >= 0
      AND s.hospital_today <= s.monitoring_ends_on
      -- Only while the patient's own check-in window is open, in the hospital's timezone
      AND s.hospital_current_time BETWEEN s.checkin_window_start AND s.checkin_window_end
      -- A day with no questions has no check-in to remind about
      AND EXISTS (
          SELECT 1 FROM meta.procedure_parameter pp
          WHERE pp.ruleset_id = s.ruleset_id
            AND s.post_op_day BETWEEN pp.collect_from_day AND pp.collect_to_day
      )
      AND NOT EXISTS (
          SELECT 1 FROM txn.episode_consent ec
          WHERE ec.episode_id = s.episode_id
            AND ec.consent_code = 'remote_monitoring'
            AND ec.granted = false
      )
      AND NOT EXISTS (
          SELECT 1 FROM txn.patient_check_in c
          WHERE c.episode_id = s.episode_id
            AND c.day_after_discharge = s.post_op_day
            AND NOT c.is_superseded
      )
      AND NOT EXISTS (
          SELECT 1 FROM txn.patient_message m
          WHERE m.episode_id = s.episode_id
            AND m.day_after_discharge = s.post_op_day
            AND m.message_type = 'checkin_reminder'
      )
    ORDER BY s.episode_id
""")


async def run_daily_checkin_dispatch(session_factory=None) -> Dict[str, Any]:
    """
    Claim today's due reminders, then send whatever patient messages are queued.
    Claiming is serialised by a transaction-level advisory lock; sending is safe
    to overlap because each message is locked while it is sent.
    """
    factory = session_factory or async_session_factory

    async with factory() as session:
        acquired = (await session.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext('eras.daily_checkin_dispatch'))")
        )).scalar_one()
        if not acquired:
            logger.debug("Daily check-in dispatch already running elsewhere; skipping this tick.")
            return {"skipped": True, "queued": 0}

        queued = 0
        for r in (await session.execute(DUE_REMINDERS_SQL)).mappings().all():
            message_id = await queue_message(
                session,
                episode_id=r["episode_id"],
                patient_id=r["patient_id"],
                hospital_id=r["hospital_id"],
                message_type="checkin_reminder",
                day=r["post_op_day"],
                phone_e164=r["phone_e164"],
                wording=await load_wording(session, r["hospital_id"], "checkin_reminder", r["language_code"]),
                values=message_values(
                    "checkin_reminder", patient_name=r["patient_name"],
                    hospital_name=r["hospital_name"], day=r["post_op_day"],
                ),
            )
            queued += message_id is not None
        await session.commit()

    if queued:
        logger.info("Daily check-in dispatch queued %d WhatsApp reminder(s).", queued)
    return {"skipped": False, "queued": queued, **await deliver_queued_messages(factory)}
