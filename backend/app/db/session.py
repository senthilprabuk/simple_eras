from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

# Create async engine optimized for Neon PgBouncer transaction pooling
# Disabling statement caching is critical to avoid 'prepared statement already exists' collisions
async_engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "ssl": "require",
    },
)

# Async session factory
async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding one session per request, rolled back on error."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

async def get_system_db() -> AsyncGenerator[AsyncSession, None]:
    """
    A session that is never tenant-scoped, for the few endpoints that must touch
    password hashes, which eras_app cannot read. Every query made through it
    must filter on the caller's hospital explicitly.
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

async def scope_to_hospital(session: AsyncSession, hospital_id: int) -> None:
    """
    Restrict the rest of this transaction to one hospital's rows via row-level
    security (db/schema/04_security.sql). Both settings are transaction-local, so
    they end at commit: a tenant endpoint must not query after committing.
    """
    await session.execute(text("set local role eras_app"))
    await session.execute(
        text("select set_config('app.hospital_id', :hospital_id, true)"),
        {"hospital_id": str(hospital_id)},
    )
