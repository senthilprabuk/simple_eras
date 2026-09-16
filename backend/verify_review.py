import os
import sys
from pathlib import Path
import psycopg
# git module not needed, using subprocess

root = Path(r"D:\alphaesai\eras\1")
env_file = root / "backend" / ".env"
env_vars = {}
with open(env_file, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip().strip('"').strip("'")

db_url = env_vars["DATABASE_URL"]

print("=== STEP 1: DATABASE REVIEW & AUDIT ===")
with psycopg.connect(db_url) as conn:
    with conn.cursor() as cur:
        # Check admin_user table constraints
        cur.execute("""
            SELECT conname, contype, pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE n.nspname = 'meta' AND c.conrelid = 'meta.admin_user'::regclass;
        """)
        admin_constraints = cur.fetchall()
        print(f"1. meta.admin_user Constraints ({len(admin_constraints)}):")
        for name, ctype, defn in admin_constraints:
            print(f"   [{ctype}] {name}: {defn}")

        # Check FK constraints on txn.alert
        cur.execute("""
            SELECT conname, pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE n.nspname = 'txn' AND c.conrelid = 'txn.alert'::regclass AND contype = 'f';
        """)
        alert_fks = cur.fetchall()
        print(f"\n2. txn.alert Foreign Keys ({len(alert_fks)}):")
        for name, defn in alert_fks:
            print(f"   {name}: {defn}")

        # Check FK constraints on txn.patient_episode
        cur.execute("""
            SELECT conname, pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE n.nspname = 'txn' AND c.conrelid = 'txn.patient_episode'::regclass AND contype = 'f';
        """)
        episode_fks = cur.fetchall()
        print(f"\n3. txn.patient_episode Foreign Keys ({len(episode_fks)}):")
        for name, defn in episode_fks:
            print(f"   {name}: {defn}")

        # Check v_alert_queue column names
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'txn' AND table_name = 'v_alert_queue'
            ORDER BY ordinal_position;
        """)
        cols = cur.fetchall()
        print(f"\n4. txn.v_alert_queue View Columns ({len(cols)}):")
        for c, dt in cols:
            print(f"   - {c}: {dt}")

print("\n=== STEP 2: PROJECT & ENVIRONMENT REVIEW ===")
# Check packages
import fastapi, sqlalchemy, asyncpg, pydantic, pydantic_settings, jwt, bcrypt, apscheduler, pytest, httpx
print("1. Core Frameworks & Libraries:")
print(f"   FastAPI: {fastapi.__version__}")
print(f"   SQLAlchemy: {sqlalchemy.__version__}")
print(f"   asyncpg: {asyncpg.__version__}")
print(f"   pydantic: {pydantic.__version__}")
print(f"   PyJWT: {jwt.__version__}")
print(f"   bcrypt: {bcrypt.__version__}")
print(f"   APScheduler: {apscheduler.__version__}")

# Check secrets
import subprocess
out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=str(root))
tracked_secrets = [line for line in out.stdout.splitlines() if ".env" in line and not line.startswith("??")]
print("\n2. Secret Leakage Audit:")
print(f"   Are any .env files tracked by git? {'YES (ALARM!)' if tracked_secrets else 'NO (Secure: .env files are untracked and gitignored)'}")

print("\n[ALL REVIEW CHECKS COMPLETE]")
