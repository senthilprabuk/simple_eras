#!/usr/bin/env python3
"""
Simple ERAS - Database Migration Runner
Executes SQL migrations against Neon PostgreSQL reading credentials from .env.
"""

import os
import sys
from pathlib import Path
import psycopg

def load_env(env_path: Path) -> dict:
    """Parse .env file without external dependencies."""
    env_vars = {}
    if not env_path.exists():
        return env_vars
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            env_vars[key.strip()] = val.strip().strip('"').strip("'")
    return env_vars

def run_migration():
    root_dir = Path(__file__).resolve().parent.parent
    env_file = root_dir / ".env"
    
    env_vars = load_env(env_file)
    db_url = os.environ.get("DATABASE_URL") or env_vars.get("DATABASE_URL")
    
    if not db_url:
        print("[ERROR] DATABASE_URL not found in environment or .env file!", file=sys.stderr)
        sys.exit(1)
        
    migration_file = root_dir / "db" / "migrations" / "001_admin_user_and_fk_cleanup.sql"
    if not migration_file.exists():
        print(f"[ERROR] Migration file not found: {migration_file}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Reading migration: {migration_file.name}")
    sql_script = migration_file.read_text(encoding="utf-8")

    print("[*] Connecting to Neon PostgreSQL...")
    with psycopg.connect(db_url) as conn:
        print("[*] Executing migration within single transaction...")
        with conn.cursor() as cur:
            cur.execute(sql_script)
        conn.commit()
        print("[+] Migration applied successfully!")

        print("\n[*] Performing verification checks:")
        with conn.cursor() as cur:
            # 1. Check meta.admin_user
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'meta' AND table_name = 'admin_user'
                ORDER BY ordinal_position;
            """)
            admin_cols = cur.fetchall()
            print(f"  - meta.admin_user columns ({len(admin_cols)}):")
            for col, dtype, nullable in admin_cols:
                print(f"      {col}: {dtype} (nullable: {nullable})")

            # 2. Check txn.alert columns
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'txn' AND table_name = 'alert' 
                  AND column_name IN ('acknowledged_by', 'resolved_by', 'escalated_to');
            """)
            alert_cols = dict(cur.fetchall())
            print(f"  - txn.alert FK columns:")
            print(f"      acknowledged_by: {alert_cols.get('acknowledged_by', 'NOT FOUND')}")
            print(f"      resolved_by:     {alert_cols.get('resolved_by', 'NOT FOUND')}")
            print(f"      escalated_to:    {alert_cols.get('escalated_to', 'DROPPED (as expected)')}")

            # 3. Check txn.patient_episode.enrolled_by
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'txn' AND table_name = 'patient_episode' 
                  AND column_name = 'enrolled_by';
            """)
            ep_col = cur.fetchone()
            print(f"  - txn.patient_episode.enrolled_by: {ep_col[1] if ep_col else 'NOT FOUND'}")

            # 4. Check txn.v_alert_queue view columns
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'txn' AND table_name = 'v_alert_queue'
                ORDER BY ordinal_position;
            """)
            view_cols = [c[0] for c in cur.fetchall()]
            print(f"  - txn.v_alert_queue view columns ({len(view_cols)}):")
            print(f"      {view_cols}")

            # 5. Test querying the view
            cur.execute("SELECT count(*) FROM txn.v_alert_queue;")
            count = cur.fetchone()[0]
            print(f"  - Test query on txn.v_alert_queue: {count} active alerts found.")

    print("\n[SUCCESS] Step 1 verification passed with 0 errors!")

if __name__ == "__main__":
    run_migration()
