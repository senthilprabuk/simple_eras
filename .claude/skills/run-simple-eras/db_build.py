"""
Build an empty database from db/schema/ and db/seed/, the way the backend test
suite builds its throwaway one. Refuses a database that already has the ERAS
schema: upgrade that one with db/migrate.py instead.

    backend/.venv/Scripts/python.exe .claude/skills/run-simple-eras/db_build.py
    backend/.venv/Scripts/python.exe .claude/skills/run-simple-eras/db_build.py --fixtures-only

--fixtures-only re-runs db/seed/02_fixtures.sql on a built database, which deletes
and rebuilds the FX-* demo patients (and everything recorded against them) at
post-op day 21. Follow it with backend/seed/seed_demo.py to restore the demo alerts.

Uses DATABASE_URL from the environment, else backend/.env.
"""

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

import psycopg  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import settings  # noqa: E402

SCHEMA_AND_SEED = [
    "db/schema/01_meta.sql",
    "db/schema/02_txn.sql",
    "db/schema/03_views.sql",
    "db/schema/04_security.sql",
    "db/seed/01_reference.sql",
    "db/seed/02_fixtures.sql",
]
FIXTURES = ["db/seed/02_fixtures.sql"]

fixtures_only = "--fixtures-only" in sys.argv[1:]
url = make_url(settings.DATABASE_URL)
with psycopg.connect(url.render_as_string(hide_password=False), autocommit=True) as conn:
    built = conn.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'meta'").fetchone() is not None
    if fixtures_only and not built:
        sys.exit(f"{url.host}/{url.database} has no ERAS schema yet; run without --fixtures-only first.")
    if not fixtures_only and built:
        sys.exit(f"{url.host}/{url.database} already has the ERAS schema; use db/migrate.py to upgrade it.")
    for rel in FIXTURES if fixtures_only else SCHEMA_AND_SEED:
        started = time.time()
        conn.execute((REPO / rel).read_text(encoding="utf-8"))
        print(f"applied {rel} ({time.time() - started:.1f}s)")
print(f"{'reset fixtures in' if fixtures_only else 'built'} {url.host}/{url.database}")
