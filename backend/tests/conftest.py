"""
Every test session runs against its own throwaway database, built from
db/schema/ and db/seed/ and dropped afterwards. Tests may therefore create and
mutate data freely, and never touch the database named in .env.
"""

import sys
import uuid
from pathlib import Path
from typing import AsyncGenerator, Dict

import httpx
import psycopg
import pytest
import pytest_asyncio
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy.engine import make_url  # noqa: E402
from app.core.config import settings  # noqa: E402
import app.db.session as session_module  # noqa: E402

TEST_DB_NAME = f"eras_test_{uuid.uuid4().hex[:12]}"
_configured = make_url(settings.DATABASE_URL)
ADMIN_SYNC_URL = _configured.render_as_string(hide_password=False)
TEST_SYNC_URL = _configured.set(database=TEST_DB_NAME).render_as_string(hide_password=False)

BUILD_FILES = [
    "db/schema/01_meta.sql",
    "db/schema/02_txn.sql",
    "db/schema/03_views.sql",
    "db/schema/04_security.sql",
    "db/seed/01_reference.sql",
    "db/seed/02_fixtures.sql",
]

# NullPool so connections are never shared across event loops.
test_engine = create_async_engine(
    settings.async_database_url.set(database=TEST_DB_NAME),
    poolclass=NullPool,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "ssl": "require",
    },
)
isolated_session_factory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Patch before importing the app, so modules that bind the factory at import time get this one.
session_module.async_engine = test_engine
session_module.async_session_factory = isolated_session_factory

from app.main import app  # noqa: E402
from app.core.login_throttle import login_throttle  # noqa: E402
from seed.seed_demo import seed_demo  # noqa: E402
from tests.support import create_hospital  # noqa: E402

NURSE = ("nurse.sarah@stmarys.org", "password123")
SURGEON = ("dr.mehta@stmarys.org", "password123")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def test_database():
    with psycopg.connect(ADMIN_SYNC_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    try:
        with psycopg.connect(TEST_SYNC_URL, autocommit=True) as conn:
            for rel in BUILD_FILES:
                conn.execute((REPO / rel).read_text(encoding="utf-8"))
        await seed_demo(isolated_session_factory)
        yield
    finally:
        await test_engine.dispose()
        with psycopg.connect(ADMIN_SYNC_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')


@pytest.fixture(autouse=True)
def checkin_simulator_on(monkeypatch):
    """Most tests submit check-ins through the simulator; the tests of it being off turn it off."""
    monkeypatch.setattr(settings, "CHECKIN_SIMULATOR_ENABLED", True)


@pytest.fixture(autouse=True)
def reset_login_throttle():
    login_throttle.clear()
    yield
    login_throttle.clear()


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """A session as the connecting role: sees every hospital, like the system jobs."""
    async with isolated_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def login_headers(client: httpx.AsyncClient, email: str, password: str, hospital_id=None) -> Dict[str, str]:
    body = {"email": email, "password": password}
    if hospital_id is not None:
        body["hospital_id"] = hospital_id
    res = await client.post("/api/v1/auth/login", json=body)
    assert res.status_code == 200, f"login failed for {email}: {res.text}"
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest_asyncio.fixture
async def nurse_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    return await login_headers(client, *NURSE)


@pytest_asyncio.fixture
async def surgeon_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    return await login_headers(client, *SURGEON)


@pytest_asyncio.fixture(scope="session")
async def second_hospital():
    """A second tenant with one admin and one patient, for isolation tests."""
    async with isolated_session_factory() as session:
        return await create_hospital(session, "TEST-02")


@pytest_asyncio.fixture
async def h2_headers(client: httpx.AsyncClient, second_hospital) -> Dict[str, str]:
    return await login_headers(client, second_hospital.email, second_hospital.password)
