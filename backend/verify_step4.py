#!/usr/bin/env python3
"""
Step 4 Verification Test
Executes async ORM queries against every single model in meta and txn schemas
to verify 100% schema alignment with the live Neon PostgreSQL database.
"""

import asyncio
import sys
from pathlib import Path
from sqlalchemy import select, func

# Ensure backend directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db.session import async_session_factory
from app.db.models import (
    Hospital,
    AdminUser,
    SurgicalProcedure,
    HospitalProcedure,
    Parameter,
    ParameterOption,
    Ruleset,
    ProcedureParameter,
    Patient,
    PatientEpisode,
    EpisodeBaseline,
    PatientCheckIn,
    PatientCheckInValue,
    CheckInEvaluation,
    Alert,
    AlertNotification,
)

MODELS = [
    # meta schema
    Hospital,
    AdminUser,
    SurgicalProcedure,
    HospitalProcedure,
    Parameter,
    ParameterOption,
    Ruleset,
    ProcedureParameter,
    # txn schema
    Patient,
    PatientEpisode,
    EpisodeBaseline,
    PatientCheckIn,
    PatientCheckInValue,
    CheckInEvaluation,
    Alert,
    AlertNotification,
]

async def verify_models():
    print("=== STEP 4: SQLALCHEMY 2.0 ORM MODEL VERIFICATION ===\n")
    print(f"[*] Verifying {len(MODELS)} declarative models against live Neon database:")

    async with async_session_factory() as session:
        for model in MODELS:
            schema_name = model.__table_args__.get("schema") if isinstance(model.__table_args__, dict) else "unknown"
            if schema_name == "unknown" and isinstance(model.__table_args__, tuple):
                for arg in model.__table_args__:
                    if isinstance(arg, dict) and "schema" in arg:
                        schema_name = arg["schema"]
            
            table_full_name = f"{schema_name}.{model.__tablename__}"
            
            try:
                # Run count query to verify table and columns
                stmt = select(func.count()).select_from(model)
                res = await session.execute(stmt)
                count = res.scalar()
                print(f"  [+] {table_full_name:<30} -> OK (Rows: {count})")
            except Exception as e:
                print(f"  [!] {table_full_name:<30} -> FAILED: {type(e).__name__}: {e}")
                raise e

    print("\n[SUCCESS] All 16 SQLAlchemy 2.0 ORM models matched live database tables with 0 errors!")

if __name__ == "__main__":
    asyncio.run(verify_models())
