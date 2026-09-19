"""
Dispatches queued escalation notifications.

NOTIFICATION_PROVIDER selects the channel:
  disabled  leave them queued and warn, so an unconfigured deployment never
            looks as though clinicians were told when they were not
  log       write each to the application log and mark it sent (development)
"""

import logging
from typing import Dict

from sqlalchemy import text

from app.core.config import settings
from app.db.session import async_session_factory

logger = logging.getLogger("eras.notifications")

async def dispatch_queued_notifications(session_factory=None, batch_size: int = 50) -> Dict[str, int]:
    factory = session_factory or async_session_factory

    async with factory() as session:
        if settings.NOTIFICATION_PROVIDER == "disabled":
            queued = (await session.execute(
                text("SELECT count(*) FROM txn.alert_notification WHERE status = 'queued'")
            )).scalar_one()
            if queued:
                logger.warning(
                    "%d escalation notification(s) waiting, but NOTIFICATION_PROVIDER is 'disabled': "
                    "no clinician has been notified.", queued,
                )
            return {"sent": 0, "queued": queued}

        # SKIP LOCKED lets a second worker take a different batch instead of waiting.
        batch = (await session.execute(
            text("""
                SELECT n.notification_id, n.channel, n.recipient, a.alert_id, a.tier
                FROM txn.alert_notification n
                JOIN txn.alert a ON a.alert_id = n.alert_id
                WHERE n.status = 'queued'
                ORDER BY n.created_at
                LIMIT :batch_size
                FOR UPDATE OF n SKIP LOCKED
            """),
            {"batch_size": batch_size},
        )).mappings().all()

        for n in batch:
            # Patient details stay out of the log: the alert id is enough to look them up.
            logger.info(
                "[notification:%s] to %s: %s alert %s unacknowledged past its SLA",
                n["channel"], n["recipient"], n["tier"], n["alert_id"],
            )
            await session.execute(
                text("""
                    UPDATE txn.alert_notification
                       SET status = 'sent', sent_at = now(), attempts = attempts + 1,
                           provider_ref = 'log', last_error = NULL
                     WHERE notification_id = :notification_id
                """),
                {"notification_id": n["notification_id"]},
            )
        await session.commit()

    return {"sent": len(batch), "queued": 0}
