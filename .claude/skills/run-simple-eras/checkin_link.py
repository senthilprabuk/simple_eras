"""
Print today's check-in link for patients, as the WhatsApp reminder would carry
it, so the patient check-in page can be opened without signing in.

    backend/.venv/Scripts/python.exe .claude/skills/run-simple-eras/checkin_link.py FX-01
    backend/.venv/Scripts/python.exe .claude/skills/run-simple-eras/checkin_link.py FX-06 FX-01 FX-12

One MRN prints the bare link; several print one labelled line each. Uses the
database and JWT secret in backend/.env.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import async_session_factory  # noqa: E402
from app.services.magic_token import generate_magic_token  # noqa: E402

LANGUAGES = {"en": "English", "ta": "Tamil", "hi": "Hindi"}


async def main(mrns: list) -> None:
    async with async_session_factory() as session:
        rows = {r["mrn"]: r for r in (await session.execute(text("""
            SELECT p.mrn, p.patient_name, p.language_code, e.episode_id,
                   ((now() AT TIME ZONE h.timezone)::date - e.discharge_date)::int AS day,
                   EXISTS (SELECT 1 FROM txn.patient_check_in c
                           WHERE c.episode_id = e.episode_id AND NOT c.is_superseded
                             AND c.day_after_discharge = ((now() AT TIME ZONE h.timezone)::date - e.discharge_date)::int
                   ) AS checked_in_today
            FROM txn.patient_episode e
            JOIN txn.patient p   ON p.patient_id = e.patient_id
            JOIN meta.hospital h ON h.hospital_id = e.hospital_id
            WHERE p.mrn = ANY(:mrns) AND e.status = 'active'
        """), {"mrns": mrns})).mappings().all()}

    missing = [m for m in mrns if m not in rows]
    if missing:
        sys.exit(f"No active episode for MRN {', '.join(missing)}")

    base = settings.FRONTEND_BASE_URL.rstrip("/")
    for mrn in mrns:
        r = rows[mrn]
        url = f"{base}/checkin#token={generate_magic_token(r['episode_id'], r['day'])}"
        if len(mrns) == 1:
            print(url)
        else:
            state = "already checked in today" if r["checked_in_today"] else "not checked in yet"
            print(f"  {mrn}  {r['patient_name']}, {LANGUAGES.get(r['language_code'], r['language_code'])}, "
                  f"day {r['day']}, {state}\n        {url}")


asyncio.run(main(sys.argv[1:] or ["FX-01"]))
