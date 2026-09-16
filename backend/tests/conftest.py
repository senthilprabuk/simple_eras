import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator, Dict
from uuid import uuid4
import pytest
import pytest_asyncio
import httpx
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Ensure backend root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
import app.db.session as session_module

# Configure NullPool during test execution so connections are not shared across event loops
test_engine = create_async_engine(
    settings.async_database_url,
    poolclass=NullPool,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "ssl": "require",
    },
)
test_session_factory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
session_module.async_engine = test_engine
session_module.async_session_factory = test_session_factory

# Also import app after patching db session
from app.main import app
from app.core.security import get_password_hash

H2_EMAIL = "admin.h2@testmetro.org"
H2_PASSWORD = "password123"

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_multi_tenant_fixtures():
    """
    Ensure Hospital 2 exists in meta.hospital and an active admin exists in meta.admin_user
    so cross-tenant isolation can be authentically validated.
    """
    async with session_module.async_session_factory() as session:
        # Check / Insert Hospital 2 using identity sequence
        res = await session.execute(text("""
            INSERT INTO meta.hospital (
                hospital_code, hospital_name, city, timezone, ack_window_secs
            ) VALUES (
                'TEST-02', 'Test Metro Hospital', 'Coimbatore', 'Asia/Kolkata', 900
            )
            ON CONFLICT (hospital_code) DO UPDATE
            SET hospital_name = EXCLUDED.hospital_name
            RETURNING hospital_id;
        """))
        h2_id = res.scalar()
        if not h2_id:
            res = await session.execute(text("SELECT hospital_id FROM meta.hospital WHERE hospital_code = 'TEST-02';"))
            h2_id = res.scalar()

        # Check / Insert Admin for Hospital 2
        hashed = get_password_hash(H2_PASSWORD)
        await session.execute(text("""
            INSERT INTO meta.admin_user (
                admin_user_id, hospital_id, email, hashed_password, full_name, role, is_active
            ) VALUES (
                :aid, :hid, :email, :pwd, 'Test Hospital 2 Admin', 'admin', true
            )
            ON CONFLICT (hospital_id, email) DO UPDATE
            SET hashed_password = EXCLUDED.hashed_password, is_active = true;
        """), {
            "aid": uuid4(),
            "hid": h2_id,
            "email": H2_EMAIL,
            "pwd": hashed
        })
        await session.commit()

@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provides an async HTTP client connected directly to the FastAPI app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

@pytest_asyncio.fixture
async def nurse_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    """Authenticates Nurse Sarah (Hospital 1) and returns authorization headers."""
    res = await client.post("/api/v1/auth/login", json={
        "email": "nurse.sarah@stmarys.org",
        "password": "password123"
    })
    assert res.status_code == 200, f"Nurse login failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest_asyncio.fixture
async def surgeon_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    """Authenticates Dr. Mehta (Hospital 1) and returns authorization headers."""
    res = await client.post("/api/v1/auth/login", json={
        "email": "dr.mehta@stmarys.org",
        "password": "password123"
    })
    assert res.status_code == 200, f"Surgeon login failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest_asyncio.fixture
async def h2_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    """Authenticates Admin for Hospital 2 and returns authorization headers."""
    res = await client.post("/api/v1/auth/login", json={
        "email": H2_EMAIL,
        "password": H2_PASSWORD
    })
    assert res.status_code == 200, f"H2 admin login failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
