from datetime import time
import pytest
from sqlalchemy import text

from app.services.daily_dispatch import run_daily_checkin_dispatch


@pytest.mark.asyncio
async def test_dispatch_respects_patient_time_preference(db):
    # Find an active episode
    row = (await db.execute(text("""
        SELECT e.episode_id, e.hospital_id, h.timezone,
               ((now() AT TIME ZONE h.timezone)::date - e.discharge_date)::int AS post_op_day
        FROM txn.patient_episode e
        JOIN meta.hospital h ON h.hospital_id = e.hospital_id
        WHERE e.status = 'active'
        LIMIT 1
    """))).mappings().first()
    assert row is not None

    episode_id = row["episode_id"]
    post_op_day = row["post_op_day"]

    # Clear prior messages and checkins for this day to test cleanly
    await db.execute(text("DELETE FROM txn.patient_message WHERE episode_id = :e"), {"e": episode_id})
    await db.execute(text("DELETE FROM txn.patient_check_in WHERE episode_id = :e AND day_after_discharge = :d"), {"e": episode_id, "d": post_op_day})
    await db.commit()

    # Case 1: Patient prefers evening (23:59), hospital local time is earlier -> MUST NOT dispatch
    await db.execute(
        text("UPDATE txn.patient_episode SET checkin_window_start = '23:59:00', checkin_window_end = '23:59:59' WHERE episode_id = :e"),
        {"e": episode_id},
    )
    await db.commit()

    # Clear any other episodes' messages to isolate this check or filter by our episode
    result1 = await run_daily_checkin_dispatch()
    # Check if a message was created for our episode
    msg1 = (await db.execute(
        text("SELECT 1 FROM txn.patient_message WHERE episode_id = :e AND day_after_discharge = :d"),
        {"e": episode_id, "d": post_op_day},
    )).scalar_one_or_none()
    assert msg1 is None, "Should not dispatch reminder before patient's checkin_window_start"

    # Case 2: Patient preferred time was 00:01 (already passed today) -> MUST dispatch
    await db.execute(
        text("UPDATE txn.patient_episode SET checkin_window_start = '00:01:00', checkin_window_end = '02:00:00' WHERE episode_id = :e"),
        {"e": episode_id},
    )
    await db.commit()

    result2 = await run_daily_checkin_dispatch()
    assert result2["dispatched"] >= 1

    msg2 = (await db.execute(
        text("""
            SELECT message_type, status, magic_token, magic_url, phone_e164
            FROM txn.patient_message
            WHERE episode_id = :e AND day_after_discharge = :d
        """),
        {"e": episode_id, "d": post_op_day},
    )).mappings().first()
    assert msg2 is not None
    assert msg2["message_type"] == "checkin_reminder"
    assert msg2["status"] == "sent"
    assert msg2["magic_token"] is not None
    assert "/checkin?token=" in msg2["magic_url"]

    # Case 3: Running again on the same day -> MUST NOT duplicate
    count_before = (await db.execute(
        text("SELECT count(*) FROM txn.patient_message WHERE episode_id = :e AND day_after_discharge = :d"),
        {"e": episode_id, "d": post_op_day},
    )).scalar_one()

    await run_daily_checkin_dispatch()

    count_after = (await db.execute(
        text("SELECT count(*) FROM txn.patient_message WHERE episode_id = :e AND day_after_discharge = :d"),
        {"e": episode_id, "d": post_op_day},
    )).scalar_one()
    assert count_after == count_before, "Dispatch must be strictly idempotent per patient per day"
