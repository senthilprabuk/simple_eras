"""
Missed check-in sweep: the engine's second call site.

A patient who stops answering is the one the dashboard most needs to show, and
silence produces no submission to score. So once a day this sweep finds the
active episodes that owed a check-in yesterday and did not send one, and runs the
same evaluator against an all-unknown reading. A second implementation here would
diverge from the real one at the first threshold change, which is why the sweep
calls `evaluate_missed_check_in` rather than deciding anything itself.

Yesterday, not today: a patient still has the rest of today to answer. The day is
counted in the hospital's own timezone, so nothing rolls over at half past five
in the morning for an Asia/Kolkata clinic.
"""

import logging
from typing import Any, Dict

from sqlalchemy import text

from app.db.session import async_session_factory
from app.services.rules_engine import evaluate_missed_check_in, load_ruleset

logger = logging.getLogger("eras.missed")

# An episode owes a check-in for a day inside its monitoring window. A day with a
# live submission, or one already judged, is left alone: the sweep is idempotent
# and can run as often as the scheduler likes.
OWED_YESTERDAY = text("""
    WITH day_for AS (
        SELECT e.episode_id, e.ruleset_id,
               ((now() AT TIME ZONE h.timezone)::date - e.discharge_date)::int - 1 AS day
        FROM txn.patient_episode e
        JOIN meta.hospital h ON h.hospital_id = e.hospital_id
        WHERE e.status = 'active' AND h.is_active
    )
    SELECT d.episode_id, d.ruleset_id, d.day
    FROM day_for d
    WHERE d.day >= 0
      AND EXISTS (SELECT 1 FROM meta.procedure_parameter pp
                  WHERE pp.ruleset_id = d.ruleset_id AND d.day BETWEEN pp.collect_from_day AND pp.collect_to_day)
      AND NOT EXISTS (SELECT 1 FROM txn.patient_check_in c
                      WHERE c.episode_id = d.episode_id AND c.day_after_discharge = d.day
                        AND NOT c.is_superseded)
      AND NOT EXISTS (SELECT 1 FROM txn.check_in_evaluation v
                      WHERE v.episode_id = d.episode_id AND v.day_after_discharge = d.day)
    ORDER BY d.episode_id
""")


async def run_missed_checkin_sweep(session_factory=None) -> Dict[str, Any]:
    """
    Run one sweep. Safe to call from several processes at once: a transaction-level
    advisory lock lets exactly one proceed and the others return immediately.
    """
    factory = session_factory or async_session_factory

    async with factory() as session:
        acquired = (await session.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext('eras.missed_checkin_sweep'))")
        )).scalar_one()
        if not acquired:
            logger.debug("Missed check-in sweep already running elsewhere; skipping this tick.")
            return {"skipped": True, "evaluated": 0, "alerts": 0}

        owed = (await session.execute(OWED_YESTERDAY)).mappings().all()
        alerts = 0
        rulesets: Dict[int, Any] = {}
        for row in owed:
            ruleset_id = row["ruleset_id"]
            if ruleset_id not in rulesets:
                rulesets[ruleset_id] = await load_ruleset(session, ruleset_id)
            _, alert_id = await evaluate_missed_check_in(
                session, episode_id=row["episode_id"], ruleset_id=ruleset_id, day=row["day"],
                ruleset=rulesets[ruleset_id],
            )
            alerts += alert_id is not None
        await session.commit()

    if owed:
        logger.info("Missed check-in sweep: judged %d day(s), raised %d alert(s).", len(owed), alerts)
    return {"skipped": False, "evaluated": len(owed), "alerts": alerts}
