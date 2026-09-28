"""
Print today's check-in link for one patient, as the WhatsApp reminder would carry
it, so the patient check-in page can be opened without signing in.

    backend/.venv/Scripts/python.exe .claude/skills/run-simple-eras/checkin_link.py FX-01

Uses the database and JWT secret in backend/.env.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import async_session_factory  # noqa: E402
from app.services.magic_token import generate_magic_token  # noqa: E402


async def main(mrn: str) -> None:
    async with async_session_factory() as session:
        row = (await session.execute(text("""
            SELECT e.episode_id, ((now() AT TIME ZONE h.timezone)::date - e.discharge_date)::int AS day
            FROM txn.patient_episode e
            JOIN txn.patient p   ON p.patient_id = e.patient_id
            JOIN meta.hospital h ON h.hospital_id = e.hospital_id
            WHERE p.mrn = :mrn AND e.status = 'active'
        """), {"mrn": mrn})).mappings().first()
    if row is None:
        sys.exit(f"No active episode for MRN {mrn}")
    token = generate_magic_token(row["episode_id"], row["day"])
    print(f"{settings.FRONTEND_BASE_URL.rstrip('/')}/checkin?token={token}")


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "FX-01"))
