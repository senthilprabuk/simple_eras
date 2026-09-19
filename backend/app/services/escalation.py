"""
Escalation sweep: finds critical and emergency alerts left unacknowledged past
their hospital's window, marks them escalated, and queues a notification to
every active admin at that hospital. Delivery is app/services/notifications.py.
"""

import logging
from typing import Any, Dict

from sqlalchemy import text

from app.db.session import async_session_factory

logger = logging.getLogger("eras.escalation")

# One statement: the UPDATE claims each overdue alert exactly once (escalated_at
# goes from NULL to now()), and notifications are inserted only for the rows it
# actually claimed. Admins have email addresses and nothing else, so email is
# the only channel that can be addressed.
ESCALATE_OVERDUE = text("""
    WITH escalated AS (
        UPDATE txn.alert a
           SET escalated_at = now()
          FROM txn.patient_episode e
          JOIN meta.hospital h ON h.hospital_id = e.hospital_id
         WHERE e.episode_id = a.episode_id
           AND a.status = 'open'
           AND a.tier IN ('critical', 'emergency')
           AND a.escalated_at IS NULL
           AND now() - coalesce(a.notified_at, a.raised_at) > make_interval(secs => h.ack_window_secs)
        RETURNING a.alert_id, e.hospital_id
    ),
    queued AS (
        INSERT INTO txn.alert_notification (alert_id, recipient, channel, status, attempts)
        SELECT x.alert_id, u.email, 'email', 'queued', 0
        FROM escalated x
        JOIN meta.admin_user u ON u.hospital_id = x.hospital_id AND u.is_active
        RETURNING 1
    )
    SELECT (SELECT count(*) FROM escalated) AS escalated,
           (SELECT count(*) FROM queued)    AS notifications
""")

async def run_escalation_sweep(session_factory=None) -> Dict[str, Any]:
    """
    Run one sweep. Safe to call from several processes at once: a transaction-level
    advisory lock lets exactly one proceed, and the others return immediately.
    """
    factory = session_factory or async_session_factory

    async with factory() as session:
        acquired = (await session.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext('eras.escalation_sweep'))")
        )).scalar_one()
        if not acquired:
            logger.debug("Escalation sweep already running elsewhere; skipping this tick.")
            return {"skipped": True, "escalated": 0, "notifications": 0}

        result = (await session.execute(ESCALATE_OVERDUE)).mappings().one()
        await session.commit()

    if result["escalated"]:
        logger.warning(
            "Escalated %d overdue alert(s); queued %d notification(s).",
            result["escalated"], result["notifications"],
        )
    return {"skipped": False, "escalated": result["escalated"], "notifications": result["notifications"]}
