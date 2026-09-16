"""
ERAS Background Escalation Service
Runs every 60 seconds inside the FastAPI process via APScheduler.
Monitors critical and emergency alerts exceeding hospital SLA acknowledgment windows,
marks them as escalated, and queues push/SMS notifications to all active hospital admins.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory

logger = logging.getLogger("eras.escalation")
logger.setLevel(logging.INFO)

async def run_escalation_sweep(session_factory=None) -> Dict[str, Any]:
    """
    Escalation sweep job.
    1. Selects open, unacknowledged alerts with tier in ('critical', 'emergency')
       where now() - COALESCE(notified_at, raised_at) > hospital.ack_window_secs
       and escalated_at is still NULL.
    2. Marks escalated_at = now().
    3. Queues push and SMS notifications for all active admin users at that hospital.
    4. Idempotent: escalated_at IS NULL condition prevents re-firing on subsequent ticks.
    
    NOTE ON FUTURE ENHANCEMENTS:
    Repeated re-notification on a longer interval (e.g. re-alerting every 30 mins)
    can be implemented in future phases by tracking a notification_attempts counter
    or last_escalated_at timestamp, but is not part of this MVP.
    """
    factory = session_factory or async_session_factory
    overdue_alerts_found = 0
    notifications_created = 0

    async with factory() as session:
        try:
            # Query open overdue alerts breaching the hospital-specific SLA window
            query = text("""
                SELECT 
                    a.alert_id,
                    a.tier,
                    a.raised_at,
                    COALESCE(a.notified_at, a.raised_at) AS notify_time,
                    e.hospital_id,
                    h.hospital_name,
                    h.ack_window_secs
                FROM txn.alert a
                JOIN txn.patient_episode e ON e.episode_id = a.episode_id
                JOIN meta.hospital h ON h.hospital_id = e.hospital_id
                WHERE a.status = 'open'
                  AND a.tier IN ('critical', 'emergency')
                  AND a.escalated_at IS NULL
                  AND (now() - COALESCE(a.notified_at, a.raised_at)) > make_interval(secs => h.ack_window_secs);
            """)

            result = await session.execute(query)
            overdue_alerts = result.mappings().all()
            overdue_alerts_found = len(overdue_alerts)

            now_utc = datetime.now(timezone.utc)

            for alert in overdue_alerts:
                alert_id = alert["alert_id"]
                hospital_id = alert["hospital_id"]

                # 1. Update alert state: mark escalated_at
                update_stmt = text("""
                    UPDATE txn.alert
                    SET escalated_at = :now_utc
                    WHERE alert_id = :alert_id AND escalated_at IS NULL;
                """)
                await session.execute(update_stmt, {"now_utc": now_utc, "alert_id": alert_id})

                # 2. Query all active admin users at this hospital
                admin_query = text("""
                    SELECT admin_user_id, email, full_name
                    FROM meta.admin_user
                    WHERE hospital_id = :h_id AND is_active = true;
                """)
                admin_res = await session.execute(admin_query, {"h_id": hospital_id})
                admins = admin_res.mappings().all()

                # 3. Create push and SMS notification records for each active admin
                for admin in admins:
                    for channel in ("push", "sms"):
                        notif_id = uuid4()
                        notif_stmt = text("""
                            INSERT INTO txn.alert_notification (
                                notification_id, alert_id, recipient, channel, status, attempts, created_at
                            ) VALUES (
                                :notif_id, :alert_id, :recipient, :channel, 'queued', 0, :created_at
                            );
                        """)
                        await session.execute(notif_stmt, {
                            "notif_id": notif_id,
                            "alert_id": alert_id,
                            "recipient": admin["email"],
                            "channel": channel,
                            "created_at": now_utc
                        })
                        notifications_created += 1

            await session.commit()

            # Structured logging: explicitly verify liveness on every sweep tick
            logger.info(
                f"[Escalation Sweep] Completed: checked {overdue_alerts_found} overdue alerts, "
                f"escalated {overdue_alerts_found}, queued {notifications_created} notifications."
            )

        except Exception as exc:
            await session.rollback()
            logger.error(f"[Escalation Sweep] Error during execution: {exc}", exc_info=True)
            raise exc

    return {
        "overdue_alerts_found": overdue_alerts_found,
        "notifications_created": notifications_created
    }
