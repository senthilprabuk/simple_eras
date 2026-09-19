#!/usr/bin/env python3
"""
Apply pending SQL migrations from db/migrations/ in version order.

Each applied version is recorded in meta.schema_migration, so a migration runs
at most once per database. A database built from db/schema/ already records
every migration folded into it.

Usage:
    python db/migrate.py                  apply pending migrations
    python db/migrate.py --status         list applied and pending migrations
    python db/migrate.py --baseline 002   record 001..002 as applied without running them

DATABASE_URL is read from the environment, falling back to backend/.env.
"""

import argparse
import os
import re
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent
MIGRATIONS = ROOT / "migrations"
ENV_FILE = ROOT.parent / "backend" / ".env"
FILENAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
# Migrations written before this runner existed wrap themselves in BEGIN/COMMIT.
OWN_TRANSACTION = re.compile(r"^\s*begin\s*;", re.IGNORECASE | re.MULTILINE)


def database_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "DATABASE_URL":
                return value.strip().strip('"').strip("'")
    sys.exit("DATABASE_URL is not set and backend/.env does not define it.")


def discover() -> list[tuple[str, Path]]:
    found = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        match = FILENAME.match(path.name)
        if not match:
            sys.exit(f"Unexpected file in db/migrations/: {path.name} (expected NNN_name.sql)")
        found.append((match.group(1), path))
    versions = [v for v, _ in found]
    if len(versions) != len(set(versions)):
        sys.exit("Two migrations share a version number.")
    return found


def record(conn: psycopg.Connection, version: str, path: Path) -> None:
    conn.execute(
        "insert into meta.schema_migration (version, name) values (%s, %s)",
        (version, path.stem),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true", help="list migrations without applying any")
    parser.add_argument("--baseline", metavar="VERSION",
                        help="record every migration up to VERSION as applied, without running it")
    args = parser.parse_args()

    migrations = discover()

    with psycopg.connect(database_url(), autocommit=True) as conn:
        if conn.execute("select to_regclass('meta.hospital')").fetchone()[0] is None:
            sys.exit("This database has no schema. Build it from db/schema/ first; "
                     "those files record the migrations they already contain.")

        tracked = conn.execute("select to_regclass('meta.schema_migration')").fetchone()[0] is not None
        if not tracked:
            conn.execute("""
                create table meta.schema_migration (
                    version     text        primary key,
                    name        text        not null,
                    applied_at  timestamptz not null default now()
                )
            """)
        applied = {row[0] for row in conn.execute("select version from meta.schema_migration")}

        if args.baseline:
            with conn.transaction():
                for version, path in migrations:
                    if version <= args.baseline and version not in applied:
                        record(conn, version, path)
                        print(f"recorded {path.name} as applied (not run)")
            return

        if not applied:
            sys.exit("This database has tables but no recorded migrations, so there is no safe way to\n"
                     "tell which have run. Record the ones it already has, e.g.\n"
                     "    python db/migrate.py --baseline 002\n"
                     "then run this again.")

        pending = [(v, p) for v, p in migrations if v not in applied]

        if args.status:
            for version, path in migrations:
                print(f"  {'applied' if version in applied else 'PENDING'}  {path.name}")
            return

        if not pending:
            print("Database is up to date.")
            return

        for version, path in pending:
            sql = path.read_text(encoding="utf-8")
            if OWN_TRANSACTION.search(sql):
                conn.execute(sql)
                record(conn, version, path)
            else:
                with conn.transaction():
                    conn.execute(sql)
                    record(conn, version, path)
            print(f"applied {path.name}")


if __name__ == "__main__":
    main()
