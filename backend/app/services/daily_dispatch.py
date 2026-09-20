"""
Daily check-in dispatch service.

Finds active episodes due for a check-in reminder based on each patient's
individual time preference (checkin_window_start) in their hospital's local timezone.
Generates a secure 1-click magic link and dispatches the WhatsApp reminder.
"""

import logging
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import text

from app.core.config import settings
from app.db.session import async_session_factory
from app.services.magic_token import generate_magic_token
from app.services.whatsapp import send_whatsapp_text

logger = logging.getLogger("eras.dispatch")

# Query active episodes whose hospital local time has reached their preferred contact time,
# who have not checked in today and have not yet received today's reminder.
ELIGIBLE_REMINDERS_SQL = text("""
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
            h.timezone,
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
        s.timezone,
        s.post_op_day,
        s.hospital_current_time,
        s.checkin_window_start,
        hw.phone_number_id AS wa_phone_number_id,
        hw.access_token AS wa_access_token
    FROM patient_status s
    LEFT JOIN meta.hospital_whatsapp hw
           ON hw.hospital_id = s.hospital_id AND hw.is_default = true AND hw.is_active = true
    WHERE s.post_op_day >= 0
      -- Respect active monitoring window
      AND s.hospital_today <= s.monitoring_ends_on
      -- Respect patient's individual time preference in hospital's local timezone
      AND s.hospital_current_time >= s.checkin_window_start
      -- Ensure there are procedure questions scheduled for this recovery day
      AND EXISTS (
          SELECT 1 FROM meta.procedure_parameter pp
          WHERE pp.ruleset_id = s.ruleset_id
            AND s.post_op_day BETWEEN pp.collect_from_day AND pp.collect_to_day
      )
      -- Check remote monitoring consent was not explicitly denied
      AND NOT EXISTS (
          SELECT 1 FROM txn.episode_consent ec
          WHERE ec.episode_id = s.episode_id
            AND ec.consent_code = 'remote_monitoring'
            AND ec.granted = false
      )
      -- Skip if patient already submitted a check-in today
      AND NOT EXISTS (
          SELECT 1 FROM txn.patient_check_in c
          WHERE c.episode_id = s.episode_id
            AND c.day_after_discharge = s.post_op_day
            AND NOT c.is_superseded
      )
      -- Skip if reminder already sent today
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
    Run one pass of the daily checkin dispatch.
    Protected by a transaction-level advisory lock so concurrent workers do not collide.
    """
    factory = session_factory or async_session_factory

    async with factory() as session:
        acquired = (await session.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext('eras.daily_checkin_dispatch'))")
        )).scalar_one()

        if not acquired:
            logger.debug("Daily check-in dispatch already running elsewhere; skipping this tick.")
            return {"skipped": True, "dispatched": 0}

        rows = (await session.execute(ELIGIBLE_REMINDERS_SQL)).mappings().all()
        if not rows:
            return {"skipped": False, "dispatched": 0}

        dispatched_count = 0
        for r in rows:
            episode_id: UUID = r["episode_id"]
            patient_id: UUID = r["patient_id"]
            hospital_id: int = r["hospital_id"]
            patient_name: str = r["patient_name"]
            phone_e164: str = r["phone_e164"]
            post_op_day: int = r["post_op_day"]
            hospital_name: str = r["hospital_name"]

            first_name = patient_name.split()[0] if patient_name else "Patient"

            # 1. Generate 24h signed token
            token = generate_magic_token(episode_id=episode_id, day=post_op_day)
            magic_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/checkin?token={token}"

            # 2. Look up hospital's configured template if present, or format default
            tpl_row = (await session.execute(
                text("""
                    SELECT body FROM meta.message_template
                    WHERE hospital_id = :h AND template_key = 'checkin_reminder' AND language_code = :lang AND is_active = true
                """),
                {"h": hospital_id, "lang": r["language_code"] or "en"},
            )).mappings().first()

            if tpl_row and tpl_row["body"]:
                body = (
                    tpl_row["body"]
                    .replace("{patient_first_name}", first_name)
                    .replace("{post_op_day}", str(post_op_day))
                    .replace("{hospital_name}", hospital_name)
                    .replace("{checkin_link}", magic_url)
                )
            else:
                body = (
                    f"Good morning {first_name}! ☀️\n\n"
                    f"It is Day {post_op_day} of your recovery with {hospital_name}.\n"
                    f"Please complete today's brief health check-in (takes ~1 min):\n"
                    f"{magic_url}\n\n"
                    f"Your care team monitors your recovery daily."
                )

            # 3. Dispatch outbound WhatsApp message
            result = await send_whatsapp_text(
                to=phone_e164,
                body=body,
                phone_number_id=r.get("wa_phone_number_id"),
                access_token=r.get("wa_access_token"),
            )

            # 4. Record in txn.patient_message audit log
            await session.execute(
                text("""
                    INSERT INTO txn.patient_message (
                        episode_id, patient_id, hospital_id, message_type,
                        day_after_discharge, phone_e164, channel, direction,
                        body, magic_token, magic_url, meta_message_id,
                        status, sent_at
                    ) VALUES (
                        :episode_id, :patient_id, :hospital_id, 'checkin_reminder',
                        :day, :phone, 'whatsapp', 'outbound',
                        :body, :token, :url, :meta_id,
                        :status, CASE WHEN :status = 'sent' THEN now() ELSE null END
                    )
                    ON CONFLICT (episode_id, day_after_discharge, message_type) WHERE message_type = 'checkin_reminder'
                    DO NOTHING
                """),
                {
                    "episode_id": episode_id,
                    "patient_id": patient_id,
                    "hospital_id": hospital_id,
                    "day": post_op_day,
                    "phone": phone_e164,
                    "body": body,
                    "token": token,
                    "url": magic_url,
                    "meta_id": result.get("message_id"),
                    "status": result.get("status", "sent"),
                },
            )
            dispatched_count += 1

        await session.commit()

        if dispatched_count > 0:
            logger.info("Daily check-in dispatch sent %d WhatsApp reminder(s).", dispatched_count)

        return {"skipped": False, "dispatched": dispatched_count}
