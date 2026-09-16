#!/usr/bin/env python3
"""
Step 2 Verification Smoke Test
Checks all required dependencies, security algorithms, and database drivers.
"""

import sys
import os

print("[*] Testing imports:")
try:
    import fastapi
    print(f"  [+] FastAPI: {fastapi.__version__}")
    import uvicorn
    print(f"  [+] Uvicorn: {uvicorn.__version__}")
    import sqlalchemy
    print(f"  [+] SQLAlchemy: {sqlalchemy.__version__}")
    import asyncpg
    print(f"  [+] asyncpg: {asyncpg.__version__}")
    import pydantic
    print(f"  [+] Pydantic: {pydantic.__version__}")
    import pydantic_settings
    print(f"  [+] Pydantic Settings: {pydantic_settings.__version__}")
    import jwt
    print(f"  [+] PyJWT: {jwt.__version__}")
    import bcrypt
    print(f"  [+] bcrypt: {bcrypt.__version__}")
    import apscheduler
    print(f"  [+] APScheduler: {apscheduler.__version__}")
    import pytest
    print(f"  [+] Pytest: {pytest.__version__}")
    import httpx
    print(f"  [+] HTTPX: {httpx.__version__}")
except Exception as e:
    print(f"[FAIL] Import error: {e}")
    sys.exit(1)

print("\n[*] Testing bcrypt password hashing and verification:")
pwd = "SecurePassword123!"
salt = bcrypt.gensalt()
hashed = bcrypt.hashpw(pwd.encode("utf-8"), salt).decode("utf-8")
assert bcrypt.checkpw(pwd.encode("utf-8"), hashed.encode("utf-8")), "Password check failed!"
print("  [+] Bcrypt hashing & verification functioning perfectly.")

print("\n[*] Testing JWT signing and verification:")
payload = {"sub": "test-admin-uuid", "hospital_id": 1, "role": "admin"}
token = jwt.encode(payload, "secret-key-test", algorithm="HS256")
decoded = jwt.decode(token, "secret-key-test", algorithms=["HS256"])
assert decoded["sub"] == "test-admin-uuid", "JWT decoding mismatch!"
print(f"  [+] JWT encode & decode successful: {decoded}")

print("\n[*] Checking directory structure:")
from pathlib import Path
backend_dir = Path(__file__).resolve().parent
expected_dirs = [
    backend_dir / "app",
    backend_dir / "app" / "core",
    backend_dir / "app" / "db",
    backend_dir / "app" / "db" / "models",
    backend_dir / "app" / "schemas",
    backend_dir / "app" / "api",
    backend_dir / "app" / "api" / "v1",
    backend_dir / "app" / "services",
    backend_dir / "seed",
    backend_dir / "tests",
]
for d in expected_dirs:
    assert d.exists(), f"Directory missing: {d}"
    assert (d / "__init__.py").exists(), f"__init__.py missing in {d}"
print("  [+] All 10 backend packages and sub-packages are scaffolded with __init__.py.")

print("\n[SUCCESS] Step 2 backend scaffolding & dependencies verified with 0 errors!")
