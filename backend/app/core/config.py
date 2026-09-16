from pathlib import Path
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url, URL

# Locate .env in backend/ or root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"
if not ENV_FILE.exists():
    ENV_FILE = BASE_DIR.parent / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database
    DATABASE_URL: str

    # Security & JWT
    JWT_SECRET_KEY: str = "change-this-to-a-secure-random-32-byte-secret-key-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720  # 12 hours

    # Hospital defaults & Escalation timing
    DEFAULT_ACK_WINDOW_SECS: int = 900     # 15 minutes
    ESCALATION_SWEEP_INTERVAL_SECS: int = 60

    # CORS
    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS origins as a list of strings."""
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def async_database_url(self) -> URL:
        """
        Dynamically adapts DATABASE_URL for asyncpg with Neon's PgBouncer pooler.
        Strips query parameters not recognized by asyncpg DSN and sets drivername.
        """
        u = make_url(self.DATABASE_URL)
        query = dict(u.query)
        # asyncpg receives ssl configuration via connect_args or ssl parameter
        query.pop("sslmode", None)
        query.pop("channel_binding", None)
        return u.set(drivername="postgresql+asyncpg", query=query)

settings = Settings()
